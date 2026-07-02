# backend/app/worker_tasks.py
# 文件说明：Celery Worker 栅格计算任务入口和进度元信息上报。
"""Celery Worker任务。"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from app.celery_app import celery_app
from app.services.raster_pipeline import RasterPipeline, RasterTask


@celery_app.task(bind=True, autoretry_for=(OSError,), retry_backoff=2, max_retries=1)
def process_raster(self: Any, task_payload: dict[str, Any]) -> dict[str, Any]:
    task = RasterTask(**task_payload)
    started_at = perf_counter()

    def progress(current: int, total: int, message: str) -> None:
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
