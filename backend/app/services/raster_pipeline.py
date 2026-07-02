# backend/app/services/raster_pipeline.py
# 文件说明：Rasterio 分块计算、统计、预览与溯源流水线。
# 主要职责：验证波段、生成窗口、共享读取、计算、写出和登记产物。
# 对外入口：RasterTask、RasterPipeline、task_as_dict。
# 依赖边界：所有执行路径共用的唯一栅格实现。

"""Rasterio分块计算、统计、预览和可复现清单。"""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from app.core.indices import get_index
from app.engines.joblib_engine import JoblibEngine
from app.engines.numpy_engine import NumpyEngine
from app.engines.torch_engine import TorchEngine
from app.services.assets import upload_artifact
from app.services.planner import EngineName, ExecutionPlanner

ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]


@dataclass(slots=True)
class RasterTask:
    """封装 RasterTask 相关状态、约束和可复用行为。"""
    source_path: str
    output_dir: str
    indices: list[str]
    bands: dict[str, int]
    engine: EngineName = "auto"
    block_size: int = 1024
    parameters: dict[str, dict[str, float]] | None = None
    preview: bool = True
    statistics: bool = True
    synchronous: bool = False


def _file_sha256(path: Path) -> str:
    """完成模块内部的 file_sha256 辅助处理。"""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _statistics(array: np.ndarray, nodata: float) -> dict[str, Any]:
    """完成模块内部的 statistics 辅助处理。"""
    valid = array[np.isfinite(array) & (array != nodata)]
    if valid.size == 0:
        return {
            "validPixels": 0,
            "minimum": None,
            "maximum": None,
            "mean": None,
            "median": None,
            "standardDeviation": None,
            "histogram": {"counts": [], "edges": []},
        }
    counts, edges = np.histogram(valid, bins=32)
    return {
        "validPixels": int(valid.size),
        "minimum": float(valid.min()),
        "maximum": float(valid.max()),
        "mean": float(valid.mean()),
        "median": float(np.median(valid)),
        "standardDeviation": float(valid.std()),
        "histogram": {
            "counts": counts.astype(int).tolist(),
            "edges": edges.astype(float).tolist(),
        },
    }


def _infer_reflectance_divisor(array: np.ndarray, dtype_name: str) -> float | None:
    """为缺少 scale 标签的常见整数反射率影像推断归一化分母。"""
    if np.issubdtype(np.dtype(dtype_name), np.floating):
        return None
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return None
    high = float(np.nanpercentile(finite, 98))
    if high <= 1.5:
        return None
    if high <= 255:
        return 255.0
    if high <= 12000:
        return 10000.0
    dtype = np.dtype(dtype_name)
    if np.issubdtype(dtype, np.integer):
        return float(np.iinfo(dtype).max)
    return None


def _to_reflectance(array: np.ndarray, dtype_name: str, scale: float, offset: float) -> np.ndarray:
    """把源波段转为 0-1 反射率语义，供带常数项的指数公式使用。"""
    result = array.astype(np.float32, copy=False)
    if scale not in (0, 1) or offset != 0:
        return result * np.float32(scale) + np.float32(offset)
    divisor = _infer_reflectance_divisor(result, dtype_name)
    return result / np.float32(divisor) if divisor else result


def _write_preview(source_path: Path, target_path: Path, nodata: float) -> None:
    """完成模块内部的 write_preview 辅助处理。"""
    import rasterio
    from PIL import Image

    with rasterio.open(source_path) as dataset:
        scale = min(1.0, 1200 / max(dataset.width, dataset.height))
        height = max(1, int(dataset.height * scale))
        width = max(1, int(dataset.width * scale))
        array = dataset.read(1, out_shape=(height, width)).astype(np.float32)
    valid_mask = np.isfinite(array) & (array != nodata)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    if valid_mask.any():
        low, high = np.percentile(array[valid_mask], [2, 98])
        normalized = np.clip((array - low) / max(high - low, 1e-6), 0, 1)
        rgba[..., 0] = (230 * (1 - normalized)).astype(np.uint8)
        rgba[..., 1] = (65 + 165 * normalized).astype(np.uint8)
        rgba[..., 2] = (45 * (1 - normalized)).astype(np.uint8)
        rgba[..., 3] = np.where(valid_mask, 220, 0).astype(np.uint8)
    Image.fromarray(rgba).save(target_path)


