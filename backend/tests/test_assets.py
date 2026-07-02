# backend/tests/test_assets.py
# 文件说明：上传影像内部金字塔构建、复用与元数据回读测试。

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.services.assets import ensure_raster_overviews, inspect_raster


def _write_raster(
    path: Path,
    width: int,
    height: int,
    count: int = 1,
    descriptions: tuple[str | None, ...] | None = None,
) -> None:
    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": count,
        "dtype": "uint16",
        "crs": "EPSG:4326",
        "transform": from_origin(100, 30, 0.0001, 0.0001),
        "nodata": 0,
        "tiled": True,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dataset:
        for band_index in range(1, count + 1):
            dataset.write(
                np.full((height, width), 1000 * band_index, dtype=np.uint16),
                band_index,
            )
        if descriptions:
            dataset.descriptions = descriptions


def test_first_open_builds_and_reuses_internal_overviews(tmp_path: Path) -> None:
    source = tmp_path / "large.tif"
    _write_raster(source, 1024, 768)

    built = ensure_raster_overviews(source)
    reused = ensure_raster_overviews(source)
    metadata = inspect_raster(str(source))

    assert built["status"] == "built"
    assert built["levels"]
    assert reused["status"] == "reused"
    assert metadata["overviewLevels"] == built["levels"]
    assert metadata["overviewCount"] == len(built["levels"])


def test_small_raster_does_not_create_unnecessary_overviews(tmp_path: Path) -> None:
    source = tmp_path / "small.tif"
    _write_raster(source, 256, 256)

    result = ensure_raster_overviews(source)

    assert result == {"status": "not-needed", "levels": []}


def test_sensor_filename_profiles_restore_exported_band_metadata(tmp_path: Path) -> None:
    expected = {
        "GF01_130200_202301.tif": (
            "GF-1",
            ["Blue B1", "Green B2", "Red B3", "NIR B4"],
            [485.0, 555.0, 660.0, 830.0],
        ),
        "LAD08_130200_202301.tif": (
            "Landsat 8/9 OLI",
            [
                "Coastal Aerosol B1",
                "Blue B2",
                "Green B3",
                "Red B4",
                "NIR B5",
                "SWIR1 B6",
                "SWIR2 B7",
            ],
            [443.0, 482.0, 561.0, 655.0, 865.0, 1610.0, 2200.0],
        ),
        "LAD09_130200_202301.tif": (
            "Landsat 8/9 OLI",
            [
                "Coastal Aerosol B1",
                "Blue B2",
                "Green B3",
                "Red B4",
                "NIR B5",
                "SWIR1 B6",
                "SWIR2 B7",
            ],
            [443.0, 482.0, 561.0, 655.0, 865.0, 1610.0, 2200.0],
        ),
        "SHB02_130200_202301.tif": (
            "Sentinel-2A/2B MSI",
            ["Blue B2", "Green B3", "Red B4", "NIR B8"],
            [490.0, 560.0, 665.0, 842.0],
        ),
    }

    for filename, (sensor, descriptions, wavelengths) in expected.items():
        source = tmp_path / filename
        _write_raster(source, 32, 32, count=len(descriptions))

        metadata = inspect_raster(str(source))

        assert metadata["sensor"] == sensor
        assert metadata["bandInferenceSource"] == "filename-profile"
        assert metadata["descriptions"] == descriptions
        assert [band["wavelengthNm"] for band in metadata["bandMetadata"]] == wavelengths


def test_sensor_profile_requires_expected_band_count_and_preserves_description(
    tmp_path: Path,
) -> None:
    wrong_count = tmp_path / "LAD08_wrong_count.tif"
    described = tmp_path / "GF01_described.tif"
    _write_raster(wrong_count, 32, 32, count=4)
    _write_raster(
        described,
        32,
        32,
        count=4,
        descriptions=("Custom Blue 500 nm", None, None, None),
    )

    wrong_metadata = inspect_raster(str(wrong_count))
    described_metadata = inspect_raster(str(described))

    assert wrong_metadata["sensor"] is None
    assert wrong_metadata["bandInferenceSource"] is None
    assert described_metadata["descriptions"][0] == "Custom Blue 500 nm"
    assert described_metadata["bandMetadata"][0]["wavelengthNm"] == 500.0


def test_original_filename_hint_restores_profile_after_uuid_storage(tmp_path: Path) -> None:
    stored_path = tmp_path / "a9d4a7a33d3749bdb6ea6e036cde042f.tif"
    _write_raster(stored_path, 32, 32, count=7)

    without_hint = inspect_raster(str(stored_path))
    with_hint = inspect_raster(
        str(stored_path),
        filename_hint="LAD08_130200_202301.tif",
    )

    assert without_hint["sensor"] is None
    assert with_hint["sensor"] == "Landsat 8/9 OLI"
    assert [band["description"] for band in with_hint["bandMetadata"]] == [
        "Coastal Aerosol B1",
        "Blue B2",
        "Green B3",
        "Red B4",
        "NIR B5",
        "SWIR1 B6",
        "SWIR2 B7",
    ]
