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
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _statistics(array: np.ndarray, nodata: float) -> dict[str, Any]:
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


def _write_preview(source_path: Path, target_path: Path, nodata: float) -> None:
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
    nodata = -9999.0

    def __init__(self) -> None:
        self.planner = ExecutionPlanner()

    def run(
        self,
        task: RasterTask,
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
    ) -> dict[str, Any]:
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import transform_bounds
        from rasterio.windows import Window

        started_at = perf_counter()
        source_path = Path(task.source_path).resolve()
        output_dir = Path(task.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        definitions = [get_index(index_id) for index_id in task.indices]

        required_bands = sorted({band for item in definitions for band in item.required_bands})
        missing_mapping = set(required_bands) - task.bands.keys()
        if missing_mapping:
            raise ValueError(f"缺少逻辑波段映射: {', '.join(sorted(missing_mapping))}")

        with rasterio.open(source_path) as source:
            invalid_numbers = [
                number for number in task.bands.values() if number < 1 or number > source.count
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
                        array = source.read(band_number, window=window, out_dtype="float32")
                        invalid_mask = source.read_masks(band_number, window=window) == 0
                        if source.nodata is not None:
                            invalid_mask |= np.isclose(array, source.nodata)
                        array[invalid_mask] = np.nan
                        arrays[logical_name] = array
                        masks.append(invalid_mask)
                    result = engine.compute(definitions, arrays, task.parameters)
                    actual_engine = result.engine
                    if result.fallback_reason:
                        fallback_reasons.append(result.fallback_reason)
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
        if name == "torch":
            return TorchEngine()
        if name == "joblib":
            return JoblibEngine()
        return NumpyEngine()


def task_as_dict(task: RasterTask) -> dict[str, Any]:
    return asdict(task)
