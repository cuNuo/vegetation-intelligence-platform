# backend/app/api/routes.py
# 文件说明：平台 REST、OGC、Agent SSE 与瓦片路由。
# 主要职责：完成协议转换、输入校验、异常映射和服务编排。
# 对外入口：router 及 /api、/processes、/jobs 接口。
# 依赖边界：不实现公式和持久化细节。

"""平台REST与OGC API - Processes兼容路由。"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse

from app.api.schemas import (
    AgentCustomIndexRequest,
    AgentKnowledgeImportRequest,
    AgentPlanRequest,
    AgentResultInterpretRequest,
    ChangeDetectionRequest,
    ConfirmPlanRequest,
    CustomFormulaRequest,
    ExecutionRequest,
    RasterInspectRequest,
    RecipeRequest,
    ZonalStatisticsRequest,
)
from app.core.indices import CORE_INDEX_COUNT, INDEX_REGISTRY, get_index
from app.services.advanced_analysis import (
    calculate_zonal_statistics,
    detect_change,
    validate_custom_expression,
)
from app.services.agent import vegetation_agent
from app.services.agent_knowledge_store import (
    is_enabled as is_agent_knowledge_store_enabled,
)
from app.services.agent_knowledge_store import (
    save_knowledge_document,
)
from app.services.agent_session_store import is_enabled as is_agent_session_store_enabled
from app.services.agent_tools import register_custom_index
from app.services.assets import (
    create_upload_url,
    inspect_raster,
    resolve_source,
    save_uploaded_asset,
)
from app.services.custom_index_store import is_enabled
from app.services.jobs import job_manager
from app.services.planner import has_cuda
from app.services.raster_pipeline import RasterTask
from app.services.tiles import render_geotiff_tile
from app.settings import settings

router = APIRouter()
custom_recipes: dict[str, dict[str, Any]] = {}


@router.get("/api/indices")
def list_indices(
    category: str | None = Query(default=None),
    band: str | None = Query(default=None),
) -> dict[str, Any]:
    """列出内置和动态指数，并支持分类与波段筛选。"""
    items = list(INDEX_REGISTRY.values())
    if category:
        items = [item for item in items if category in item.categories]
    if band:
        items = [item for item in items if band in item.required_bands]
    return {"total": len(items), "items": [item.public_metadata() for item in items]}


@router.get("/api/indices/{index_id}")
def index_detail(index_id: str) -> dict[str, Any]:
    """执行 index_detail 对应的领域操作并返回结构化结果。"""
    try:
        return get_index(index_id).public_metadata()
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/processes")
def list_processes() -> dict[str, Any]:
    """执行 list_processes 对应的领域操作并返回结构化结果。"""
    return {
        "processes": [
            {
                "id": item.id,
                "title": item.name,
                "description": item.description,
                "version": "1.0.0",
                "jobControlOptions": ["sync-execute", "async-execute", "dismiss"],
            }
            for item in INDEX_REGISTRY.values()
        ]
    }


@router.get("/processes/{process_id}")
def describe_process(process_id: str) -> dict[str, Any]:
    """执行 describe_process 对应的领域操作并返回结构化结果。"""
    try:
        item = get_index(process_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        **item.public_metadata(),
        "version": "1.0.0",
        "jobControlOptions": ["sync-execute", "async-execute", "dismiss"],
        "inputs": {
            "source": {"schema": {"type": "object"}},
            "bands": {"schema": {"type": "object"}},
            "engine": {"schema": {"enum": ["auto", "numpy", "joblib", "torch"]}},
        },
        "outputs": {"result": {"schema": {"type": "object"}}},
    }


@router.post("/processes/{process_id}/execution")
def execute_process(
    process_id: str,
    request: ExecutionRequest,
    prefer: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """根据 Prefer 头选择同步结果或异步任务响应。"""
    try:
        indices = request.indices
        if process_id != "batch":
            get_index(process_id)
            indices = [process_id]
        task = _to_raster_task(request, indices)
    except ValueError as error:
        if "未知植被指数" in str(error):
            raise HTTPException(status_code=404, detail=str(error)) from error
        raise HTTPException(status_code=422, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if prefer and "respond-async" in prefer.lower():
        record = job_manager.submit(task, request.priority)
        return {
            "jobID": record.id,
            "status": record.status,
            "location": f"/jobs/{record.id}",
        }
    try:
        return {"status": "successful", "outputs": job_manager.execute_sync(task)}
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/jobs")
def list_jobs() -> dict[str, Any]:
    """执行 list_jobs 对应的领域操作并返回结构化结果。"""
    return {"jobs": job_manager.list()}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """执行 get_job 对应的领域操作并返回结构化结果。"""
    try:
        return job_manager.get(job_id).public()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/jobs/{job_id}/results")
def get_job_results(job_id: str) -> dict[str, Any]:
    """执行 get_job_results 对应的领域操作并返回结构化结果。"""
    try:
        record = job_manager.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if record.status != "successful":
        raise HTTPException(status_code=409, detail=f"任务状态为{record.status}，结果尚不可用")
    return record.result or {}


@router.delete("/jobs/{job_id}", status_code=status.HTTP_202_ACCEPTED)
def cancel_job(job_id: str) -> dict[str, Any]:
    """执行 cancel_job 对应的领域操作并返回结构化结果。"""
    try:
        return job_manager.cancel(job_id).public()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/api/assets/inspect")
def inspect_asset(request: RasterInspectRequest) -> dict[str, Any]:
    """执行 inspect_asset 对应的领域操作并返回结构化结果。"""
    try:
        return inspect_raster(request.path)
    except (FileNotFoundError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error



@router.post("/api/assets/upload", status_code=status.HTTP_201_CREATED)
async def upload_asset(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    """执行 upload_asset 对应的领域操作并返回结构化结果。"""
    try:
        return await save_uploaded_asset(file)
    except (ValueError, FileNotFoundError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

@router.post("/api/assets/upload-url")
def upload_url(object_key: str = Query(min_length=1)) -> dict[str, str]:
    """执行 upload_url 对应的领域操作并返回结构化结果。"""
    try:
        return create_upload_url(object_key)
    except Exception as error:  # noqa: BLE001 - 转换外部服务错误
        raise HTTPException(status_code=503, detail=f"MinIO不可用: {error}") from error


@router.get("/api/tiles/{z}/{x}/{y}.png")
def geotiff_tile(
    z: int,
    x: int,
    y: int,
    key: Annotated[str, Query(min_length=1)],
) -> Response:
    """执行 geotiff_tile 对应的领域操作并返回结构化结果。"""
    try:
        tile = render_geotiff_tile(key, z, x, y)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001 - 栅格渲染边界需要返回可诊断错误
        raise HTTPException(status_code=422, detail=f"瓦片渲染失败: {error}") from error
    return Response(content=tile, media_type="image/png")


@router.post("/api/agent/plan")
async def create_agent_plan(request: AgentPlanRequest) -> dict[str, Any]:
    """执行 create_agent_plan 对应的领域操作并返回结构化结果。"""
    return await vegetation_agent.create_plan(
        request.message,
        request.available_bands,
        request.raster_width,
        request.raster_height,
        request.llm,
        request.enable_web_search,
        [document.model_dump() for document in request.external_documents],
        request.custom_index.model_dump(by_alias=True) if request.custom_index else None,
        request.session_id,
    )


@router.post("/api/agent/plan/stream")
async def stream_agent_plan(request: AgentPlanRequest) -> StreamingResponse:
    """通过 SSE 分阶段返回状态、思考摘要和最终计划。"""
    bands_label = " / ".join(request.available_bands) if request.available_bands else "未提供"
    size_label = (
        f"{request.raster_width}×{request.raster_height}"
        if request.raster_width and request.raster_height
        else "未提供"
    )
    document_count = len(request.external_documents)

    async def events():
        """执行 events 对应的领域操作并返回结构化结果。"""
        yield _sse(
            "thought",
            {
                "title": "建立上下文",
                "detail": (
                    f"影像尺寸 {size_label}；可用波段 {bands_label}；"
                    f"外部资料 {document_count} 条；正在整理历史会话。"
                ),
                "status": "running",
            },
        )
        yield _sse("status", {"message": "已收到问题，正在建立分析上下文。"})
        await asyncio.sleep(0)
        try:
            yield _sse(
                "thought",
                {
                    "title": "检索知识",
                    "detail": (
                        "正在匹配指数适用场景、必要波段、公式约束和可执行性；"
                        f"外部知识库补充 {document_count} 条。"
                    ),
                    "status": "running",
                },
            )
            yield _sse("status", {"message": "正在检索本地指数知识和外部知识库。"})
            await asyncio.sleep(0)
            if request.enable_web_search:
                yield _sse(
                    "thought",
                    {
                        "title": "网络检索",
                        "detail": "正在补充公开资料中的适用场景、异常区域线索和判读限制。",
                        "status": "running",
                    },
                )
                yield _sse("status", {"message": "正在联合网络检索适用场景。"})
                await asyncio.sleep(0)
            yield _sse(
                "thought",
                {
                    "title": "生成方案",
                    "detail": (
                        "正在综合波段映射、指数需求、引擎选择、内存估算和人工确认边界。"
                    ),
                    "status": "running",
                },
            )
            await asyncio.sleep(0)
            plan = await vegetation_agent.create_plan(
                request.message,
                request.available_bands,
                request.raster_width,
                request.raster_height,
                request.llm,
                request.enable_web_search,
                [document.model_dump() for document in request.external_documents],
                request.custom_index.model_dump(by_alias=True) if request.custom_index else None,
                request.session_id,
            )
            selected_indices = [str(index).upper() for index in plan.get("selectedIndices", [])]
            recommendations = plan.get("recommendations", [])
            executable_count = sum(1 for item in recommendations if item.get("executable"))
            yield _sse(
                "thought",
                {
                    "title": "推荐指数",
                    "detail": (
                        f"已选 {', '.join(selected_indices) if selected_indices else '无'}；"
                        f"可执行 {executable_count}/{len(recommendations)} 个。"
                    ),
                    "status": "done",
                },
            )
            await asyncio.sleep(0)
            yield _sse(
                "thought",
                {
                    "title": "执行引擎",
                    "detail": (
                        f"推荐 {str(plan.get('engine', 'auto')).upper()}；"
                        f"估算内存 {plan.get('estimatedMemoryMb', '未知')} MB；"
                        "提交前仍需人工确认。"
                    ),
                    "status": "done",
                },
            )
            await asyncio.sleep(0)
            yield _sse(
                "status",
                {
                    "message": (
                        f"方案已生成：{plan['title']}，"
                        f"可执行指数 {len(plan['selectedIndices'])} 个。"
                    )
                },
            )
            yield _sse("plan", plan)
            yield _sse("done", {"message": "方案生成完成，等待人工确认。"})
        except Exception as error:  # noqa: BLE001 - 流式边界需要把失败写回客户端
            yield _sse("error", {"message": str(error)})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/api/agent/chat")
async def chat_with_agent(request: AgentPlanRequest) -> dict[str, Any]:
    """执行 chat_with_agent 对应的领域操作并返回结构化结果。"""
    plan = await create_agent_plan(request)
    return {
        "message": f"建议执行“{plan['title']}”。我已生成可编辑方案，确认后才会提交计算。",
        "plan": plan,
    }


@router.post("/api/agent/plans/{plan_id}/confirm")
def confirm_agent_plan(plan_id: str, request: ConfirmPlanRequest) -> dict[str, Any]:
    """执行 confirm_agent_plan 对应的领域操作并返回结构化结果。"""
    try:
        plan = vegetation_agent.get_plan(plan_id)
        allowed_indices = {
            item["id"]
            for item in plan["recommendations"]
            if item["executable"]
        }
        selected_indices = request.indices or plan["selectedIndices"]
        invalid_indices = sorted(set(selected_indices) - allowed_indices)
        if invalid_indices:
            raise ValueError(f"执行单包含不可执行指数: {', '.join(invalid_indices)}")
        execution_request = ExecutionRequest(
            source=request.source,
            indices=selected_indices,
            bands=request.bands,
            engine=request.engine or plan["engine"],
            block_size=request.block_size,
            priority=request.priority,
        )
        record = job_manager.submit(
            _to_raster_task(execution_request, selected_indices),
            request.priority,
        )
        return vegetation_agent.mark_confirmed(
            plan_id,
            record.id,
            {
                "indices": selected_indices,
                "engine": execution_request.engine,
                "blockSize": execution_request.block_size,
                "priority": request.priority,
            },
        )
    except (KeyError, ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/api/agent/plans/{plan_id}/confirm/stream")
async def stream_confirm_agent_plan(plan_id: str, request: ConfirmPlanRequest) -> StreamingResponse:
    """通过 SSE 提交已确认计划并推送任务直到终态。"""
    async def events():
        """执行 events 对应的领域操作并返回结构化结果。"""
        try:
            yield _sse("status", {"message": "正在校验执行单、影像路径和波段映射。"})
            plan = vegetation_agent.get_plan(plan_id)
            allowed_indices = {
                item["id"]
                for item in plan["recommendations"]
                if item["executable"]
            }
            selected_indices = request.indices or plan["selectedIndices"]
            invalid_indices = sorted(set(selected_indices) - allowed_indices)
            if invalid_indices:
                raise ValueError(f"执行单包含不可执行指数: {', '.join(invalid_indices)}")
            execution_request = ExecutionRequest(
                source=request.source,
                indices=selected_indices,
                bands=request.bands,
                engine=request.engine or plan["engine"],
                block_size=request.block_size,
                priority=request.priority,
            )
            task = _to_raster_task(execution_request, selected_indices)
            _validate_raster_task(task)
            yield _sse("status", {"message": "校验通过，正在提交异步计算任务。"})
            record = job_manager.submit(task, request.priority)
            confirmed = vegetation_agent.mark_confirmed(
                plan_id,
                record.id,
                {
                    "indices": selected_indices,
                    "engine": execution_request.engine,
                    "blockSize": execution_request.block_size,
                    "priority": request.priority,
                },
            )
            yield _sse("plan", confirmed)
            yield _sse("status", {"message": f"任务 {record.id} 已进入队列。"})

            while True:
                job = job_manager.get(record.id).public()
                yield _sse("job", job)
                if job["status"] in {"successful", "failed", "dismissed"}:
                    if job["status"] == "successful":
                        yield _sse("result", job.get("result") or {})
                        yield _sse("done", {"message": "任务完成，结果已生成。"})
                    else:
                        yield _sse(
                            "error",
                            {
                                "message": job.get("error") or job.get("message") or "任务执行失败",
                                "job": job,
                            },
                        )
                    break
                await asyncio.sleep(0.8)
        except Exception as error:  # noqa: BLE001 - 流式边界需要把失败写回客户端
            yield _sse("error", {"message": str(error)})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/api/agent/interpret-results")
async def interpret_agent_results(request: AgentResultInterpretRequest) -> dict[str, Any]:
    """执行 interpret_agent_results 对应的领域操作并返回结构化结果。"""
    return await vegetation_agent.interpret_results(
        request.products,
        request.user_goal,
        request.llm,
        request.session_id,
    )


@router.get("/api/agent/sessions/{session_id}/events")
def get_agent_session_events(session_id: str) -> dict[str, Any]:
    """执行 get_agent_session_events 对应的领域操作并返回结构化结果。"""
    return {"items": vegetation_agent.get_session_events(session_id)}


@router.post("/api/agent/knowledge", status_code=status.HTTP_201_CREATED)
def import_agent_knowledge(request: AgentKnowledgeImportRequest) -> dict[str, Any]:
    """执行 import_agent_knowledge 对应的领域操作并返回结构化结果。"""
    try:
        document = save_knowledge_document(request.model_dump(by_alias=True))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return document


@router.post("/api/indices/custom", status_code=status.HTTP_201_CREATED)
def create_custom_index(request: AgentCustomIndexRequest) -> dict[str, Any]:
    """执行 create_custom_index 对应的领域操作并返回结构化结果。"""
    try:
        return register_custom_index(request.model_dump(by_alias=True))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/api/recipes")
def list_recipes() -> dict[str, Any]:
    """执行 list_recipes 对应的领域操作并返回结构化结果。"""
    return {"items": vegetation_agent.recipes() + list(custom_recipes.values())}


@router.post("/api/recipes", status_code=status.HTTP_201_CREATED)
def create_recipe(request: RecipeRequest) -> dict[str, Any]:
    """执行 create_recipe 对应的领域操作并返回结构化结果。"""
    for index_id in request.indices:
        try:
            get_index(index_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    recipe_id = uuid.uuid4().hex
    recipe = {"id": recipe_id, **request.model_dump()}
    custom_recipes[recipe_id] = recipe
    return recipe


@router.post("/api/formulas/validate")
def validate_formula(request: CustomFormulaRequest) -> dict[str, Any]:
    """执行 validate_formula 对应的领域操作并返回结构化结果。"""
    try:
        return validate_custom_expression(request.expression, request.allowed_bands)
    except (SyntaxError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/api/analysis/change")
def change_detection(request: ChangeDetectionRequest) -> dict[str, Any]:
    """执行 change_detection 对应的领域操作并返回结构化结果。"""
    try:
        return detect_change(
            request.before_path,
            request.after_path,
            request.output_path,
            request.decrease_threshold,
            request.increase_threshold,
        )
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/api/analysis/zonal-statistics")
def zonal_statistics(request: ZonalStatisticsRequest) -> dict[str, Any]:
    """执行 zonal_statistics 对应的领域操作并返回结构化结果。"""
    try:
        return calculate_zonal_statistics(request.raster_path, request.geojson)
    except (KeyError, OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/api/benchmarks/engines")
def engine_benchmarks() -> dict[str, Any]:
    """执行 engine_benchmarks 对应的领域操作并返回结构化结果。"""
    return {
        "thresholds": {
            "numpyMaxPixels": 2_000_000,
            "torchMinPixels": 20_000_000,
            "torchMinIndices": 4,
        },
        "note": "实际基准需在目标机器执行backend/scripts/benchmark.py生成。",
    }


@router.get("/api/system/capabilities")
def capabilities() -> dict[str, Any]:
    """执行 capabilities 对应的领域操作并返回结构化结果。"""
    custom_count = max(len(INDEX_REGISTRY) - CORE_INDEX_COUNT, 0)
    return {
        "cuda": has_cuda(),
        "engines": ["numpy", "joblib", "torch"],
        "indexCount": CORE_INDEX_COUNT,
        "totalIndexCount": len(INDEX_REGISTRY),
        "customIndexCount": custom_count,
        "customIndexStorage": "postgresql" if is_enabled() else "memory",
        "agentSessionStorage": "postgresql" if is_agent_session_store_enabled() else "memory",
        "agentKnowledgeStorage": "postgresql" if is_agent_knowledge_store_enabled() else "memory",
        "asyncJobs": True,
        "objectStorage": "minio",
        "agentMode": "langchain+rag+web-search+rules",
    }


@router.get("/api/system/taskbook-coverage")
def taskbook_coverage() -> dict[str, Any]:
    """执行 taskbook_coverage 对应的领域操作并返回结构化结果。"""
    items = [
        _coverage(
            "35种植被指数",
            "covered",
            "app/core/indices.py",
            "内置30个任务书指数，并补齐5个旧服务兼容指数",
        ),
        _coverage(
            "Rasterio分块窗口计算",
            "covered",
            "app/services/raster_pipeline.py",
            "按窗口读取、计算和写入",
        ),
        _coverage("NumPy引擎", "covered", "app/engines/numpy_engine.py", "默认同步/小影像引擎"),
        _coverage("Joblib并行引擎", "covered", "app/engines/joblib_engine.py", "CPU并行计算"),
        _coverage("PyTorch CUDA引擎", "covered", "app/engines/torch_engine.py", "CUDA不可用时回退"),
        _coverage("自动引擎选择", "covered", "app/services/planner.py", "按尺寸、指数数和CUDA选择"),
        _coverage("OGC API - Processes", "covered", "app/api/routes.py", "/processes与/jobs接口"),
        _coverage(
            "pygeoapi处理器",
            "covered",
            "app/pygeoapi_processor.py",
            "SpectralIndexProcessor",
        ),
        _coverage("同步执行", "covered", "app/api/routes.py", "POST /processes/{id}/execution"),
        _coverage("异步执行", "covered", "app/services/jobs.py", "Prefer: respond-async与后台任务"),
        _coverage("取消任务", "covered", "app/api/routes.py", "DELETE /jobs/{job_id}"),
        _coverage("Celery + Redis", "covered", "app/celery_app.py", "部署模式任务队列"),
        _coverage("MinIO存储", "covered", "app/services/assets.py", "上传输入与结果对象"),
        _coverage("Nacos服务发现", "covered", "app/services/nacos.py", "API服务注册"),
        _coverage("Traefik网关", "covered", "infra/traefik/traefik.yml", "网关配置"),
        _coverage("Docker Compose", "covered", "compose.yml", "三服务、三Worker及基础设施"),
        _coverage("Vue 3前端", "covered", "frontend/src/App.vue", "遥感工作台"),
        _coverage(
            "GeoTIFF上传与检查",
            "covered",
            "frontend/src/components/AssetToolbar.vue",
            "上传和元数据检查",
        ),
        _coverage(
            "指数实验室",
            "covered",
            "frontend/src/components/IndexCatalog.vue",
            "指数浏览和检索",
        ),
        _coverage(
            "任务中心",
            "covered",
            "frontend/src/components/JobProgressPanel.vue",
            "轮询、结果、取消",
        ),
        _coverage(
            "地图结果工作台",
            "covered",
            "frontend/src/components/MapWorkspace.vue",
            "地图叠加和透明度",
        ),
        _coverage(
            "统计图表",
            "covered",
            "frontend/src/components/StatisticsDashboard.vue",
            "直方图和统计卡片",
        ),
        _coverage(
            "变化检测",
            "covered",
            "app/services/advanced_analysis.py",
            "/api/analysis/change",
        ),
        _coverage(
            "区域统计",
            "covered",
            "app/services/advanced_analysis.py",
            "/api/analysis/zonal-statistics",
        ),
        _coverage("自定义公式", "covered", "app/services/advanced_analysis.py", "AST白名单校验"),
        _coverage("分析配方", "covered", "app/api/routes.py", "/api/recipes"),
        _coverage(
            "可复现实验清单",
            "covered",
            "app/services/raster_pipeline.py",
            "manifest.json含哈希和环境",
        ),
        _coverage(
            "智能分析代理",
            "covered",
            "app/services/agent.py",
            "规则+LangChain+RAG+网络检索",
        ),
        _coverage(
            "PostgreSQL自定义指数",
            "covered",
            "app/services/custom_index_store.py",
            "自定义指数持久化",
        ),
        _coverage("基准测试", "covered", "scripts/benchmark.py", "多引擎误差与耗时微基准"),
    ]
    summary = {
        "covered": sum(1 for item in items if item["status"] == "covered"),
        "partial": sum(1 for item in items if item["status"] == "partial"),
        "missing": sum(1 for item in items if item["status"] == "missing"),
    }
    return {"summary": summary, "items": items}


def _coverage(requirement: str, status: str, location: str, evidence: str) -> dict[str, str]:
    """完成模块内部的 coverage 辅助处理。"""
    return {
        "requirement": requirement,
        "status": status,
        "location": location,
        "evidence": evidence,
    }


def _to_raster_task(request: ExecutionRequest, indices: list[str]) -> RasterTask:
    """完成模块内部的 to_raster_task 辅助处理。"""
    source = resolve_source(request.source.object_key, request.source.local_path)
    output_dir = settings.data_dir / "outputs" / uuid.uuid4().hex
    return RasterTask(
        source_path=str(source),
        output_dir=str(output_dir),
        indices=indices,
        bands=request.bands,
        engine=request.engine,
        block_size=request.block_size,
        parameters=request.parameters,
        preview=request.preview,
        statistics=request.statistics,
    )


def _validate_raster_task(task: RasterTask) -> None:
    """完成模块内部的 validate_raster_task 辅助处理。"""
    import rasterio

    definitions = [get_index(index_id) for index_id in task.indices]
    required_bands = sorted({band for item in definitions for band in item.required_bands})
    missing_mapping = sorted(set(required_bands) - task.bands.keys())
    if missing_mapping:
        raise ValueError(f"缺少逻辑波段映射: {', '.join(missing_mapping)}")
    with rasterio.open(task.source_path) as source:
        invalid_numbers = [
            task.bands[logical_name]
            for logical_name in required_bands
            if task.bands[logical_name] < 1 or task.bands[logical_name] > source.count
        ]
    if invalid_numbers:
        raise ValueError(f"波段号超出影像范围: {invalid_numbers}")


def _sse(event: str, data: dict[str, Any]) -> str:
    """完成模块内部的 sse 辅助处理。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
