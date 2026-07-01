import numpy as np

from app.core.indices import INDEX_REGISTRY, get_index
from app.engines.joblib_engine import JoblibEngine
from app.engines.numpy_engine import NumpyEngine
from app.engines.torch_engine import TorchEngine

BANDS = {
    "blue": np.array([[0.1, 0.2]], dtype=np.float32),
    "green": np.array([[0.2, 0.3]], dtype=np.float32),
    "red": np.array([[0.3, 0.4]], dtype=np.float32),
    "red_edge": np.array([[0.45, 0.5]], dtype=np.float32),
    "nir": np.array([[0.7, 0.8]], dtype=np.float32),
    "swir1": np.array([[0.35, 0.45]], dtype=np.float32),
    "swir2": np.array([[0.25, 0.3]], dtype=np.float32),
}


def test_registry_contains_taskbook_and_legacy_service_indices() -> None:
    assert len(INDEX_REGISTRY) == 35
    assert {
        "ndvi",
        "osavi",
        "gndvi",
        "evi",
        "ndre",
        "ndmi",
        "bndvi",
        "normb",
        "gr",
        "msr",
        "rdvi",
    } <= INDEX_REGISTRY.keys()


def test_ndvi_matches_manual_formula() -> None:
    result = NumpyEngine().compute([get_index("ndvi")], BANDS).arrays["ndvi"]
    expected = (BANDS["nir"] - BANDS["red"]) / (BANDS["nir"] + BANDS["red"])
    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_all_indices_produce_finite_float32_arrays() -> None:
    result = NumpyEngine().compute(list(INDEX_REGISTRY.values()), BANDS)
    assert result.arrays.keys() == INDEX_REGISTRY.keys()
    for array in result.arrays.values():
        assert array.dtype == np.float32
        assert np.isfinite(array).all()


def test_joblib_matches_numpy() -> None:
    definitions = [get_index("ndvi"), get_index("evi"), get_index("msavi")]
    expected = NumpyEngine().compute(definitions, BANDS).arrays
    actual = JoblibEngine(workers=2).compute(definitions, BANDS).arrays
    for index_id in expected:
        np.testing.assert_allclose(actual[index_id], expected[index_id], rtol=1e-6)


def test_torch_engine_falls_back_or_matches() -> None:
    definition = [get_index("ndvi")]
    expected = NumpyEngine().compute(definition, BANDS).arrays["ndvi"]
    result = TorchEngine().compute(definition, BANDS)
    np.testing.assert_allclose(result.arrays["ndvi"], expected, rtol=1e-5)
