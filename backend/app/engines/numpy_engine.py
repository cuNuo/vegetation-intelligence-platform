"""NumPy兼容计算引擎。"""

from __future__ import annotations

import numpy as np

from app.core.indices import IndexDefinition
from app.engines.base import EngineResult, sanitize_result


class NumpyEngine:
    name = "numpy"

    def compute(
        self,
        definitions: list[IndexDefinition],
        bands: dict[str, np.ndarray],
        parameters: dict[str, dict[str, float]] | None = None,
    ) -> EngineResult:
        normalized_bands = {
            name: np.asarray(array, dtype=np.float32) for name, array in bands.items()
        }
        arrays = {
            definition.id: sanitize_result(
                definition.calculate(
                    np,
                    normalized_bands,
                    (parameters or {}).get(definition.id),
                )
            )
            for definition in definitions
        }
        return EngineResult(arrays=arrays, engine=self.name)
