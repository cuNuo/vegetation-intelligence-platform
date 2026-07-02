# backend/app/engines/joblib_engine.py
# 文件说明：Joblib CPU 并行计算引擎。
# 主要职责：并行计算同一窗口内的多个指数并支持回退。
# 对外入口：JoblibEngine。
# 依赖边界：不并行 Rasterio 写入。

"""Joblib线程并行计算引擎。"""

from __future__ import annotations

import os

import numpy as np

from app.core.indices import IndexDefinition
from app.engines.base import EngineResult, sanitize_result
from app.engines.numpy_engine import NumpyEngine


class JoblibEngine:
    """封装 JoblibEngine 相关状态、约束和可复用行为。"""
    name = "joblib"

    def __init__(self, workers: int | None = None) -> None:
        """初始化实例依赖、运行状态和可配置参数。"""
        self.workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))

    def compute(
        self,
        definitions: list[IndexDefinition],
        bands: dict[str, np.ndarray],
        parameters: dict[str, dict[str, float]] | None = None,
    ) -> EngineResult:
        """计算一个窗口内的指数数组并返回统一结果结构。"""
        try:
            from joblib import Parallel, delayed
        except ImportError:
            fallback = NumpyEngine().compute(definitions, bands, parameters)
            fallback.fallback_reason = "joblib未安装，已回退NumPy"
            return fallback

        normalized_bands = {
            name: np.asarray(array, dtype=np.float32) for name, array in bands.items()
        }

        def calculate(definition: IndexDefinition) -> tuple[str, np.ndarray]:
            """校验所需波段、合并参数并调用统一公式表达式。"""
            result = definition.calculate(
                np,
                normalized_bands,
                (parameters or {}).get(definition.id),
            )
            return definition.id, sanitize_result(result, expected_range=definition.expected_range)

        results = Parallel(n_jobs=self.workers, prefer="threads", batch_size="auto")(
            delayed(calculate)(definition) for definition in definitions
        )
        return EngineResult(arrays=dict(results), engine=self.name)
