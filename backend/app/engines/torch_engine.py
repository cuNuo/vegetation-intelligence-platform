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
        self.torch = torch_module

    def abs(self, value: Any) -> Any:
        return self.torch.abs(value)

    def sqrt(self, value: Any) -> Any:
        return self.torch.sqrt(value)

    def sign(self, value: Any) -> Any:
        return self.torch.sign(value)

    def where(self, condition: Any, yes: Any, no: Any) -> Any:
        if not self.torch.is_tensor(yes):
            yes = self.torch.as_tensor(yes, dtype=no.dtype, device=no.device)
        if not self.torch.is_tensor(no):
            no = self.torch.as_tensor(no, dtype=yes.dtype, device=yes.device)
        return self.torch.where(condition, yes, no)

    def maximum(self, left: Any, right: Any) -> Any:
        if not self.torch.is_tensor(right):
            right = self.torch.as_tensor(right, dtype=left.dtype, device=left.device)
        return self.torch.maximum(left, right)


class TorchEngine:
    name = "torch"

    def __init__(self, allow_amp: bool = False) -> None:
        self.allow_amp = allow_amp

    def compute(
        self,
        definitions: list[IndexDefinition],
        bands: dict[str, np.ndarray],
        parameters: dict[str, dict[str, float]] | None = None,
    ) -> EngineResult:
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
                    arrays[definition.id] = sanitize_result(result.float().cpu().numpy())
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
        result = JoblibEngine().compute(definitions, bands, parameters)
        result.fallback_reason = f"{reason}，已回退{result.engine}"
        return result
