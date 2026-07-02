# backend/app/engines/base.py
# 文件说明：计算引擎公共协议与输出清洗。
# 主要职责：定义结果结构、compute 协议和 nodata 归一化。
# 对外入口：EngineResult、ComputeEngine、sanitize_result。
# 依赖边界：不负责栅格 I/O 和调度。

"""计算引擎公共协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from app.core.indices import IndexDefinition


@dataclass(slots=True)
class EngineResult:
    """封装 EngineResult 相关状态、约束和可复用行为。"""
    arrays: dict[str, np.ndarray]
    engine: str
    fallback_reason: str | None = None


class ComputeEngine(Protocol):
    """封装 ComputeEngine 相关状态、约束和可复用行为。"""

    name: str

    def compute(
        self,
        definitions: list[IndexDefinition],
        bands: dict[str, np.ndarray],
        parameters: dict[str, dict[str, float]] | None = None,
    ) -> EngineResult:
        """计算一个窗口内的多个指数，并返回统一结果结构。"""
        ...


def sanitize_result(
    array: np.ndarray,
    nodata: float = -9999.0,
    expected_range: tuple[float, float] | None = None,
) -> np.ndarray:
    """统一转换输出类型，并把不可解释的异常指数值写成 nodata。"""
    result = np.asarray(array, dtype=np.float32)
    result = np.nan_to_num(result, nan=nodata, posinf=nodata, neginf=nodata)
    if expected_range is not None:
        lower, upper = expected_range
        tolerance = max(1e-4, (upper - lower) * 1e-4)
        out_of_range = (result != nodata) & (
            (result < lower - tolerance) | (result > upper + tolerance)
        )
        result[out_of_range] = nodata
    return result
