# backend/app/services/agent.py
# 文件说明：植被分析 Agent 的意图识别、方案生成、确认与结果解读。
"""可解释、需确认的植被分析方案智能体。"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.indices import INDEX_REGISTRY
from app.services.agent_session_store import append_event, create_session, list_events
from app.services.agent_tools import (
    build_process_steps,
    interpret_products,
    register_custom_index,
    search_index_knowledge,
    search_web_knowledge,
)
from app.services.planner import ExecutionPlanner
from app.settings import settings


@dataclass(frozen=True, slots=True)
class IntentRule:
    intent: str
    title: str
    keywords: tuple[str, ...]
    indices: tuple[str, ...]
    description: str
    warnings: tuple[str, ...]


RULES = (
    IntentRule(
        "growth",
        "作物长势空间差异分析",
        ("长势", "健康", "不好", "覆盖", "生物量", "农田"),
        ("ndvi", "evi", "gndvi"),
        "综合比较植被覆盖、高生物量响应和叶绿素差异。",
        ("高覆盖区NDVI可能饱和", "应先进行云和阴影掩膜"),
    ),
    IntentRule(
        "sparse",
        "稀疏植被与裸土背景分析",
        ("稀疏", "苗期", "裸土", "荒漠", "土壤"),
        ("savi", "osavi", "msavi", "bsi"),
        "使用土壤调节指数降低裸土背景干扰。",
        ("土壤湿度和颜色差异仍可能影响结果",),
    ),
    IntentRule(
        "chlorophyll",
        "叶绿素与氮素状态分析",
        ("叶绿素", "氮", "营养", "红边", "黄化"),
        ("gndvi", "ndre", "gci", "reci"),
        "利用绿色和红边波段提高对叶绿素变化的敏感性。",
        ("NDRE和RECI要求红边波段",),
    ),
    IntentRule(
        "water_stress",
        "植被水分胁迫辅助分析",
        ("干旱", "水分", "缺水", "胁迫", "灌溉"),
        ("ndvi", "ndmi", "msi"),
        "结合植被活力和短波红外水分响应识别潜在胁迫。",
        ("NDMI和MSI要求短波红外波段", "结论需结合气象和土壤数据"),
    ),
    IntentRule(
        "change",
        "多时相植被变化监测",
        ("变化", "两期", "前后", "退化", "恢复", "火灾"),
        ("ndvi", "evi", "nbr"),
        "对两期同源、同尺度数据进行指数差值和变化分类。",
        ("两期影像必须完成配准与辐射一致化",),
    ),
)


class VegetationAgent:
    def __init__(self) -> None:
        self._plans: dict[str, dict[str, Any]] = {}

    async def create_plan(
        self,
        message: str,
        available_bands: list[str],
        width: int | None = None,
        height: int | None = None,
        llm_config: Any | None = None,
        enable_web_search: bool = True,
        external_documents: list[dict[str, str]] | None = None,
        custom_index: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        session_id = session_id or create_session(message)
        append_event(
            session_id,
            "user",
            "question",
            message,
            {
                "availableBands": available_bands,
                "rasterWidth": width,
                "rasterHeight": height,
            },
        )
        trace = [
            {
                "id": "question",
                "title": "接收问题",
                "status": "done",
                "detail": "已读取用户问题、当前可用波段和影像规模信息。",
            }
        ]
        knowledge_hits = search_index_knowledge(message, external_documents)
        trace.append(
            {
                "id": "rag",
                "title": "RAG检索指数知识",
                "status": "done",
                "detail": f"已召回 {len(knowledge_hits)} 条内置/外部指数知识。",
            }
        )
        web_hits: list[dict[str, Any]] = []
        if enable_web_search:
            web_hits = await search_web_knowledge(message)
            trace.append(
                {
                    "id": "web_search",
                    "title": "网络检索适用场景",
                    "status": "done" if web_hits else "warning",
                    "detail": (
                        f"已获取 {len(web_hits)} 条网络资料。"
                        if web_hits
                        else "网络检索未返回可用结果，已降级使用本地指数知识。"
                    ),
                }
            )
        custom_index_metadata = None
        if custom_index:
            custom_index_metadata = register_custom_index(custom_index)
            available_bands = sorted(
                set(available_bands) | set(custom_index_metadata["requiredBands"])
            )
            trace.append(
                {
                    "id": "custom_index",
                    "title": "注册自定义指数",
                    "status": "done",
                    "detail": f"已新增 {custom_index_metadata['id'].upper()} 并完成表达式试算。",
                }
            )

        llm_result = await self._classify_with_llm(message, llm_config, knowledge_hits + web_hits)
        llm_intent = llm_result.get("intent")
        rule = self._match_rule(message, llm_intent)
        available = set(available_bands)
        recommendations = []
        executable_indices = []
        candidate_indices = list(rule.indices)
        if custom_index_metadata:
            candidate_indices.insert(0, custom_index_metadata["id"])
        for index_id in candidate_indices:
            definition = INDEX_REGISTRY[index_id]
            missing = sorted(set(definition.required_bands) - available) if available else []
            is_executable = not missing
            if is_executable:
                executable_indices.append(index_id)
            recommendations.append(
                {
                    **definition.public_metadata(),
                    "executable": is_executable,
                    "missingBands": missing,
                    "reason": self._recommendation_reason(definition.recommendation_tags, message),
                }
            )

        planner = ExecutionPlanner()
        decision = planner.choose(
            width or 5000,
            height or 5000,
            max(len(available), 3),
            max(len(executable_indices), 1),
        )
        plan_id = uuid.uuid4().hex
        plan = {
            "id": plan_id,
            "status": "awaiting_confirmation",
            "intent": rule.intent,
            "title": rule.title,
            "summary": rule.description,
            "recommendations": recommendations,
            "selectedIndices": executable_indices,
            "engine": decision.selected,
            "engineReason": decision.reason,
            "estimatedMemoryMb": round(decision.estimated_memory_mb, 2),
            "suggestedBlockSize": 1024,
            "suggestedColorRamp": "soil-to-canopy",
            "suggestedThresholds": self._thresholds(rule.intent),
            "warnings": list(rule.warnings),
            "requiresConfirmation": True,
            "canExecute": bool(executable_indices),
            "trace": trace,
            "processSteps": [],
            "knowledgeHits": knowledge_hits,
            "webHits": web_hits,
            "llmStatus": llm_result["status"],
            "llmProvider": llm_result["provider"],
            "llmMessage": llm_result["message"],
            "customIndex": custom_index_metadata,
            "agentMode": "langchain+rag+web-search+rules",
            "sessionId": session_id,
        }
        if not executable_indices:
            plan["warnings"].append("当前波段条件不足，禁止提交执行")
        if llm_result["status"] != "used":
            plan["warnings"].append(llm_result["message"])
        plan["processSteps"] = build_process_steps(plan)
        plan["trace"].extend(plan["processSteps"])
        self._plans[plan_id] = plan
        append_event(
            session_id,
            "assistant",
            "plan",
            f"建议执行“{plan['title']}”，推荐{len(executable_indices)}个可执行指数。",
            {
                "planId": plan_id,
                "intent": plan["intent"],
                "selectedIndices": plan["selectedIndices"],
                "engine": plan["engine"],
                "llmStatus": plan["llmStatus"],
                "trace": plan["trace"],
                "warnings": plan["warnings"],
            },
        )
        plan["conversation"] = self.get_session_events(session_id)
        return plan

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        try:
            return self._plans[plan_id]
        except KeyError as error:
            raise KeyError(f"方案不存在: {plan_id}") from error

    def mark_confirmed(
        self,
        plan_id: str,
        job_id: str,
        execution_sheet: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = self.get_plan(plan_id)
        if not plan["canExecute"]:
            raise ValueError("方案缺少必需波段，不能执行")
        if execution_sheet:
            plan["selectedIndices"] = execution_sheet["indices"]
            plan["engine"] = execution_sheet["engine"]
            plan["suggestedBlockSize"] = execution_sheet["blockSize"]
            plan["priority"] = execution_sheet["priority"]
        plan["status"] = "confirmed"
        plan["jobId"] = job_id
        plan["trace"].append(
            {
                "id": "execution_submitted",
                "title": "提交异步计算",
                "status": "running",
                "detail": f"已通过确认门提交任务 {job_id}，前端将轮询队列状态。",
            }
        )
        append_event(
            plan["sessionId"],
            "assistant",
            "execution",
            f"已提交计算任务 {job_id}。",
            {
                "planId": plan_id,
                "jobId": job_id,
                "executionSheet": execution_sheet or {},
                "trace": plan["trace"],
            },
        )
        plan["conversation"] = self.get_session_events(plan["sessionId"])
        return plan

    def get_session_events(self, session_id: str) -> list[dict[str, Any]]:
        return list_events(session_id)

    @staticmethod
    def _match_rule(message: str, llm_intent: str | None) -> IntentRule:
        if llm_intent:
            for rule in RULES:
                if rule.intent == llm_intent:
                    return rule
        scores = {
            rule.intent: sum(1 for keyword in rule.keywords if keyword in message) for rule in RULES
        }
        selected_intent = max(scores, key=scores.get)
        if scores[selected_intent] == 0:
            selected_intent = "growth"
        return next(rule for rule in RULES if rule.intent == selected_intent)

    async def _classify_with_llm(
        self,
        message: str,
        llm_config: Any | None,
        knowledge_hits: list[dict[str, Any]],
    ) -> dict[str, Any]:
        config = self._normalize_llm_config(llm_config)
        if not config["base_url"] or not config["token"]:
            return {
                "intent": None,
                "status": "skipped",
                "provider": config["provider"],
                "message": "未配置token/base_url，已使用规则引擎完成方案生成。",
            }
        schema = {"allowed": [rule.intent for rule in RULES]}
        system_prompt = (
            "你是遥感植被指数智能体，只返回JSON。字段intent只能取："
            + ",".join(schema["allowed"])
            + "。可选字段reason用一句中文说明依据。RAG资料仅用于辅助分类；"
            "禁止引入用户问题中未明确提及的具体病害、虫害、灾害或成因，"
            "若资料与问题不直接相关必须忽略。"
        )
        rag_context = "\n".join(
            f"- {hit['title']}: {hit['content']} 来源={hit['source']}" for hit in knowledge_hits[:8]
        )
        try:
            content = await self._invoke_langchain(
                config,
                [
                    ("system", system_prompt),
                    ("user", f"问题：{message}\n\nRAG资料：\n{rag_context}"),
                ],
            )
            parsed = json.loads(re.search(r"\{.*\}", content, re.S).group())
            intent = parsed.get("intent")
            return {
                "intent": intent if intent in schema["allowed"] else None,
                "status": "used",
                "provider": config["provider"],
                "message": parsed.get("reason") or "LangChain已参与意图判断。",
            }
        except (ImportError, KeyError, ValueError, AttributeError, json.JSONDecodeError) as error:
            return {
                "intent": None,
                "status": "failed",
                "provider": config["provider"],
                "message": f"LangChain调用失败，已降级规则引擎: {error}",
            }

    @staticmethod
    def _recommendation_reason(tags: tuple[str, ...], message: str) -> str:
        matched = [tag for tag in tags if tag in message]
        return f"与需求中的{matched[0]}直接相关" if matched else f"适用于{'、'.join(tags[:2])}"

    @staticmethod
    def _thresholds(intent: str) -> list[dict[str, Any]]:
        if intent == "growth":
            return [
                {"label": "低活力候选区", "maximum": 0.25},
                {"label": "中等活力", "minimum": 0.25, "maximum": 0.55},
                {"label": "高活力", "minimum": 0.55},
            ]
        if intent == "change":
            return [
                {"label": "明显退化", "maximum": -0.2},
                {"label": "基本稳定", "minimum": -0.2, "maximum": 0.2},
                {"label": "明显恢复", "minimum": 0.2},
            ]
        return []

    def recipes(self) -> list[dict[str, Any]]:
        return [
            {
                "id": rule.intent,
                "name": rule.title,
                "indices": list(rule.indices),
                "description": rule.description,
            }
            for rule in RULES
        ]

    async def interpret_results(
        self,
        products: list[dict[str, Any]],
        user_goal: str = "",
        llm_config: Any | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        base = interpret_products(products, user_goal)
        config = self._normalize_llm_config(llm_config)
        if not config["base_url"] or not config["token"]:
            base["llmStatus"] = "skipped"
            base["trace"] = [
                {"id": "statistics", "title": "读取统计信息", "status": "done"},
                {"id": "rules", "title": "规则解释", "status": "done"},
            ]
            if session_id:
                append_event(
                    session_id,
                    "assistant",
                    "interpretation",
                    base["summary"],
                    {"trace": base["trace"], "llmStatus": base["llmStatus"]},
                )
                base["conversation"] = self.get_session_events(session_id)
            return base
        try:
            content = await self._invoke_langchain(
                config,
                [
                    ("system", "你是农业遥感分析师。只返回JSON，字段summary、nextActions。"),
                    (
                        "user",
                        json.dumps(
                            {"goal": user_goal, "statistics": products},
                            ensure_ascii=False,
                        ),
                    ),
                ],
            )
            parsed = json.loads(re.search(r"\{.*\}", content, re.S).group())
            base["summary"] = parsed.get("summary") or base["summary"]
            base["nextActions"] = parsed.get("nextActions") or base["nextActions"]
            base["llmStatus"] = "used"
        except (ImportError, KeyError, ValueError, AttributeError, json.JSONDecodeError) as error:
            base["llmStatus"] = "failed"
            base["llmMessage"] = f"LangChain统计解读失败，已保留规则建议: {error}"
        base["trace"] = [
            {"id": "statistics", "title": "读取统计信息", "status": "done"},
            {"id": "interpret", "title": "生成农学建议", "status": "done"},
        ]
        if session_id:
            append_event(
                session_id,
                "assistant",
                "interpretation",
                base["summary"],
                {
                    "trace": base["trace"],
                    "llmStatus": base["llmStatus"],
                    "insightCount": len(base.get("insights", [])),
                },
            )
            base["conversation"] = self.get_session_events(session_id)
        return base

    @staticmethod
    async def _invoke_langchain(config: dict[str, Any], messages: list[tuple[str, str]]) -> str:
        if config["provider"] == "anthropic":
            from langchain_anthropic import ChatAnthropic

            kwargs = {
                "model": config["model"],
                "anthropic_api_key": config["token"],
                "temperature": config["temperature"],
            }
            if config["base_url"]:
                kwargs["base_url"] = config["base_url"]
            model = ChatAnthropic(**kwargs)
        else:
            from langchain_openai import ChatOpenAI

            model = ChatOpenAI(
                model=config["model"],
                api_key=config["token"],
                base_url=config["base_url"],
                temperature=config["temperature"],
            )
        response = await model.ainvoke(messages)
        content = response.content
        if isinstance(content, list):
            return "\n".join(str(item) for item in content)
        return str(content)

    @staticmethod
    def _normalize_llm_config(llm_config: Any | None) -> dict[str, Any]:
        if llm_config is None:
            return {
                "provider": "openai-compatible",
                "base_url": settings.openai_base_url,
                "token": settings.openai_api_key,
                "model": settings.openai_model,
                "temperature": 0,
            }
        data = (
            llm_config.model_dump(by_alias=False)
            if hasattr(llm_config, "model_dump")
            else dict(llm_config)
        )
        return {
            "provider": data.get("provider") or "openai-compatible",
            "base_url": data.get("base_url") or data.get("baseUrl"),
            "token": data.get("token"),
            "model": data.get("model") or settings.openai_model,
            "temperature": data.get("temperature", 0),
        }


vegetation_agent = VegetationAgent()
