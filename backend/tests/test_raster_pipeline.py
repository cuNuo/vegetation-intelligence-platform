from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.services.raster_pipeline import RasterPipeline, RasterTask


def test_windowed_raster_pipeline_preserves_geometry(tmp_path: Path) -> None:
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
