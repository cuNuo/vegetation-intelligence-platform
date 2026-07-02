# backend/app/services/agent_tools.py
# 文件说明：Agent 指数知识、动态注册和结果解释工具。
# 主要职责：检索知识、验证指数、构造追踪并解释统计。
# 对外入口：search_index_knowledge、register_custom_index、interpret_products。
# 依赖边界：动态表达式必须白名单验证。

"""智能体工具：指数检索、运行期指数注册与统计解释。"""

from __future__ import annotations

import ast
import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import numpy as np

from app.core.indices import COMMON_LIMITATIONS, INDEX_REGISTRY, IndexDefinition, safe_divide
from app.services.advanced_analysis import validate_custom_expression
from app.services.agent_knowledge_store import search_persisted_knowledge
from app.services.custom_index_store import load_custom_indices, save_custom_index

ALLOWED_BANDS = ("blue", "green", "red", "red_edge", "nir", "swir1", "swir2")
COMMON_AGRONOMY_KNOWLEDGE = (
    (
        "通用作物长势判读",
        "长势 健康 覆盖 生物量 农田",
        "长势判读优先联合NDVI、EVI和GNDVI；NDVI适合覆盖度，EVI缓解高覆盖饱和，"
        "GNDVI补充叶绿素和氮素响应。结论应结合云阴影掩膜、地块边界和历史同期。",
    ),
    (
        "叶绿素与氮素状态判读",
        "叶绿素 氮素 黄化 红边 营养",
        "叶绿素和氮素状态可联合GNDVI、NDRE、GCI和RECI；有红边波段时优先使用NDRE/RECI，"
        "并结合生育期、施肥记录和叶片实测，避免把土壤背景或阴影误判为缺氮。",
    ),
    (
        "水分与干旱胁迫判读",
        "水分 干旱 缺水 灌溉 胁迫",
        "水分胁迫可联合NDMI、MSI与NDVI；NDMI/MSI依赖SWIR，NDVI用于区分水分信号与整体长势下降。"
        "需要叠加近期降雨、灌溉、土壤含水量和温度资料，不能仅凭指数诊断具体病害。",
    ),
    (
        "积水与涝害辅助判读",
        "积水 涝害 过湿 排水",
        "积水或过湿区域常表现为水分指数异常并伴随长势下降，可联合NDMI、NDVI和地形低洼区分析；"
        "需排除水体、阴影和灌溉时相差异，并通过现场或排水记录确认。",
    ),
    (
        "稀疏植被与裸土背景",
        "稀疏 裸土 苗期 土壤 荒漠",
        "稀疏植被和苗期优先使用SAVI、OSAVI、MSAVI降低土壤背景影响；"
        "可结合BSI识别裸土，但土壤湿度、颜色和耕作痕迹仍会改变结果。",
    ),
    (
        "盐碱与土壤胁迫辅助判读",
        "盐碱 盐渍化 土壤 胁迫",
        "盐碱胁迫可表现为NDVI/SAVI降低和裸土特征增强，建议联合植被指数、BSI、土壤采样和地块历史；"
        "遥感异常不能直接区分盐碱、缺水、缺肥或病害。",
    ),
    (
        "倒伏与冠层结构异常",
        "倒伏 冠层 结构 风灾",
        "倒伏判读应结合指数变化、纹理、阴影方向和多时相对比；单一NDVI往往不足，"
        "需要高分辨率影像、地块边界及灾前影像辅助确认。",
    ),
    (
        "病虫害异常的遥感边界",
        "病害 虫害 病虫害 斑块 异常",
        "病虫害可能引起叶绿素、红边、水分和冠层结构异常，可联合NDRE、GNDVI、NDMI与NDVI筛查。"
        "遥感只能定位疑似异常区，不能在缺少用户病害信息和现场证据时诊断具体病名。",
    ),
    (
        "多时相变化监测",
        "变化 两期 前后 退化 恢复",
        "多时相监测应使用同传感器、同尺度、完成配准和辐射一致化的影像，比较NDVI/EVI/NDRE等指数差值；"
        "需区分物候变化、收割、云阴影和真实退化。",
    ),
)


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    """封装 KnowledgeHit 相关状态、约束和可复用行为。"""
    title: str
    content: str
    source: str
    score: float

    def public(self) -> dict[str, Any]:
        """执行 public 对应的领域操作并返回结构化结果。"""
        return {
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "score": round(self.score, 3),
        }


