"""计算引擎公共协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from app.core.indices import IndexDefinition


@dataclass(slots=True)
class EngineResult:
    arrays: dict[str, np.ndarray]
    engine: str
    fallback_reason: str | None = None


class ComputeEngine(Protocol):
    name: str

    def compute(
        self,
        definitions: list[IndexDefinition],
        bands: dict[str, np.ndarray],
        parameters: dict[str, dict[str, float]] | None = None,
    ) -> EngineResult: ...


def sanitize_result(array: np.ndarray, nodata: float = -9999.0) -> np.ndarray:
    """统一转换输出类型，并替换 NaN/Inf。"""
    result = np.asarray(array, dtype=np.float32)
    return np.nan_to_num(result, nan=nodata, posinf=nodata, neginf=nodata)
