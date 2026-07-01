from pathlib import Path

import numpy as np
import pytest
import rasterio

from app.services.advanced_analysis import (
    calculate_zonal_statistics,
    detect_change,
    evaluate_custom_expression,
    validate_custom_expression,
)


def test_custom_formula_uses_whitelisted_bands_and_operators() -> None:
    validation = validate_custom_expression("(nir-red)/(nir+red)", ["nir", "red"])
    assert validation["requiredBands"] == ["nir", "red"]
    result = evaluate_custom_expression(
        "(nir-red)/(nir+red)",
        {
            "nir": np.array([0.8], dtype=np.float32),
            "red": np.array([0.2], dtype=np.float32),
        },
    )
    np.testing.assert_allclose(result, [0.6])


def test_custom_formula_rejects_attribute_access() -> None:
    with pytest.raises(ValueError):
        validate_custom_expression("nir.__class__", ["nir"])


def test_change_detection_and_zonal_statistics(sample_raster: Path, tmp_path: Path) -> None:
    before = tmp_path / "before.tif"
    after = tmp_path / "after.tif"
    output = tmp_path / "change.tif"

    with rasterio.open(sample_raster) as source:
        profile = source.profile
        base = source.read(1)
    with rasterio.open(before, "w", **profile) as dataset:
        dataset.write(base, 1)
        for band in range(2, profile["count"] + 1):
            dataset.write(base, band)
    with rasterio.open(after, "w", **profile) as dataset:
        dataset.write(base + 0.3, 1)
        for band in range(2, profile["count"] + 1):
            dataset.write(base, band)

    result = detect_change(str(before), str(after), str(output), -0.2, 0.2)
    assert Path(result["outputPath"]).is_file()
    assert result["classPixelCounts"]["increase"] == 96 * 64

    zones = calculate_zonal_statistics(
        str(after),
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "plot-1",
                    "properties": {"name": "测试地块"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [100.0, 29.936],
                                [100.096, 29.936],
                                [100.096, 30.0],
                                [100.0, 30.0],
                                [100.0, 29.936],
                            ]
                        ],
                    },
                }
            ],
        },
    )
    assert zones["zones"][0]["id"] == "plot-1"
    assert zones["zones"][0]["validPixels"] == 96 * 64
