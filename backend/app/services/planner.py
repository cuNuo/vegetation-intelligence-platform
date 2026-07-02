# backend/app/services/planner.py
# 文件说明：计算引擎自动选择器。
# 主要职责：按像元数、指数数、CUDA 和用户偏好选择引擎。
# 对外入口：ExecutionPlanner、ExecutionDecision、has_cuda。
# 依赖边界：只做可解释决策，不执行计算。

"""依据数据规模和硬件能力选择计算引擎。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EngineName = Literal["auto", "numpy", "joblib", "torch"]


@dataclass(slots=True)
class ExecutionDecision:
    """封装 ExecutionDecision 相关状态、约束和可复用行为。"""
    requested: EngineName
    selected: Literal["numpy", "joblib", "torch"]
    reason: str
    estimated_memory_mb: float


def has_cuda() -> bool:
    """执行 has_cuda 对应的领域操作并返回结构化结果。"""
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


class ExecutionPlanner:
    """采用保守阈值，避免小任务因GPU传输产生负加速。"""

    def choose(
        self,
        width: int,
        height: int,
        band_count: int,
        index_count: int,
        requested: EngineName = "auto",
        is_synchronous: bool = False,
    ) -> ExecutionDecision:
        """按照显式请求或规模阈值选择实际计算引擎。"""
        pixels = width * height
        estimated_memory_mb = pixels * (band_count + index_count) * 4 / 1024**2

        if requested != "auto":
            selected = requested
            reason = f"用户指定{requested}引擎"
            if requested == "torch" and not has_cuda():
                selected = "joblib"
                reason = "用户指定torch，但CUDA不可用，预先回退joblib"
            return ExecutionDecision(requested, selected, reason, estimated_memory_mb)

        if is_synchronous or pixels < 2_000_000:
            return ExecutionDecision(
                requested, "numpy", "小型或同步任务优先降低调度开销", estimated_memory_mb
            )
        if has_cuda() and (pixels >= 20_000_000 or index_count >= 4):
            return ExecutionDecision(
                requested, "torch", "大型或多指数任务且检测到CUDA", estimated_memory_mb
            )
        return ExecutionDecision(
            requested, "joblib", "中大型任务使用CPU线程并行", estimated_memory_mb
        )
