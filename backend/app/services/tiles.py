# backend/app/services/tiles.py
# 文件说明：GeoTIFF/COG 动态瓦片渲染、路径约束与内存瓦片缓存服务。
"""GeoTIFF/COG 动态瓦片渲染服务。"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from app.settings import settings

WEB_MERCATOR_LIMIT = 20037508.342789244
TILE_SIZE = 256


def resolve_tile_key(key: str) -> Path:
    """把前端 objectKey 安全解析到 data_dir 下的本地文件。"""
    normalized = key.replace("\\", "/").lstrip("/")
    target = (settings.data_dir / normalized).resolve()
    data_root = settings.data_dir.resolve()
    if data_root not in target.parents and target != data_root:
        raise FileNotFoundError("瓦片资源越界")
    if not target.is_file():
        raise FileNotFoundError(f"瓦片资源不存在: {normalized}")
    return target


def render_geotiff_tile(key: str, z: int, x: int, y: int) -> bytes:
    """从 GeoTIFF/COG 按 XYZ 瓦片读取并渲染 PNG。"""
    source_path = resolve_tile_key(key)
    stat = source_path.stat()
    return _render_geotiff_tile_cached(key, z, x, y, stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=512)
def _render_geotiff_tile_cached(
    key: str,
    z: int,
    x: int,
    y: int,
    mtime_ns: int,
    size: int,
) -> bytes:
    """缓存最近访问的 TIF 瓦片；mtime/size 参与键，文件更新后自动失效。"""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject

    source_path = resolve_tile_key(key)
    tile_bounds = _tile_bounds_mercator(z, x, y)
    with rasterio.open(source_path) as dataset:
        if not dataset.crs:
            return _empty_tile()
        indexes = _display_indexes(dataset.count)
        stretches = _tile_stretches_cached(key, mtime_ns, size, tuple(indexes))
        tile_transform = from_bounds(*tile_bounds, TILE_SIZE, TILE_SIZE)
        bands = []
        for index in indexes:
            destination = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype=np.float32)
            reproject(
                source=rasterio.band(dataset, index),
                destination=destination,
                src_transform=dataset.transform,
                src_crs=dataset.crs,
                src_nodata=dataset.nodata,
                dst_transform=tile_transform,
                dst_crs="EPSG:3857",
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )
            bands.append(destination)
    data = np.ma.masked_invalid(np.stack(bands))
    return _render_array(data, stretches)


@lru_cache(maxsize=64)
def _tile_stretches_cached(
    key: str,
    mtime_ns: int,
    size: int,
    indexes: tuple[int, ...],
) -> tuple[tuple[float, float], ...]:
    """为同一影像计算一次显示拉伸范围，避免每个瓦片单独拉伸造成色差。"""
    import rasterio
    from rasterio.enums import Resampling

    del mtime_ns, size
    source_path = resolve_tile_key(key)
    with rasterio.open(source_path) as dataset:
        scale = min(1.0, 1024 / max(dataset.width, dataset.height))
        height = max(1, int(dataset.height * scale))
        width = max(1, int(dataset.width * scale))
        stretches = []
        for index in indexes:
            array = dataset.read(
                index,
                out_shape=(height, width),
                out_dtype="float32",
                resampling=Resampling.average,
            )
            valid = dataset.read_masks(index, out_shape=(height, width)) > 0
            if dataset.nodata is not None:
                valid &= ~np.isclose(array, dataset.nodata)
            valid &= np.isfinite(array)
            if not valid.any():
                stretches.append((0.0, 1.0))
                continue
            values = array[valid]
            low, high = np.percentile(values, [2, 98])
            if not np.isfinite(low) or not np.isfinite(high) or high <= low:
                low = float(np.nanmin(values))
                high = float(np.nanmax(values))
            if high <= low:
                high = low + 1.0
            stretches.append((float(low), float(high)))
    return tuple(stretches)


def _tile_bounds_mercator(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    scale = 2**z
    tile_span = WEB_MERCATOR_LIMIT * 2 / scale
    west = -WEB_MERCATOR_LIMIT + x * tile_span
    east = west + tile_span
    north = WEB_MERCATOR_LIMIT - y * tile_span
    south = north - tile_span
    return west, south, east, north


def _display_indexes(count: int) -> list[int]:
    if count >= 3:
        return [3, 2, 1]
    return [1]


def _render_array(data: np.ma.MaskedArray, stretches: tuple[tuple[float, float], ...]) -> bytes:
    mask = np.ma.getmaskarray(data)
    if data.shape[0] == 1:
        valid = ~mask[0] & np.isfinite(data[0])
        rgba = _render_single_band(
            np.asarray(data[0].filled(np.nan), dtype=np.float32),
            valid,
            stretches[0] if stretches else None,
        )
    else:
        valid = ~np.logical_or.reduce(mask) & np.all(np.isfinite(data.filled(np.nan)), axis=0)
        rgba = _render_rgb(np.asarray(data.filled(np.nan), dtype=np.float32), valid, stretches)
    if not valid.any():
        return _empty_tile()
    image = Image.fromarray(rgba, mode="RGBA")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _render_rgb(
    data: np.ndarray,
    valid: np.ndarray,
    stretches: tuple[tuple[float, float], ...],
) -> np.ndarray:
    rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
    for channel in range(3):
        rgba[..., channel] = _stretch(
            data[channel],
            valid,
            stretches[channel] if channel < len(stretches) else None,
        )
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return rgba


def _render_single_band(
    array: np.ndarray,
    valid: np.ndarray,
    stretch: tuple[float, float] | None,
) -> np.ndarray:
    rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
    stretched = _stretch(array, valid, stretch)
    rgba[..., 0] = np.clip(38 + stretched * 0.55, 0, 255).astype(np.uint8)
    rgba[..., 1] = np.clip(84 + stretched * 0.62, 0, 255).astype(np.uint8)
    rgba[..., 2] = np.clip(42 + (255 - stretched) * 0.26, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return rgba


def _stretch(
    array: np.ndarray,
    valid: np.ndarray,
    stretch: tuple[float, float] | None,
) -> np.ndarray:
    if not valid.any():
        return np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)
    if stretch is None:
        values = array[valid]
        low, high = np.percentile(values, [2, 98])
    else:
        low, high = stretch
    normalized = np.clip((array - low) / max(high - low, 1e-6), 0, 1)
    return np.where(valid, normalized * 255, 0).astype(np.uint8)


def _empty_tile() -> bytes:
    image = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
