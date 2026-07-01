"""植被指数注册表。

公式函数只依赖传入的数组后端 ``xp``，因此同一份定义可以由 NumPy 或
PyTorch 执行。所有除法统一经过 ``safe_divide``，避免无穷值污染结果。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

Array = Any
Expression = Callable[[Any, dict[str, Array], dict[str, float]], Array]


def safe_divide(xp: Any, numerator: Array, denominator: Array, epsilon: float = 1e-6) -> Array:
    """在 NumPy/PyTorch 间保持一致的安全除法语义。"""
    safe_denominator = xp.where(xp.abs(denominator) < epsilon, epsilon, denominator)
    return numerator / safe_denominator


@dataclass(frozen=True, slots=True)
class IndexDefinition:
    id: str
    name: str
    formula: str
    required_bands: tuple[str, ...]
    expression: Expression
    description: str
    expected_range: tuple[float, float] | None = None
    parameters: dict[str, float] = field(default_factory=dict)
    categories: tuple[str, ...] = ()
    recommendation_tags: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    amp_safe: bool = True

    def calculate(
        self,
        xp: Any,
        bands: dict[str, Array],
        parameters: dict[str, float] | None = None,
    ) -> Array:
        missing = set(self.required_bands) - bands.keys()
        if missing:
            raise ValueError(f"{self.id} 缺少波段: {', '.join(sorted(missing))}")
        merged_parameters = {**self.parameters, **(parameters or {})}
        return self.expression(xp, bands, merged_parameters)

    def public_metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "formula": self.formula,
            "requiredBands": list(self.required_bands),
            "description": self.description,
            "expectedRange": self.expected_range,
            "parameters": self.parameters,
            "categories": list(self.categories),
            "recommendationTags": list(self.recommendation_tags),
            "limitations": list(self.limitations),
        }


def _ratio(a: str, b: str) -> Expression:
    return lambda xp, bands, _params: safe_divide(xp, bands[a], bands[b])


def _normalized(a: str, b: str) -> Expression:
    return lambda xp, bands, _params: safe_divide(xp, bands[a] - bands[b], bands[a] + bands[b])


COMMON_LIMITATIONS = ("云、阴影和积雪会影响结果", "使用前需确认波段映射与反射率尺度")


INDEX_DEFINITIONS = (
    IndexDefinition(
        "ndvi",
        "归一化植被指数",
        "(NIR-Red)/(NIR+Red)",
        ("nir", "red"),
        _normalized("nir", "red"),
        "通用植被覆盖度和长势指标。",
        (-1, 1),
        categories=("vegetation", "biomass"),
        recommendation_tags=("植被覆盖", "长势评估", "变化监测"),
        limitations=COMMON_LIMITATIONS + ("高覆盖度区域容易饱和",),
    ),
    IndexDefinition(
        "gndvi",
        "绿色归一化植被指数",
        "(NIR-Green)/(NIR+Green)",
        ("nir", "green"),
        _normalized("nir", "green"),
        "对叶绿素变化较敏感。",
        (-1, 1),
        categories=("chlorophyll",),
        recommendation_tags=("叶绿素", "氮素状态", "长势评估"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "ndre",
        "归一化红边指数",
        "(NIR-RedEdge)/(NIR+RedEdge)",
        ("nir", "red_edge"),
        _normalized("nir", "red_edge"),
        "适合中高覆盖度作物叶绿素与胁迫监测。",
        (-1, 1),
        categories=("red-edge", "chlorophyll"),
        recommendation_tags=("叶绿素", "作物胁迫", "中后期长势"),
        limitations=COMMON_LIMITATIONS + ("传感器必须具有红边波段",),
    ),
    IndexDefinition(
        "rvi",
        "比值植被指数",
        "NIR/Red",
        ("nir", "red"),
        _ratio("nir", "red"),
        "简单的近红外与红光比值。",
        categories=("vegetation",),
        recommendation_tags=("植被覆盖",),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "dvi",
        "差值植被指数",
        "NIR-Red",
        ("nir", "red"),
        lambda _xp, b, _p: b["nir"] - b["red"],
        "突出近红外与红光反射差异。",
        categories=("vegetation",),
        recommendation_tags=("植被覆盖",),
        limitations=COMMON_LIMITATIONS + ("对辐射尺度敏感",),
    ),
    IndexDefinition(
        "savi",
        "土壤调节植被指数",
        "(1+L)*(NIR-Red)/(NIR+Red+L)",
        ("nir", "red"),
        lambda xp, b, p: (
            (1 + p["L"]) * safe_divide(xp, b["nir"] - b["red"], b["nir"] + b["red"] + p["L"])
        ),
        "降低稀疏植被区域土壤背景影响。",
        (-1, 1),
        {"L": 0.5},
        ("soil-adjusted",),
        ("稀疏植被", "裸土背景"),
        COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "osavi",
        "优化土壤调节植被指数",
        "1.16*(NIR-Red)/(NIR+Red+0.16)",
        ("nir", "red"),
        lambda xp, b, _p: 1.16 * safe_divide(xp, b["nir"] - b["red"], b["nir"] + b["red"] + 0.16),
        "无需场景相关土壤调节参数。",
        (-1, 1),
        categories=("soil-adjusted",),
        recommendation_tags=("稀疏植被", "裸土背景"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "msavi",
        "修正土壤调节植被指数",
        "(2*NIR+1-sqrt((2*NIR+1)^2-8*(NIR-Red)))/2",
        ("nir", "red"),
        lambda xp, b, _p: (
            (
                2 * b["nir"]
                + 1
                - xp.sqrt(xp.maximum((2 * b["nir"] + 1) ** 2 - 8 * (b["nir"] - b["red"]), 0))
            )
            / 2
        ),
        "自动调节土壤背景影响。",
        (-1, 1),
        categories=("soil-adjusted",),
        recommendation_tags=("稀疏植被", "苗期监测"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "evi",
        "增强植被指数",
        "G*(NIR-Red)/(NIR+C1*Red-C2*Blue+L)",
        ("nir", "red", "blue"),
        lambda xp, b, p: (
            p["G"]
            * safe_divide(
                xp,
                b["nir"] - b["red"],
                b["nir"] + p["C1"] * b["red"] - p["C2"] * b["blue"] + p["L"],
            )
        ),
        "减弱大气与土壤背景影响，适合高生物量区域。",
        (-1, 1),
        {"G": 2.5, "C1": 6.0, "C2": 7.5, "L": 1.0},
        ("vegetation", "atmosphere-resistant"),
        ("高覆盖植被", "生物量", "长势评估"),
        COMMON_LIMITATIONS + ("需要蓝光波段",),
    ),
    IndexDefinition(
        "evi2",
        "双波段增强植被指数",
        "2.5*(NIR-Red)/(NIR+2.4*Red+1)",
        ("nir", "red"),
        lambda xp, b, _p: 2.5 * safe_divide(xp, b["nir"] - b["red"], b["nir"] + 2.4 * b["red"] + 1),
        "无蓝光波段时的增强植被指数。",
        (-1, 1),
        categories=("vegetation",),
        recommendation_tags=("高覆盖植被", "长势评估"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "arvi",
        "抗大气植被指数",
        "(NIR-(2*Red-Blue))/(NIR+(2*Red-Blue))",
        ("nir", "red", "blue"),
        lambda xp, b, _p: safe_divide(
            xp,
            b["nir"] - (2 * b["red"] - b["blue"]),
            b["nir"] + (2 * b["red"] - b["blue"]),
        ),
        "降低大气散射对植被识别的影响。",
        (-1, 1),
        categories=("atmosphere-resistant",),
        recommendation_tags=("大气影响", "植被覆盖"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "vari",
        "可见光抗大气指数",
        "(Green-Red)/(Green+Red-Blue)",
        ("green", "red", "blue"),
        lambda xp, b, _p: safe_divide(xp, b["green"] - b["red"], b["green"] + b["red"] - b["blue"]),
        "仅使用可见光进行植被识别。",
        (-1, 1),
        categories=("visible",),
        recommendation_tags=("无人机RGB", "植被覆盖"),
        limitations=COMMON_LIMITATIONS + ("不包含近红外，稳定性低于NDVI",),
    ),
    IndexDefinition(
        "gli",
        "绿叶指数",
        "(2*Green-Red-Blue)/(2*Green+Red+Blue)",
        ("green", "red", "blue"),
        lambda xp, b, _p: safe_divide(
            xp,
            2 * b["green"] - b["red"] - b["blue"],
            2 * b["green"] + b["red"] + b["blue"],
        ),
        "基于RGB图像估计绿色叶片比例。",
        (-1, 1),
        categories=("visible",),
        recommendation_tags=("无人机RGB", "冠层绿度"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "ngrdi",
        "归一化绿红差异指数",
        "(Green-Red)/(Green+Red)",
        ("green", "red"),
        _normalized("green", "red"),
        "适用于RGB农田影像。",
        (-1, 1),
        categories=("visible",),
        recommendation_tags=("无人机RGB", "植被覆盖"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "exg",
        "过绿指数",
        "2*Green-Red-Blue",
        ("green", "red", "blue"),
        lambda _xp, b, _p: 2 * b["green"] - b["red"] - b["blue"],
        "突出RGB影像中的绿色像元。",
        categories=("visible",),
        recommendation_tags=("苗木分割", "无人机RGB"),
        limitations=COMMON_LIMITATIONS + ("对光照和反射率尺度敏感",),
    ),
    IndexDefinition(
        "tvi",
        "变换植被指数",
        "sqrt(max(NDVI+0.5,0))",
        ("nir", "red"),
        lambda xp, b, _p: xp.sqrt(
            xp.maximum(safe_divide(xp, b["nir"] - b["red"], b["nir"] + b["red"]) + 0.5, 0)
        ),
        "对NDVI进行平方根变换。",
        categories=("vegetation",),
        recommendation_tags=("植被覆盖",),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "ctvi",
        "修正变换植被指数",
        "sign(NDVI+0.5)*sqrt(abs(NDVI+0.5))",
        ("nir", "red"),
        lambda xp, b, _p: (
            xp.sign(safe_divide(xp, b["nir"] - b["red"], b["nir"] + b["red"]) + 0.5)
            * xp.sqrt(xp.abs(safe_divide(xp, b["nir"] - b["red"], b["nir"] + b["red"]) + 0.5))
        ),
        "保留变换后指数的符号。",
        categories=("vegetation",),
        recommendation_tags=("植被覆盖",),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "ipvi",
        "红外百分比植被指数",
        "NIR/(NIR+Red)",
        ("nir", "red"),
        lambda xp, b, _p: safe_divide(xp, b["nir"], b["nir"] + b["red"]),
        "与NDVI线性相关，范围通常为0到1。",
        (0, 1),
        categories=("vegetation",),
        recommendation_tags=("植被覆盖",),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "gci",
        "绿色叶绿素指数",
        "NIR/Green-1",
        ("nir", "green"),
        lambda xp, b, _p: safe_divide(xp, b["nir"], b["green"]) - 1,
        "估计叶片叶绿素含量。",
        categories=("chlorophyll",),
        recommendation_tags=("叶绿素", "氮素状态"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "reci",
        "红边叶绿素指数",
        "NIR/RedEdge-1",
        ("nir", "red_edge"),
        lambda xp, b, _p: safe_divide(xp, b["nir"], b["red_edge"]) - 1,
        "使用红边波段估计叶绿素。",
        categories=("red-edge", "chlorophyll"),
        recommendation_tags=("叶绿素", "作物胁迫"),
        limitations=COMMON_LIMITATIONS + ("传感器必须具有红边波段",),
    ),
    IndexDefinition(
        "mcari",
        "修正叶绿素吸收比值指数",
        "((RE-Red)-0.2*(RE-Green))*(RE/Red)",
        ("red_edge", "red", "green"),
        lambda xp, b, _p: (
            ((b["red_edge"] - b["red"]) - 0.2 * (b["red_edge"] - b["green"]))
            * safe_divide(xp, b["red_edge"], b["red"])
        ),
        "增强叶绿素吸收特征。",
        categories=("chlorophyll", "red-edge"),
        recommendation_tags=("叶绿素", "冠层状态"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "tcari",
        "转换叶绿素吸收比值指数",
        "3*((RE-Red)-0.2*(RE-Green)*(RE/Red))",
        ("red_edge", "red", "green"),
        lambda xp, b, _p: (
            3
            * (
                (b["red_edge"] - b["red"])
                - 0.2 * (b["red_edge"] - b["green"]) * safe_divide(xp, b["red_edge"], b["red"])
            )
        ),
        "用于叶绿素含量变化分析。",
        categories=("chlorophyll", "red-edge"),
        recommendation_tags=("叶绿素",),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "mtci",
        "陆地叶绿素指数",
        "(NIR-RE)/(RE-Red)",
        ("nir", "red_edge", "red"),
        lambda xp, b, _p: safe_divide(xp, b["nir"] - b["red_edge"], b["red_edge"] - b["red"]),
        "适用于具有红边波段的叶绿素监测。",
        categories=("chlorophyll", "red-edge"),
        recommendation_tags=("叶绿素", "氮素状态"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "psri",
        "植物衰老反射指数",
        "(Red-Green)/RE",
        ("red", "green", "red_edge"),
        lambda xp, b, _p: safe_divide(xp, b["red"] - b["green"], b["red_edge"]),
        "辅助识别叶片衰老和类胡萝卜素变化。",
        categories=("senescence",),
        recommendation_tags=("衰老", "成熟期", "胁迫"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "sipi",
        "结构不敏感色素指数",
        "(NIR-Blue)/(NIR-Red)",
        ("nir", "blue", "red"),
        lambda xp, b, _p: safe_divide(xp, b["nir"] - b["blue"], b["nir"] - b["red"]),
        "反映类胡萝卜素与叶绿素比例。",
        categories=("pigment",),
        recommendation_tags=("色素", "胁迫"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "ndmi",
        "归一化水分指数",
        "(NIR-SWIR1)/(NIR+SWIR1)",
        ("nir", "swir1"),
        _normalized("nir", "swir1"),
        "反映冠层含水量与水分胁迫。",
        (-1, 1),
        categories=("water",),
        recommendation_tags=("水分胁迫", "干旱"),
        limitations=COMMON_LIMITATIONS + ("需要短波红外波段",),
    ),
    IndexDefinition(
        "ndwi",
        "归一化水体指数",
        "(Green-NIR)/(Green+NIR)",
        ("green", "nir"),
        _normalized("green", "nir"),
        "突出开放水体，也可辅助排除水体。",
        (-1, 1),
        categories=("water",),
        recommendation_tags=("水体识别", "干旱辅助"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "msi",
        "水分胁迫指数",
        "SWIR1/NIR",
        ("swir1", "nir"),
        _ratio("swir1", "nir"),
        "数值升高通常表示冠层水分减少。",
        categories=("water",),
        recommendation_tags=("水分胁迫", "干旱"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "nbr",
        "归一化燃烧比",
        "(NIR-SWIR2)/(NIR+SWIR2)",
        ("nir", "swir2"),
        _normalized("nir", "swir2"),
        "用于植被火烧迹地和严重扰动分析。",
        (-1, 1),
        categories=("disturbance",),
        recommendation_tags=("火烧迹地", "植被扰动", "变化监测"),
        limitations=COMMON_LIMITATIONS,
    ),
    IndexDefinition(
        "bsi",
        "裸土指数",
        "((SWIR1+Red)-(NIR+Blue))/((SWIR1+Red)+(NIR+Blue))",
        ("swir1", "red", "nir", "blue"),
        lambda xp, b, _p: safe_divide(
            xp,
            (b["swir1"] + b["red"]) - (b["nir"] + b["blue"]),
            (b["swir1"] + b["red"]) + (b["nir"] + b["blue"]),
        ),
        "识别裸土并辅助判断土壤背景。",
        (-1, 1),
        categories=("soil",),
        recommendation_tags=("裸土", "稀疏植被"),
        limitations=COMMON_LIMITATIONS,
    ),
)

INDEX_REGISTRY = {definition.id: definition for definition in INDEX_DEFINITIONS}
CORE_INDEX_COUNT = len(INDEX_DEFINITIONS)

if CORE_INDEX_COUNT != 30:
    raise RuntimeError(f"注册表必须包含30种指数，当前为{len(INDEX_REGISTRY)}")


def get_index(index_id: str) -> IndexDefinition:
    try:
        return INDEX_REGISTRY[index_id.lower()]
    except KeyError as error:
        raise ValueError(f"未知植被指数: {index_id}") from error
