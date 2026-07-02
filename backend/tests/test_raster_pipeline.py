# backend/tests/test_raster_pipeline.py
# 文件说明：分块流水线空间几何测试。
# 主要职责：构造可重复数据并验证业务边界和回归行为。
# 对外入口：pytest fixture 与 test_* 用例。
# 依赖边界：隔离数据库、MinIO 和外部 LLM。

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.services.raster_pipeline import RasterPipeline, RasterTask


def test_windowed_raster_pipeline_preserves_geometry(tmp_path: Path) -> None:
    """验证 windowed raster pipeline preserves geometry 场景的行为和回归边界。"""
    source_path = tmp_path / "source.tif"
    profile = {
        "driver": "GTiff",
        "width": 64,
        "height": 64,
        "count": 4,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(100, 30, 0.001, 0.001),
        "nodata": -9999,
    }
    with rasterio.open(source_path, "w", **profile) as dataset:
        dataset.write(np.full((64, 64), 0.1, dtype=np.float32), 1)
        dataset.write(np.full((64, 64), 0.2, dtype=np.float32), 2)
        dataset.write(np.full((64, 64), 0.3, dtype=np.float32), 3)
        dataset.write(np.full((64, 64), 0.7, dtype=np.float32), 4)

    result = RasterPipeline().run(
        RasterTask(
            source_path=str(source_path),
            output_dir=str(tmp_path / "outputs"),
            indices=["ndvi", "evi"],
            bands={"blue": 1, "green": 2, "red": 3, "nir": 4},
            engine="numpy",
            block_size=128,
        )
    )

    assert result["actualEngine"] == "numpy"
    assert len(result["products"]) == 2
    with rasterio.open(result["products"][0]["path"]) as output:
        assert (output.width, output.height) == (64, 64)
        assert output.crs.to_string() == "EPSG:4326"
        assert output.count == 1
        assert output.dtypes == ("float32",)
        np.testing.assert_allclose(output.read(1), 0.4, atol=1e-5)


def test_integer_reflectance_raster_uses_evi_reflectance_scale(tmp_path: Path) -> None:
    """验证 0-10000 整数反射率不会被 EVI 公式当作原始 DN 直接计算。"""
    source_path = tmp_path / "scaled_reflectance.tif"
    profile = {
        "driver": "GTiff",
        "width": 32,
        "height": 32,
        "count": 4,
        "dtype": "uint16",
        "crs": "EPSG:4326",
        "transform": from_origin(100, 30, 0.001, 0.001),
        "nodata": 0,
    }
    with rasterio.open(source_path, "w", **profile) as dataset:
        dataset.write(np.full((32, 32), 1000, dtype=np.uint16), 1)
        dataset.write(np.full((32, 32), 2000, dtype=np.uint16), 2)
        dataset.write(np.full((32, 32), 3000, dtype=np.uint16), 3)
        dataset.write(np.full((32, 32), 7000, dtype=np.uint16), 4)

    result = RasterPipeline().run(
        RasterTask(
            source_path=str(source_path),
            output_dir=str(tmp_path / "scaled_outputs"),
            indices=["evi"],
            bands={"blue": 1, "green": 2, "red": 3, "nir": 4},
            engine="numpy",
            block_size=128,
        )
    )

    expected_evi = 2.5 * (0.7 - 0.3) / (0.7 + 6 * 0.3 - 7.5 * 0.1 + 1)
    with rasterio.open(result["products"][0]["path"]) as output:
        np.testing.assert_allclose(output.read(1), expected_evi, atol=1e-5)
    assert result["products"][0]["statistics"]["mean"] == pytest.approx(expected_evi)