class RasterPipeline:
    """协调窗口读取、共享计算、顺序写出、统计和产物登记。"""
    nodata = -9999.0

    def __init__(self) -> None:
        """初始化实例依赖、运行状态和可配置参数。"""
        self.planner = ExecutionPlanner()

    def run(
        self,
        task: RasterTask,
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
    ) -> dict[str, Any]:
        """执行完整任务或基准流程，并返回结构化结果。"""
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import transform_bounds
        from rasterio.windows import Window

        started_at = perf_counter()
        source_path = Path(task.source_path).resolve()
        output_dir = Path(task.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        definitions = [get_index(index_id) for index_id in task.indices]

        # 先对全部指数求逻辑波段并集。同一窗口中每个物理波段只读取一次，
        # 后续多个指数共享 arrays，避免“指数数量 × 磁盘读取次数”的 I/O 放大。
        required_bands = sorted({band for item in definitions for band in item.required_bands})
        missing_mapping = set(required_bands) - task.bands.keys()
        if missing_mapping:
            raise ValueError(f"缺少逻辑波段映射: {', '.join(sorted(missing_mapping))}")

        with rasterio.open(source_path) as source:
            invalid_numbers = [
                task.bands[logical_name]
                for logical_name in required_bands
                if task.bands[logical_name] < 1 or task.bands[logical_name] > source.count
            ]
            if invalid_numbers:
                raise ValueError(f"波段号超出影像范围: {invalid_numbers}")

            decision = self.planner.choose(
                source.width,
                source.height,
                len(required_bands),
                len(definitions),
                task.engine,
                task.synchronous,
            )
            engine = self._create_engine(decision.selected)
            profile = source.profile.copy()
            block_size = max(128, min(2048, task.block_size))
            # GeoTIFF 的 tile 宽高要求为 16 的倍数。请求值不满足时使用稳定的
            # 1024 写块，但计算窗口仍使用用户请求值，两者职责彼此独立。
            profile.update(
                driver="GTiff",
                count=1,
                dtype="float32",
                nodata=self.nodata,
                compress="deflate",
                predictor=3,
                tiled=True,
                blockxsize=block_size if block_size % 16 == 0 else 1024,
                blockysize=block_size if block_size % 16 == 0 else 1024,
                BIGTIFF="IF_SAFER",
            )
            output_paths = {
                item.id: output_dir / f"{source_path.stem}_{item.id}.tif" for item in definitions
            }
            writers = {
                index_id: rasterio.open(path, "w", **profile)
                for index_id, path in output_paths.items()
            }
            windows = [
                Window(
                    column,
                    row,
                    min(block_size, source.width - column),
                    min(block_size, source.height - row),
                )
                for row in range(0, source.height, block_size)
                for column in range(0, source.width, block_size)
            ]
            actual_engine = decision.selected
            fallback_reasons: list[str] = []
            try:
                for current, window in enumerate(windows, start=1):
                    if is_cancelled and is_cancelled():
                        raise RuntimeError("任务已取消")
                    arrays: dict[str, np.ndarray] = {}
                    masks: list[np.ndarray] = []
                    for logical_name in required_bands:
                        band_number = task.bands[logical_name]
                        band_index = band_number - 1
                        array = source.read(band_number, window=window, out_dtype="float32")
                        # Rasterio mask 与显式 nodata 都表示无效像元。计算前统一改为
                        # NaN，使所有数组引擎使用相同语义；写出前再改为固定 nodata。
                        invalid_mask = source.read_masks(band_number, window=window) == 0
                        if source.nodata is not None:
                            invalid_mask |= np.isclose(array, source.nodata)
                        array = _to_reflectance(
                            array,
                            source.dtypes[band_index],
                            source.scales[band_index],
                            source.offsets[band_index],
                        )
                        array[invalid_mask] = np.nan
                        arrays[logical_name] = array
                        masks.append(invalid_mask)
                    result = engine.compute(definitions, arrays, task.parameters)
                    actual_engine = result.engine
                    if result.fallback_reason:
                        fallback_reasons.append(result.fallback_reason)
                    # 任一必需波段无效时，该像元的所有指数均不可信，因此采用逻辑或
                    # 合并掩膜，而不是让不同指数产生相互矛盾的有效区域。
                    combined_mask = np.logical_or.reduce(masks)
                    for index_id, array in result.arrays.items():
                        array[combined_mask] = self.nodata
                        writers[index_id].write(array, 1, window=window)
                    if on_progress:
                        on_progress(current, len(windows), f"正在计算窗口 {current}/{len(windows)}")
            finally:
                for writer in writers.values():
                    writer.close()

        products: list[dict[str, Any]] = []
        for definition in definitions:
            output_path = output_paths[definition.id]
            with rasterio.open(output_path, "r+") as dataset:
                # 结果 overview 用 average 降采样，服务于缩放浏览；它不会改变
                # 全分辨率主波段，因此统计和下载仍基于原始计算结果。
                factors = [
                    factor
                    for factor in (2, 4, 8, 16)
                    if min(dataset.width, dataset.height) > factor
                ]
                if factors:
                    dataset.build_overviews(factors, Resampling.average)
                    dataset.update_tags(ns="rio_overview", resampling="average")
                crs = dataset.crs.to_string() if dataset.crs else None
                bounds = (
                    list(transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds))
                    if dataset.crs
                    else list(dataset.bounds)
                )
                array = dataset.read(1) if task.statistics else np.empty(0, dtype=np.float32)
            preview_path = output_dir / f"{output_path.stem}.png"
            if task.preview:
                _write_preview(output_path, preview_path, self.nodata)
            output_object_key = upload_artifact(
                output_path, f"outputs/{output_dir.name}/{output_path.name}"
            )
            preview_object_key = (
                upload_artifact(
                    preview_path,
                    f"outputs/{output_dir.name}/{preview_path.name}",
                )
                if task.preview
                else None
            )
            products.append(
                {
                    "index": definition.id,
                    "name": definition.name,
                    "path": str(output_path),
                    "previewPath": str(preview_path) if task.preview else None,
                    "objectKey": output_object_key,
                    "previewObjectKey": preview_object_key,
                    "bounds": bounds,
                    "crs": crs,
                    "statistics": _statistics(array, self.nodata) if task.statistics else None,
                }
            )

        # manifest 同时记录输入哈希、请求引擎、实际引擎与回退原因，
        # 用于答辩复现、结果追责和后续性能基准分析。
        manifest = {
            "source": str(source_path),
            "sourceSha256": _file_sha256(source_path),
            "indices": task.indices,
            "bands": task.bands,
            "parameters": task.parameters or {},
            "requestedEngine": task.engine,
            "selectedEngine": decision.selected,
            "actualEngine": actual_engine,
            "selectionReason": decision.reason,
            "fallbackReasons": sorted(set(fallback_reasons)),
            "blockSize": task.block_size,
            "durationSeconds": round(perf_counter() - started_at, 4),
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "products": products,
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest["manifestPath"] = str(manifest_path)
        if on_progress:
            on_progress(1, 1, "处理完成")
        return manifest

    @staticmethod
    def _create_engine(name: str) -> Any:
        """完成模块内部的 create_engine 辅助处理。"""
        if name == "torch":
            return TorchEngine()
        if name == "joblib":
            return JoblibEngine()
        return NumpyEngine()


def task_as_dict(task: RasterTask) -> dict[str, Any]:
    """执行 task_as_dict 对应的领域操作并返回结构化结果。"""
    return asdict(task)
