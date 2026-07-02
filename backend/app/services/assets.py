"""本地资产检查与可选MinIO访问。"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.settings import settings


def _geographic_bounds(dataset: Any) -> list[float] | None:
    if not dataset.crs:
        return None
    from rasterio.warp import transform_bounds

    return list(transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds))


def inspect_raster(path: str) -> dict[str, Any]:
    import rasterio

    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"影像不存在: {resolved}")
    with rasterio.open(resolved) as dataset:
        geographic_bounds = _geographic_bounds(dataset)
        band_metadata = [
            {
                "band": band_index,
                "description": dataset.descriptions[band_index - 1],
                "tags": dataset.tags(band_index),
                "wavelengthNm": _extract_wavelength_nm(
                    dataset.descriptions[band_index - 1],
                    dataset.tags(band_index),
                ),
            }
            for band_index in range(1, dataset.count + 1)
        ]
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
            "descriptions": list(dataset.descriptions),
            "bandMetadata": band_metadata,
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
    metadata = inspect_raster(str(target))
    preview_path = settings.data_dir / "previews" / f"{target.stem}.png"
    write_asset_preview(target, preview_path)
    return {
        "objectKey": f"inputs/{safe_name}",
        "localPath": str(target),
        "filename": file.filename,
        "size": target.stat().st_size,
        "metadata": metadata,
        "previewPath": str(preview_path),
    }

def upload_artifact(path: Path, object_key: str) -> str | None:
    """部署模式上传派生产品；开发模式保留本地文件。"""
    if not settings.minio_enabled:
        return None
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
