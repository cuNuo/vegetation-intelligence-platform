# backend/app/services/assets.py
# 文件说明：上传影像保存、GeoTIFF 金字塔构建、元数据检查与预览生成。
"""本地资产检查与可选MinIO访问。"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.settings import settings

_SENSOR_BAND_PROFILES = (
    {
        "pattern": re.compile(r"^GF01(?:[_-]|$)", re.IGNORECASE),
        "count": 4,
        "sensor": "GF-1",
        "bands": (
            ("Blue B1", 485.0),
            ("Green B2", 555.0),
            ("Red B3", 660.0),
            ("NIR B4", 830.0),
        ),
    },
    {
        "pattern": re.compile(r"^LAD08(?:[_-]|$)", re.IGNORECASE),
        "count": 7,
        "sensor": "Landsat 8/9 OLI",
        "bands": (
            ("Coastal Aerosol B1", 443.0),
            ("Blue B2", 482.0),
            ("Green B3", 561.0),
            ("Red B4", 655.0),
            ("NIR B5", 865.0),
            ("SWIR1 B6", 1610.0),
            ("SWIR2 B7", 2200.0),
        ),
    },
    {
        "pattern": re.compile(r"^LAD09(?:[_-]|$)", re.IGNORECASE),
        "count": 7,
        "sensor": "Landsat 8/9 OLI",
        "bands": (
            ("Coastal Aerosol B1", 443.0),
            ("Blue B2", 482.0),
            ("Green B3", 561.0),
            ("Red B4", 655.0),
            ("NIR B5", 865.0),
            ("SWIR1 B6", 1610.0),
            ("SWIR2 B7", 2200.0),
        ),
    },
    {
        "pattern": re.compile(r"^SHB02(?:[_-]|$)", re.IGNORECASE),
        "count": 4,
        "sensor": "Sentinel-2A/2B MSI",
        "bands": (
            ("Blue B2", 490.0),
            ("Green B3", 560.0),
            ("Red B4", 665.0),
            ("NIR B8", 842.0),
        ),
    },
)


def _sensor_band_profile(filename: str, count: int) -> dict[str, Any] | None:
    """按受控文件名前缀识别缺少光谱元数据的测试影像。"""
    for profile in _SENSOR_BAND_PROFILES:
        if profile["count"] == count and profile["pattern"].search(filename):
            return profile
    return None


def _overview_factors(width: int, height: int) -> list[int]:
    """生成直到最长边接近 256 像素的 2 倍金字塔层级。"""
    if max(width, height) <= 512:
        return []
    factors: list[int] = []
    factor = 2
    while factor <= 128 and min(width, height) > factor:
        factors.append(factor)
        if max(width / factor, height / factor) <= 256:
            break
        factor *= 2
    return factors


def ensure_raster_overviews(path: Path) -> dict[str, Any]:
    """复用已有 overview；缺失时在受控输入 TIF 内首次构建压缩金字塔。"""
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(path) as dataset:
        desired = _overview_factors(dataset.width, dataset.height)
        existing = dataset.overviews(1) if dataset.count else []
    if not desired:
        return {"status": "not-needed", "levels": existing}
    if all(factor in existing for factor in desired):
        return {"status": "reused", "levels": existing}

    with rasterio.Env(
        COMPRESS_OVERVIEW="DEFLATE",
        INTERLEAVE_OVERVIEW="PIXEL",
        GDAL_TIFF_OVR_BLOCKSIZE="256",
    ):
        with rasterio.open(path, "r+") as dataset:
            dataset.build_overviews(desired, Resampling.average)
            dataset.update_tags(
                ns="rio_overview",
                resampling="average",
                source="upload-first-open",
            )
            levels = dataset.overviews(1) if dataset.count else []
    return {"status": "built", "levels": levels}


def _geographic_bounds(dataset: Any) -> list[float] | None:
    if not dataset.crs:
        return None
    from rasterio.warp import transform_bounds

    return list(transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds))


def inspect_raster(path: str, filename_hint: str | None = None) -> dict[str, Any]:
    import rasterio

    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"影像不存在: {resolved}")
    with rasterio.open(resolved) as dataset:
        geographic_bounds = _geographic_bounds(dataset)
        profile_filename = Path(filename_hint).name if filename_hint else resolved.name
        sensor_profile = _sensor_band_profile(profile_filename, dataset.count)
        band_metadata = []
        descriptions = []
        for band_index in range(1, dataset.count + 1):
            original_description = dataset.descriptions[band_index - 1]
            tags = dataset.tags(band_index)
            wavelength_nm = _extract_wavelength_nm(original_description, tags)
            inferred_band = sensor_profile["bands"][band_index - 1] if sensor_profile else None
            description = original_description or (inferred_band[0] if inferred_band else None)
            if wavelength_nm is None and inferred_band:
                wavelength_nm = inferred_band[1]
            descriptions.append(description)
            band_metadata.append(
                {
                    "band": band_index,
                    "description": description,
                    "tags": tags,
                    "wavelengthNm": wavelength_nm,
                }
            )
        return {
            "path": str(resolved),
            "width": dataset.width,
            "height": dataset.height,
            "count": dataset.count,
            "dtypes": list(dataset.dtypes),
            "crs": dataset.crs.to_string() if dataset.crs else None,
            "bounds": list(dataset.bounds),
            "geographicBounds": geographic_bounds,
            "resolution": list(dataset.res),
            "nodata": dataset.nodata,
            "descriptions": descriptions,
            "bandMetadata": band_metadata,
            "sensor": sensor_profile["sensor"] if sensor_profile else None,
            "bandInferenceSource": "filename-profile" if sensor_profile else None,
            "overviewLevels": dataset.overviews(1) if dataset.count else [],
            "overviewCount": len(dataset.overviews(1)) if dataset.count else 0,
        }


def _extract_wavelength_nm(description: str | None, tags: dict[str, Any]) -> float | None:
    text = " ".join(
        str(value)
        for value in [
            description,
            *tags.keys(),
            *tags.values(),
        ]
        if value is not None
    ).lower()
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(nm|nanometer|nanometers|µm|um|micrometer|micrometers)",
        text,
    )
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    return value * 1000 if unit in {"µm", "um", "micrometer", "micrometers"} else value


def write_asset_preview(source_path: Path, target_path: Path) -> None:
    import numpy as np
    import rasterio
    from PIL import Image

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(source_path) as dataset:
        scale = min(1.0, 1400 / max(dataset.width, dataset.height))
        height = max(1, int(dataset.height * scale))
        width = max(1, int(dataset.width * scale))
        if dataset.count >= 3:
            band_indexes = [3, 2, 1]
        else:
            band_indexes = [1, 1, 1]
        arrays = [
            dataset.read(index, out_shape=(height, width), out_dtype="float32")
            for index in band_indexes
        ]
        masks = [dataset.read_masks(index, out_shape=(height, width)) > 0 for index in band_indexes]
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    valid_mask = np.logical_or.reduce(masks)
    for channel, array in enumerate(arrays):
        finite = np.isfinite(array) & valid_mask
        if not finite.any():
            continue
        low, high = np.percentile(array[finite], [2, 98])
        normalized = np.clip((array - low) / max(high - low, 1e-6), 0, 1)
        rgb[..., channel] = (normalized * 255).astype(np.uint8)
    alpha = np.where(valid_mask, 230, 0).astype(np.uint8)
    Image.fromarray(np.dstack([rgb, alpha])).save(target_path)


def resolve_source(object_key: str | None, local_path: str | None) -> Path:
    if local_path:
        path = Path(local_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"本地资产不存在: {path}")
        return path
    if not object_key:
        raise ValueError("缺少资产引用")
    target = (settings.data_dir / "inputs" / Path(object_key).name).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        client.fget_object(settings.minio_bucket, object_key, str(target))
    except Exception as error:  # noqa: BLE001 - 外部存储边界
        raise FileNotFoundError(f"无法从MinIO取得对象 {object_key}: {error}") from error
    return target


def create_upload_url(object_key: str) -> dict[str, str]:
    from minio import Minio

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
    url = client.presigned_put_object(
        settings.minio_bucket,
        object_key,
        expires=timedelta(minutes=30),
    )
    return {"objectKey": object_key, "uploadUrl": url}



async def save_uploaded_asset(file: Any) -> dict[str, Any]:
    """保存浏览器上传的GeoTIFF到后端受控输入目录。"""
    suffix = Path(file.filename or "asset.tif").suffix.lower()
    if suffix not in {".tif", ".tiff"}:
        raise ValueError("仅支持GeoTIFF文件（.tif/.tiff）")
    safe_name = f"{uuid4().hex}{suffix}"
    target_dir = settings.data_dir / "inputs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = (target_dir / safe_name).resolve()
    with target.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            output.write(chunk)
    overview_info = ensure_raster_overviews(target)
    metadata = inspect_raster(str(target), filename_hint=file.filename)
    metadata["overviewStatus"] = overview_info["status"]
    preview_path = settings.data_dir / "previews" / f"{target.stem}.png"
    write_asset_preview(target, preview_path)
    return {
        "objectKey": f"inputs/{safe_name}",
        "localPath": str(target),
        "filename": file.filename,
        "size": target.stat().st_size,
        "metadata": metadata,
        "previewPath": str(preview_path),
        "previewObjectKey": f"previews/{preview_path.name}",
    }

def upload_artifact(path: Path, object_key: str) -> str | None:
    """部署模式上传派生产品；开发模式返回本地静态资源key。"""
    if not settings.minio_enabled:
        return object_key
    from minio import Minio

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
    client.fput_object(settings.minio_bucket, object_key, str(path))
    return object_key
