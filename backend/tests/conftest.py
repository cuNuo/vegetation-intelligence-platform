from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.settings import settings


@pytest.fixture(autouse=True)
def isolate_external_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """单元测试不依赖本机.env里的外部服务凭据，保证断言稳定。"""
    monkeypatch.setattr(settings, "database_url", None)
    monkeypatch.setattr(settings, "minio_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "openai_base_url", None)


@pytest.fixture
def sample_raster(tmp_path: Path) -> Path:
    """生成包含Blue、Green、Red、NIR四波段的测试GeoTIFF。"""
    source_path = tmp_path / "sample.tif"
    profile = {
        "driver": "GTiff",
        "width": 96,
        "height": 64,
        "count": 4,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(100, 30, 0.001, 0.001),
        "nodata": -9999,
    }
    with rasterio.open(source_path, "w", **profile) as dataset:
        dataset.write(np.full((64, 96), 0.1, dtype=np.float32), 1)
        dataset.write(np.full((64, 96), 0.2, dtype=np.float32), 2)
        dataset.write(np.full((64, 96), 0.3, dtype=np.float32), 3)
        dataset.write(np.full((64, 96), 0.7, dtype=np.float32), 4)
    return source_path
