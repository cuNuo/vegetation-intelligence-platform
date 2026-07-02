# backend/app/worker_tasks.py
# 文件说明：Celery Worker 栅格任务入口。
# 主要职责：反序列化任务、上报窗口进度并执行统一流水线。
# 对外入口：process_raster。
# 依赖边界：不得复制公式或另建 Worker 算法。

"""Celery Worker任务。"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from app.celery_app import celery_app
from app.services.raster_pipeline import RasterPipeline, RasterTask


@celery_app.task(bind=True, autoretry_for=(OSError,), retry_backoff=2, max_retries=1)
def process_raster(self: Any, task_payload: dict[str, Any]) -> dict[str, Any]:
    """执行 Celery 栅格任务并上报窗口进度。"""
    task = RasterTask(**task_payload)
    started_at = perf_counter()

    def progress(current: int, total: int, message: str) -> None:
        """执行 progress 对应的领域操作并返回结构化结果。"""
        elapsed = max(perf_counter() - started_at, 1e-6)
        throughput = current / elapsed if current > 0 else None
        self.update_state(
            state="PROGRESS",
            meta={
                "progress": round(current / max(total, 1) * 100, 2),
                "message": message,
                "current": current,
                "total": total,
                "throughput": round(throughput, 4) if throughput else None,
                "eta_seconds": (
                    round((total - current) / throughput, 2)
                    if throughput and current < total
                    else 0 if current >= total else None
                ),
            },
        )

    return RasterPipeline().run(task, on_progress=progress)
