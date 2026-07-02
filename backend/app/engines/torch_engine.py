# backend/app/engines/torch_engine.py
# 文件说明：PyTorch CUDA 计算与回退引擎。
# 主要职责：迁移窗口数组到 GPU、执行公式并回传 CPU。
# 对外入口：TorchArrayAPI、TorchEngine。
# 依赖边界：不构建梯度，失败回退 Joblib。

"""PyTorch CUDA分块计算引擎。"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any

import numpy as np

from app.core.indices import IndexDefinition
from app.engines.base import EngineResult, sanitize_result
from app.engines.joblib_engine import JoblibEngine


class TorchArrayAPI:
    """补齐公式所需的轻量数组API，处理PyTorch与NumPy的标量差异。"""

    def __init__(self, torch_module: Any) -> None:
        """初始化实例依赖、运行状态和可配置参数。"""
        self.torch = torch_module

    def abs(self, value: Any) -> Any:
        """执行 abs 对应的领域操作并返回结构化结果。"""
        return self.torch.abs(value)

    def sqrt(self, value: Any) -> Any:
        """执行 sqrt 对应的领域操作并返回结构化结果。"""
        return self.torch.sqrt(value)

    def sign(self, value: Any) -> Any:
        """执行 sign 对应的领域操作并返回结构化结果。"""
        return self.torch.sign(value)

    def where(self, condition: Any, yes: Any, no: Any) -> Any:
        """执行 where 对应的领域操作并返回结构化结果。"""
        if not self.torch.is_tensor(yes):
            yes = self.torch.as_tensor(yes, dtype=no.dtype, device=no.device)
        if not self.torch.is_tensor(no):
            no = self.torch.as_tensor(no, dtype=yes.dtype, device=yes.device)
        return self.torch.where(condition, yes, no)

    def maximum(self, left: Any, right: Any) -> Any:
        """执行 maximum 对应的领域操作并返回结构化结果。"""
        if not self.torch.is_tensor(right):
            right = self.torch.as_tensor(right, dtype=left.dtype, device=left.device)
        return self.torch.maximum(left, right)


class TorchEngine:
    """封装 TorchEngine 相关状态、约束和可复用行为。"""
    name = "torch"

    def __init__(self, allow_amp: bool = False) -> None:
        """初始化实例依赖、运行状态和可配置参数。"""
        self.allow_amp = allow_amp

    def compute(
        self,
        definitions: list[IndexDefinition],
        bands: dict[str, np.ndarray],
        parameters: dict[str, dict[str, float]] | None = None,
    ) -> EngineResult:
        """计算一个窗口内的指数数组并返回统一结果结构。"""
        try:
            import torch
        except ImportError:
            return self._fallback(definitions, bands, parameters, "PyTorch未安装")

        if not torch.cuda.is_available():
            return self._fallback(definitions, bands, parameters, "CUDA不可用")

        try:
            device = torch.device("cuda")
            tensor_bands = {
                name: torch.as_tensor(array, dtype=torch.float32, device=device)
                for name, array in bands.items()
            }
            xp = TorchArrayAPI(torch)
            amp_enabled = self.allow_amp and all(item.amp_safe for item in definitions)
            amp_context = (
                torch.autocast(device_type="cuda", dtype=torch.float16)
                if amp_enabled
                else nullcontext()
            )
            arrays: dict[str, np.ndarray] = {}
            with torch.inference_mode(), amp_context:
                for definition in definitions:
                    result = definition.calculate(
                        xp,
                        tensor_bands,
                        (parameters or {}).get(definition.id),
                    )
                    arrays[definition.id] = sanitize_result(
                        result.float().cpu().numpy(),
                        expected_range=definition.expected_range,
                    )
            return EngineResult(arrays=arrays, engine=self.name)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            return self._fallback(definitions, bands, parameters, "GPU显存不足")
        except RuntimeError as error:
            return self._fallback(definitions, bands, parameters, f"CUDA执行失败: {error}")

    @staticmethod
    def _fallback(
        definitions: list[IndexDefinition],
        bands: dict[str, np.ndarray],
        parameters: dict[str, dict[str, float]] | None,
        reason: str,
    ) -> EngineResult:
        """完成模块内部的 fallback 辅助处理。"""
        result = JoblibEngine().compute(definitions, bands, parameters)
        result.fallback_reason = f"{reason}，已回退{result.engine}"
        return result
