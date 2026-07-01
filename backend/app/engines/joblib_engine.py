"""Joblib线程并行计算引擎。"""

from __future__ import annotations

import os

import numpy as np

from app.core.indices import IndexDefinition
from app.engines.base import EngineResult, sanitize_result
from app.engines.numpy_engine import NumpyEngine


class JoblibEngine:
    name = "joblib"

    def __init__(self, workers: int | None = None) -> None:
        self.workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))

    def compute(
        self,
        definitions: list[IndexDefinition],
        bands: dict[str, np.ndarray],
        parameters: dict[str, dict[str, float]] | None = None,
    ) -> EngineResult:
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
            result = definition.calculate(
                np,
                normalized_bands,
                (parameters or {}).get(definition.id),
            )
            return definition.id, sanitize_result(result)

        results = Parallel(n_jobs=self.workers, prefer="threads", batch_size="auto")(
            delayed(calculate)(definition) for definition in definitions
        )
        return EngineResult(arrays=dict(results), engine=self.name)
