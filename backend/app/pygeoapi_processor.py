# backend/app/pygeoapi_processor.py
# 文件说明：pygeoapi 动态植被指数处理器。
# 主要职责：把标准 Process 输入转换为 RasterTask。
# 对外入口：SpectralIndexProcessor、PROCESS_METADATA。
# 依赖边界：复用注册表与 RasterPipeline。

"""pygeoapi动态植被指数Processor插件。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from app.core.indices import get_index
from app.services.raster_pipeline import RasterPipeline, RasterTask
from app.settings import settings

PROCESS_METADATA = {
    "version": "1.0.0",
    "id": "spectral-index",
    "title": {"en": "Spectral index", "zh": "植被指数动态处理器"},
    "description": {"en": "Windowed vegetation index calculation"},
    "jobControlOptions": ["sync-execute", "async-execute"],
    "keywords": ["vegetation", "raster", "remote-sensing"],
    "inputs": {
        "source": {
            "title": "GeoTIFF path",
            "schema": {"type": "string"},
            "minOccurs": 1,
            "maxOccurs": 1,
        },
        "index": {
            "title": "Index identifier",
            "schema": {"type": "string"},
            "minOccurs": 1,
            "maxOccurs": 1,
        },
        "bands": {
            "title": "Logical band mapping",
            "schema": {"type": "object"},
            "minOccurs": 1,
            "maxOccurs": 1,
        },
    },
    "outputs": {
        "result": {
            "title": "Processing result",
            "schema": {"type": "object", "contentMediaType": "application/json"},
        }
    },
}


class SpectralIndexProcessor(BaseProcessor):
    """单个类动态处理全部注册指数。"""

    def __init__(self, processor_def: dict[str, Any]) -> None:
        """初始化实例依赖、运行状态和可配置参数。"""
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """解析标准处理输入，复用分块流水线并返回 JSON 结果。"""
        try:
            index_id = str(data["index"]).lower()
            get_index(index_id)
            source = Path(str(data["source"])).resolve()
            output_dir = settings.data_dir / "outputs" / f"pygeoapi-{uuid.uuid4().hex}"
            result = RasterPipeline().run(
                RasterTask(
                    source_path=str(source),
                    output_dir=str(output_dir),
                    indices=[index_id],
                    bands={key: int(value) for key, value in data["bands"].items()},
                    engine=str(data.get("engine", "auto")),
                )
            )
            return "application/json", result
        except Exception as error:
            raise ProcessorExecuteError(str(error)) from error

    def __repr__(self) -> str:
        """完成模块内部的 repr__ 辅助处理。"""
        return "<SpectralIndexProcessor>"
