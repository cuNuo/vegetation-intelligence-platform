# backend/tests/test_agent.py
# 文件说明：Agent 推荐、确认、RAG 和知识隔离测试。
# 主要职责：构造可重复数据并验证业务边界和回归行为。
# 对外入口：pytest fixture 与 test_* 用例。
# 依赖边界：隔离数据库、MinIO 和外部 LLM。

import asyncio

import pytest

from app.core.indices import INDEX_REGISTRY
from app.services.agent import vegetation_agent
from app.services.agent_knowledge_store import (
    delete_knowledge_documents_by_source,
    save_knowledge_document,
)
from app.services.agent_tools import interpret_products


def test_agent_recommends_growth_workflow() -> None:
    """验证 agent recommends growth workflow 场景的行为和回归边界。"""
    plan = asyncio.run(
        vegetation_agent.create_plan(
            "我想看这片农田哪些区域长势不好",
            ["blue", "green", "red", "nir"],
            5000,
            5000,
        )
    )
    assert plan["intent"] == "growth"
    assert plan["selectedIndices"] == ["ndvi", "evi", "gndvi"]
    assert plan["requiresConfirmation"] is True
    assert plan["canExecute"] is True
    assert plan["sessionId"]
    assert [event["eventType"] for event in plan["conversation"]] == ["question", "plan"]


def test_agent_blocks_indices_with_missing_bands() -> None:
    """验证 agent blocks indices with missing bands 场景的行为和回归边界。"""
    plan = asyncio.run(
        vegetation_agent.create_plan(
            "分析叶绿素和红边变化",
            ["red", "nir"],
        )
    )
    assert "gndvi" not in plan["selectedIndices"]
    assert any(item["missingBands"] for item in plan["recommendations"])


def test_agent_requires_confirmation_before_execution() -> None:
    """验证 agent requires confirmation before execution 场景的行为和回归边界。"""
    plan = asyncio.run(
        vegetation_agent.create_plan("分析稀疏植被", ["blue", "red", "nir", "swir1"])
    )
    assert plan["status"] == "awaiting_confirmation"
    assert "jobId" not in plan


def test_agent_interpretation_appends_session_event() -> None:
    """验证 agent interpretation appends session event 场景的行为和回归边界。"""
    plan = asyncio.run(
        vegetation_agent.create_plan(
            "我想看这片农田哪些区域长势不好",
            ["blue", "green", "red", "nir"],
        )
    )
    result = asyncio.run(
        vegetation_agent.interpret_results(
            [
                {
                    "index": "ndvi",
                    "name": "NDVI",
                    "statistics": {
                        "validPixels": 100,
                        "minimum": 0.1,
                        "maximum": 0.8,
                        "mean": 0.32,
                        "median": 0.3,
                        "standardDeviation": 0.12,
                    },
                }
            ],
            "长势诊断",
            session_id=plan["sessionId"],
        )
    )
    assert result["conversation"][-1]["eventType"] == "interpretation"


def test_agent_interprets_ndmi_and_msi_with_distinct_water_semantics() -> None:
    """验证 NDMI 与 MSI 不再共用同一套水分判断语义。"""
    result = interpret_products(
        [
            {
                "index": "ndmi",
                "statistics": {
                    "mean": 0.82,
                    "minimum": 0.19,
                    "maximum": 0.95,
                    "standardDeviation": 0.09,
                },
            },
            {
                "index": "msi",
                "statistics": {
                    "mean": 0.86,
                    "minimum": 0.40,
                    "maximum": 1.10,
                    "standardDeviation": 0.04,
                },
            },
        ],
        "水分胁迫判读",
    )

    details = " ".join(item["detail"] for item in result["insights"])
    assert "NDMI 水分信号异常偏高" in details
    assert "MSI 越高通常表示水分胁迫越强" in details
    assert "不宜直接判定为水分稳定" in details
    assert result["nextActions"] and isinstance(result["nextActions"][0], str)


