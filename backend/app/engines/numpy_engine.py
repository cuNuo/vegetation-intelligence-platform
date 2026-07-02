# backend/app/engines/numpy_engine.py
# 文件说明：NumPy 基线计算引擎。
# 主要职责：顺序执行注册公式并统一清洗结果。
# 对外入口：NumpyEngine。
# 依赖边界：作为跨引擎正确性基线。

"""NumPy兼容计算引擎。"""

from __future__ import annotations

import numpy as np

from app.core.indices import IndexDefinition
from app.engines.base import EngineResult, sanitize_result


class NumpyEngine:
    """封装 NumpyEngine 相关状态、约束和可复用行为。"""
    name = "numpy"

    def compute(
        self,
        definitions: list[IndexDefinition],
        bands: dict[str, np.ndarray],
        parameters: dict[str, dict[str, float]] | None = None,
    ) -> EngineResult:
        """计算一个窗口内的指数数组并返回统一结果结构。"""
        normalized_bands = {
            name: np.asarray(array, dtype=np.float32) for name, array in bands.items()
        }
        arrays = {
            definition.id: sanitize_result(
                definition.calculate(
                    np,
                    normalized_bands,
                    (parameters or {}).get(definition.id),
                ),
                expected_range=definition.expected_range,
            )
            for definition in definitions
        }
        return EngineResult(arrays=arrays, engine=self.name)
