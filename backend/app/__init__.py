"""植被指数智能分析平台后端。"""

import os
from importlib.util import find_spec
from pathlib import Path

__version__ = "0.1.0"


def _repair_proj_data_path() -> None:
    """修复外部环境变量指向不存在PROJ数据库时的运行环境。"""
    configured = Path(os.environ.get("PROJ_DATA") or os.environ.get("PROJ_LIB") or "")
    if configured.joinpath("proj.db").is_file():
        return
    rasterio_spec = find_spec("rasterio")
    if not rasterio_spec or not rasterio_spec.origin:
        return
    bundled = Path(rasterio_spec.origin).parent / "proj_data"
    if bundled.joinpath("proj.db").is_file():
        os.environ["PROJ_DATA"] = str(bundled)
        os.environ["PROJ_LIB"] = str(bundled)


_repair_proj_data_path()
