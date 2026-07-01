"""多引擎公式计算微基准。"""

from __future__ import annotations

import argparse
import json
from time import perf_counter

import numpy as np

from app.core.indices import get_index
from app.engines.joblib_engine import JoblibEngine
from app.engines.numpy_engine import NumpyEngine
from app.engines.torch_engine import TorchEngine


def run(size: int, repeats: int) -> list[dict[str, object]]:
    random = np.random.default_rng(42)
    bands = {
        name: random.uniform(0.05, 0.9, (size, size)).astype(np.float32)
        for name in ("blue", "green", "red", "red_edge", "nir", "swir1", "swir2")
    }
    definitions = [get_index(item) for item in ("ndvi", "evi", "gndvi", "savi", "ndmi")]
    baseline = NumpyEngine().compute(definitions, bands).arrays
    records = []
    for engine in (NumpyEngine(), JoblibEngine(), TorchEngine()):
        durations = []
        result = None
        for _ in range(repeats):
            started = perf_counter()
            result = engine.compute(definitions, bands)
            durations.append(perf_counter() - started)
        max_error = max(
            float(np.max(np.abs(result.arrays[key] - baseline[key]))) for key in baseline
        )
        records.append(
            {
                "engine": result.engine,
                "requestedEngine": engine.name,
                "size": size,
                "repeats": repeats,
                "meanSeconds": sum(durations) / len(durations),
                "maxError": max_error,
                "fallbackReason": result.fallback_reason,
            }
        )
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=2048)
    parser.add_argument("--repeats", type=int, default=3)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.size, arguments.repeats), ensure_ascii=False, indent=2))
