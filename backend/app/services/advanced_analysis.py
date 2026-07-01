"""安全自定义公式、分块变化检测与GeoJSON地块统计。"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import numpy as np

ALLOWED_FUNCTIONS = {"abs", "sqrt", "minimum", "maximum"}
ALLOWED_OPERATORS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.USub,
    ast.UAdd,
)


class SafeExpressionValidator(ast.NodeVisitor):
    def __init__(self, allowed_names: set[str]) -> None:
        self.allowed_names = allowed_names

    def visit_Name(self, node: ast.Name) -> None:
        if node.id not in self.allowed_names and node.id not in ALLOWED_FUNCTIONS:
            raise ValueError(f"表达式包含未允许名称: {node.id}")

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
            raise ValueError("只允许abs、sqrt、minimum、maximum函数")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if not isinstance(node.op, ALLOWED_OPERATORS):
            raise ValueError(f"不允许的运算符: {type(node.op).__name__}")
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if not isinstance(node.op, ALLOWED_OPERATORS):
            raise ValueError(f"不允许的单目运算符: {type(node.op).__name__}")
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        forbidden = (
            ast.Attribute,
            ast.Subscript,
            ast.Lambda,
            ast.Dict,
            ast.List,
            ast.Tuple,
            ast.Compare,
            ast.BoolOp,
        )
        if isinstance(node, forbidden):
            raise ValueError(f"不允许的表达式结构: {type(node).__name__}")
        super().generic_visit(node)


def validate_custom_expression(expression: str, allowed_bands: list[str]) -> dict[str, Any]:
    tree = ast.parse(expression, mode="eval")
    SafeExpressionValidator(set(allowed_bands)).visit(tree)
    names = sorted(
        {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id in allowed_bands
        }
    )
    return {"valid": True, "normalizedExpression": ast.unparse(tree), "requiredBands": names}


def evaluate_custom_expression(
    expression: str, arrays: dict[str, np.ndarray]
) -> np.ndarray:
    validate_custom_expression(expression, list(arrays))
    functions = {
        "abs": np.abs,
        "sqrt": np.sqrt,
        "minimum": np.minimum,
        "maximum": np.maximum,
    }
    result = eval(  # noqa: S307 - AST白名单校验后在空builtins环境执行
        compile(ast.parse(expression, mode="eval"), "<custom-index>", "eval"),
        {"__builtins__": {}},
        {**functions, **arrays},
    )
    return np.nan_to_num(np.asarray(result, dtype=np.float32), nan=-9999.0)


def detect_change(
    before_path: str,
    after_path: str,
    output_path: str,
    decrease_threshold: float,
    increase_threshold: float,
) -> dict[str, Any]:
    import rasterio

    before_resolved = Path(before_path).resolve()
    after_resolved = Path(after_path).resolve()
    output_resolved = Path(output_path).resolve()
    output_resolved.parent.mkdir(parents=True, exist_ok=True)
    counts = {"decrease": 0, "stable": 0, "increase": 0}

    with (
        rasterio.open(before_resolved) as before,
        rasterio.open(after_resolved) as after,
    ):
        if (
            before.width != after.width
            or before.height != after.height
            or before.transform != after.transform
            or before.crs != after.crs
        ):
            raise ValueError("两期结果必须具有相同尺寸、CRS和仿射变换")
        profile = before.profile.copy()
        profile.update(dtype="float32", count=2, nodata=-9999.0, compress="deflate")
        with rasterio.open(output_resolved, "w", **profile) as output:
            output.set_band_description(1, "difference")
            output.set_band_description(2, "change_class")
            for _, window in before.block_windows(1):
                before_array = before.read(1, window=window, out_dtype="float32")
                after_array = after.read(1, window=window, out_dtype="float32")
                invalid = (before_array == before.nodata) | (after_array == after.nodata)
                difference = after_array - before_array
                classes = np.zeros_like(difference, dtype=np.float32)
                classes[difference <= decrease_threshold] = -1
                classes[difference >= increase_threshold] = 1
                difference[invalid] = -9999
                classes[invalid] = -9999
                counts["decrease"] += int(np.count_nonzero(classes == -1))
                counts["stable"] += int(np.count_nonzero(classes == 0))
                counts["increase"] += int(np.count_nonzero(classes == 1))
                output.write(difference, 1, window=window)
                output.write(classes, 2, window=window)
    return {"outputPath": str(output_resolved), "classPixelCounts": counts}


def calculate_zonal_statistics(raster_path: str, geojson: dict[str, Any]) -> dict[str, Any]:
    import rasterio
    from rasterio.mask import mask

    features = geojson.get("features", [])
    if not features:
        raise ValueError("GeoJSON必须包含至少一个Feature")
    results = []
    with rasterio.open(Path(raster_path).resolve()) as dataset:
        for position, feature in enumerate(features):
            clipped, _ = mask(dataset, [feature["geometry"]], crop=True, filled=False)
            values = clipped[0].compressed()
            results.append(
                {
                    "id": feature.get("id", position),
                    "properties": feature.get("properties", {}),
                    "validPixels": int(values.size),
                    "mean": float(values.mean()) if values.size else None,
                    "median": float(np.median(values)) if values.size else None,
                    "standardDeviation": float(values.std()) if values.size else None,
                }
            )
    return {"zones": results}