def test_agent_normalizes_llm_next_actions_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 LLM 返回字符串 nextActions 时后端规整为列表，防止前端逐字渲染。"""
    async def fake_invoke_langchain(*_args, **_kwargs) -> str:
        return '{"summary":"模型摘要","nextActions":"复核地块边界和原始影像"}'

    monkeypatch.setattr(vegetation_agent, "_invoke_langchain", fake_invoke_langchain)
    result = asyncio.run(
        vegetation_agent.interpret_results(
            [
                {
                    "index": "ndvi",
                    "statistics": {"mean": 0.62, "standardDeviation": 0.05},
                }
            ],
            "长势诊断",
            llm_config={
                "baseUrl": "https://example.invalid/v1",
                "token": "test-token",
                "model": "test-model",
            },
        )
    )

    assert result["nextActions"] == ["复核地块边界和原始影像"]


def test_agent_exposes_trace_and_rag_hits() -> None:
    """验证 agent exposes trace and rag hits 场景的行为和回归边界。"""
    plan = asyncio.run(
        vegetation_agent.create_plan(
            "干旱水分胁迫应该看哪些指数",
            ["blue", "green", "red", "nir", "swir1"],
            enable_web_search=False,
        )
    )
    assert plan["agentMode"] == "langchain+rag+web-search+rules"
    assert plan["knowledgeHits"]
    assert any(step["id"] == "rag" for step in plan["trace"])


def test_agent_rag_uses_imported_knowledge_document() -> None:
    """验证 agent rag uses imported knowledge document 场景的行为和回归边界。"""
    delete_knowledge_documents_by_source("pytest-knowledge")
    try:
        save_knowledge_document(
            {
                "title": "根腐病水分胁迫判读",
                "content": "根腐病排查时需要联合NDMI水分指数和NDVI长势指数，重点看灌溉异常区域。",
                "source": "pytest-knowledge",
            }
        )
        plan = asyncio.run(
            vegetation_agent.create_plan(
                "根腐病和灌溉异常应该看什么指数",
                ["blue", "green", "red", "nir", "swir1"],
                enable_web_search=False,
            )
        )
        assert any(hit["source"].startswith("knowledge-base") for hit in plan["knowledgeHits"])
    finally:
        delete_knowledge_documents_by_source("pytest-knowledge")


def test_agent_rag_does_not_inject_unmentioned_specific_disease() -> None:
    """验证 agent rag does not inject unmentioned specific disease 场景的行为和回归边界。"""
    delete_knowledge_documents_by_source("pytest-knowledge")
    try:
        save_knowledge_document(
            {
                "title": "根腐病水分胁迫判读",
                "content": "根腐病排查时需要联合NDMI水分指数和NDVI长势指数。",
                "source": "pytest-knowledge",
            }
        )
        plan = asyncio.run(
            vegetation_agent.create_plan(
                "我想分析这片地的植被长势",
                ["blue", "green", "red", "nir"],
                enable_web_search=False,
            )
        )
        assert all("根腐病" not in hit["title"] for hit in plan["knowledgeHits"])
        assert all("根腐病" not in hit["content"] for hit in plan["knowledgeHits"])
    finally:
        delete_knowledge_documents_by_source("pytest-knowledge")


def test_agent_can_register_runtime_custom_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 agent can register runtime custom index 场景的行为和回归边界。"""
    monkeypatch.setattr("app.services.agent_tools.save_custom_index", lambda _spec: False)
    try:
        plan = asyncio.run(
            vegetation_agent.create_plan(
                "我要新增一个近红外红光差异指数并执行",
                ["red", "nir"],
                enable_web_search=False,
                custom_index={
                    "id": "demo_diff",
                    "name": "演示差异指数",
                    "expression": "nir - red",
                    "description": "用于演示运行期新增指数。",
                },
            )
        )
        assert plan["customIndex"]["id"] == "demo_diff"
        assert plan["customIndex"]["storage"] in {"memory", "postgresql"}
        assert plan["selectedIndices"][0] == "demo_diff"
    finally:
        INDEX_REGISTRY.pop("demo_diff", None)