def search_index_knowledge(
    query: str,
    external_documents: list[dict[str, str]] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """在内置指数库和外部文档片段中做轻量RAG召回。"""
    terms = _tokenize(query)
    hits: list[KnowledgeHit] = []
    for title, keywords, content in COMMON_AGRONOMY_KNOWLEDGE:
        score = _score(terms, f"{title} {keywords} {content}")
        if score > 0:
            hits.append(
                KnowledgeHit(
                    title=title,
                    content=content,
                    source="built-in-agronomy",
                    score=score + 0.04,
                )
            )
    for definition in INDEX_REGISTRY.values():
        content = " ".join(
            [
                definition.name,
                definition.formula,
                definition.description,
                " ".join(definition.required_bands),
                " ".join(definition.categories),
                " ".join(definition.recommendation_tags),
                " ".join(definition.limitations),
            ]
        )
        score = _score(terms, content)
        if score > 0:
            hits.append(
                KnowledgeHit(
                    title=f"{definition.id.upper()} {definition.name}",
                    content=_definition_knowledge_content(definition),
                    source="index-registry",
                    score=score,
                )
            )
    for position, document in enumerate(external_documents or []):
        title = document.get("title") or f"外部资料 {position + 1}"
        content = document.get("content", "")
        score = _score(terms, f"{title} {content}") + 0.05
        if content and score > 0:
            hits.append(
                KnowledgeHit(title=title, content=content[:500], source="external", score=score)
            )
    for document in search_persisted_knowledge(query, limit=limit):
        hits.append(
            KnowledgeHit(
                title=document["title"],
                content=document["content"],
                source=document["source"],
                score=float(document["score"]),
            )
        )
    hits.sort(key=lambda item: item.score, reverse=True)
    return [hit.public() for hit in hits[:limit]]


def _definition_knowledge_content(definition: IndexDefinition) -> str:
    """把内置指数定义展开为 Agent 可校验的结构化知识。"""
    range_label = (
        f"{definition.expected_range[0]} 到 {definition.expected_range[1]}"
        if definition.expected_range
        else "未限定，需结合场景和统计分布解释"
    )
    return "；".join(
        [
            f"公式={definition.formula}",
            f"必需波段={', '.join(definition.required_bands)}",
            f"期望范围={range_label}",
            f"用途={definition.description}",
            f"推荐场景={', '.join(definition.recommendation_tags) or '未标注'}",
            f"限制={', '.join(definition.limitations) or '无'}",
        ]
    )


async def search_web_knowledge(query: str, limit: int = 4) -> list[dict[str, Any]]:
    """默认网络检索入口，用公开搜索结果补充指数适用场景。"""
    params = {"q": f"{query} vegetation index remote sensing use case", "kl": "wt-wt"}
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            response = await client.get("https://duckduckgo.com/html/", params=params)
            response.raise_for_status()
    except httpx.HTTPError:
        return []
    pattern = re.compile(
        r'class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
        r'class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        re.S,
    )
    hits = []
    for match in pattern.finditer(response.text):
        title = _clean_html(match.group("title"))
        snippet = _clean_html(match.group("snippet"))
        url = html.unescape(match.group("url"))
        if title and snippet:
            hits.append(
                {
                    "title": title,
                    "content": snippet[:500],
                    "source": url,
                    "score": 0.72,
                }
            )
        if len(hits) >= limit:
            break
    return hits


def register_custom_index(spec: dict[str, Any]) -> dict[str, Any]:
    """校验并注册运行期自定义指数，避免错误公式进入源码注册表。"""
    metadata = _register_custom_index_in_memory(spec, allow_replace=False)
    persisted = save_custom_index(
        {
            "id": metadata["id"],
            "name": metadata["name"],
            "expression": metadata["formula"],
            "description": metadata["description"],
            "expectedRange": metadata["expectedRange"],
            "categories": metadata["categories"],
            "recommendationTags": metadata["recommendationTags"],
            "limitations": metadata["limitations"],
        }
    )
    metadata["storage"] = "postgresql" if persisted else "memory"
    return metadata


def load_persisted_custom_indices() -> int:
    """执行 load_persisted_custom_indices 对应的领域操作并返回结构化结果。"""
    loaded = 0
    for spec in load_custom_indices():
        try:
            _register_custom_index_in_memory(spec, allow_replace=True)
            loaded += 1
        except ValueError:
            continue
    return loaded


def _register_custom_index_in_memory(
    spec: dict[str, Any],
    allow_replace: bool,
) -> dict[str, Any]:
    """完成模块内部的 register_custom_index_in_memory 辅助处理。"""
    index_id = _normalize_index_id(str(spec.get("id") or ""))
    if not index_id:
        raise ValueError("自定义指数必须提供id")
    if index_id in INDEX_REGISTRY and not allow_replace:
        raise ValueError(f"指数已存在: {index_id}")
    expression = str(spec.get("expression") or "").strip()
    if not expression:
        raise ValueError("自定义指数必须提供表达式")
    validation = validate_custom_expression(expression, list(ALLOWED_BANDS))
    required_bands = tuple(validation["requiredBands"])
    if not required_bands:
        raise ValueError("表达式必须至少引用一个波段")
    _probe_expression(expression, required_bands)
    definition = IndexDefinition(
        id=index_id,
        name=str(spec.get("name") or index_id.upper()),
        formula=validation["normalizedExpression"],
        required_bands=required_bands,
        expression=_build_expression(validation["normalizedExpression"]),
        description=str(spec.get("description") or "运行期新增自定义植被指数。"),
        expected_range=_expected_range(spec.get("expectedRange")),
        categories=tuple(spec.get("categories") or ("custom",)),
        recommendation_tags=tuple(spec.get("recommendationTags") or ("自定义指数",)),
        limitations=tuple(spec.get("limitations") or COMMON_LIMITATIONS),
    )
    INDEX_REGISTRY[index_id] = definition
    return definition.public_metadata()


def build_process_steps(plan: dict[str, Any]) -> list[dict[str, str]]:
    """生成面向演示的执行过程轨迹。"""
    steps = [
        ("understand", "理解问题", "已识别分析意图并召回相关指数知识。"),
        ("catalog", "检索指数库", f"已检查 {len(INDEX_REGISTRY)} 个指数的波段、公式和限制。"),
        ("validate", "校验可执行性", "已比对当前影像波段与候选指数必需波段。"),
        ("engine", "选择执行引擎", f"推荐使用 {plan['engine']}：{plan['engineReason']}"),
        ("confirm", "等待确认", "确认后才会提交 OGC Processes 异步任务。"),
    ]
    return [
        {"id": step_id, "title": title, "status": "done", "detail": detail}
        for step_id, title, detail in steps
    ]


def interpret_products(products: list[dict[str, Any]], user_goal: str = "") -> dict[str, Any]:
    """基于产品统计信息给出规则化农学建议。"""
    insights: list[dict[str, str]] = []
    index_ids: set[str] = set()
    for product in products:
        statistics = product.get("statistics") or {}
        index_id = str(product.get("index", "")).lower()
        index_ids.add(index_id)
        mean = statistics.get("mean")
        deviation = statistics.get("standardDeviation")
        if mean is None:
            insights.append(
                {
                    "title": f"{index_id.upper()} 暂无有效统计",
                    "severity": "warning",
                    "detail": "结果缺少有效像元，建议先检查 nodata、裁剪范围和波段映射。",
                }
            )
            continue
        severity, detail = _interpret_index(
            index_id,
            float(mean),
            _optional_float(deviation),
            _optional_float(statistics.get("minimum")),
            _optional_float(statistics.get("maximum")),
        )
        insights.append(
            {"title": f"{index_id.upper()} 均值 {mean:.3f}", "severity": severity, "detail": detail}
        )
    action = _next_action_from_context(index_ids, user_goal)
    return {
        "summary": _summary_from_insights(insights),
        "insights": insights,
        "nextActions": [action],
    }


def _build_expression(expression: str) -> Callable[[Any, dict[str, Any], dict[str, float]], Any]:
    """完成模块内部的 build_expression 辅助处理。"""
    tree = ast.parse(expression, mode="eval")
    code = compile(tree, "<runtime-index>", "eval")

    def calculate(xp: Any, bands: dict[str, Any], _parameters: dict[str, float]) -> Any:
        """校验所需波段、合并参数并调用统一公式表达式。"""
        functions = {
            "abs": xp.abs,
            "sqrt": xp.sqrt,
            "minimum": xp.minimum,
            "maximum": xp.maximum,
            "safe_divide": lambda numerator, denominator: safe_divide(xp, numerator, denominator),
        }
        return eval(code, {"__builtins__": {}}, {**functions, **bands})  # noqa: S307

    return calculate


def _probe_expression(expression: str, required_bands: tuple[str, ...]) -> None:
    """完成模块内部的 probe_expression 辅助处理。"""
    arrays = {band: np.array([[0.2, 0.6]], dtype=np.float32) for band in required_bands}
    result = _build_expression(expression)(np, arrays, {})
    array = np.asarray(result, dtype=np.float32)
    if array.shape != (1, 2) or not np.isfinite(array).all():
        raise ValueError("表达式试算失败，结果必须为有限数组")


def _expected_range(value: Any) -> tuple[float, float] | None:
    """完成模块内部的 expected_range 辅助处理。"""
    if not value:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (float(value[0]), float(value[1]))
    return None


def _normalize_index_id(value: str) -> str:
    """完成模块内部的 normalize_index_id 辅助处理。"""
    normalized = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
    return normalized[:40]


def _tokenize(value: str) -> set[str]:
    """完成模块内部的 tokenize 辅助处理。"""
    words = set(re.findall(r"[a-zA-Z0-9_]+", value.lower()))
    chinese_terms = {
        term
        for term in (
            "长势",
            "健康",
            "叶绿素",
            "水分",
            "干旱",
            "裸土",
            "稀疏",
            "变化",
            "火灾",
            "红边",
            "黄化",
            "氮素",
            "设施农业",
            "无人机",
            "rgb",
            "病虫害",
            "病害",
            "虫害",
            "灌溉",
            "积水",
            "涝害",
            "盐碱",
            "倒伏",
            "冠层",
        )
        if term in value.lower()
    }
    return words | chinese_terms


def _score(terms: set[str], content: str) -> float:
    """完成模块内部的 score 辅助处理。"""
    if not terms:
        return 0.0
    lowered = content.lower()
    matches = sum(1 for term in terms if term in lowered)
    return matches / max(len(terms), 1)


def _clean_html(value: str) -> str:
    """完成模块内部的 clean_html 辅助处理。"""
    text = re.sub(r"<.*?>", "", value)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def _optional_float(value: Any) -> float | None:
    """把统计字段安全转换为可选浮点数。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _spread_sentence(deviation: float | None) -> str:
    """根据标准差生成空间异质性描述。"""
    if deviation is None:
        return ""
    level = "明显" if deviation > 0.18 else "可控"
    return f" 标准差 {deviation:.3f}，空间差异{level}。"


def _range_sentence(minimum: float | None, maximum: float | None) -> str:
    """补充最小值和最大值，便于判读是否存在局部异常。"""
    if minimum is None or maximum is None:
        return ""
    return f" 有效值范围 {minimum:.3f} 到 {maximum:.3f}。"


def _interpret_index(
    index_id: str,
    mean: float,
    deviation: float | None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> tuple[str, str]:
    """完成模块内部的 interpret_index 辅助处理。"""
    spread = _spread_sentence(deviation)
    value_range = _range_sentence(minimum, maximum)
    if index_id in {"ndvi", "gndvi", "evi", "savi", "osavi", "msavi"}:
        if mean < 0.25:
            return "danger", f"植被活力偏低，需重点排查裸土、缺苗、病虫害或云阴影影响。{value_range}{spread}"
        if mean < 0.55:
            return "warning", f"植被活力中等，建议结合历史同期或地块分区继续判断。{value_range}{spread}"
        return "normal", f"整体长势较好，可关注局部低值斑块是否集中。{value_range}{spread}"
    if index_id == "ndmi":
        if mean < 0:
            return "danger", f"NDMI 均值低于 0，水分亏缺或裸土/阴影干扰风险较高。{value_range}{spread}"
        if mean < 0.2:
            return "warning", f"NDMI 处于偏低水分区间，建议优先核验灌溉、降雨和土壤含水量。{value_range}{spread}"
        if mean > 0.75:
            return "warning", f"NDMI 水分信号异常偏高，可能对应高湿、积水、云影或波段定标偏差，需要与原始影像和地块记录核对。{value_range}{spread}"
        return "normal", f"NDMI 显示冠层水分状况总体可接受，仍需结合 MSI 和局部低值区判断。{value_range}{spread}"
    if index_id == "msi":
        if mean >= 1.2:
            return "danger", f"MSI 越高通常表示水分胁迫越强；当前均值进入明显胁迫区间，应核查干旱、灌溉不足或 SWIR/NIR 波段映射。{value_range}{spread}"
        if mean >= 0.7:
            return "warning", f"MSI 越高通常表示水分胁迫越强；当前均值处于轻度压力或需复核区间，不宜直接判定为水分稳定。{value_range}{spread}"
        return "normal", f"MSI 均值较低，暂未显示明显水分胁迫，但仍需与 NDMI、天气和地块管理记录联合解释。{value_range}{spread}"
    return "normal", f"该指数统计处于可解释范围，建议与主指数联合判读。{value_range}{spread}"


def _summary_from_insights(insights: list[dict[str, str]]) -> str:
    """完成模块内部的 summary_from_insights 辅助处理。"""
    if not insights:
        return "暂无可判读的统计结果，请先完成指数计算并确认有效像元。"
    if any(item["severity"] == "danger" for item in insights):
        return "统计结果提示存在需要优先核查的低值或异常区域。"
    if any(item["severity"] == "warning" for item in insights):
        return "统计结果可用于初步判断，但部分指数进入需复核区间，应结合原始影像、地块记录和分区统计后再下结论。"
    return "统计结果未显示明显异常，可作为当前地块状态的基线参考。"


def _next_action_from_context(index_ids: set[str], user_goal: str) -> str:
    """根据指数组合和用户目标给出下一步核验建议。"""
    if {"ndmi", "msi"} & index_ids or "干旱" in user_goal or "水分" in user_goal:
        return "把 NDMI、MSI、近期降雨、灌溉记录和土壤水分传感器放在同一地块边界内复核，重点检查 MSI 高值与 NDMI 低值是否空间重合。"
    if {"ndvi", "evi", "gndvi"} & index_ids or "长势" in user_goal:
        return "优先叠加地块边界、云阴影掩膜和历史同期 NDVI/EVI，确认低值斑块是作物长势问题还是影像质量问题。"
    return "优先复核波段映射、云阴影掩膜和异常斑块；必要时叠加地块边界做分区统计。"
