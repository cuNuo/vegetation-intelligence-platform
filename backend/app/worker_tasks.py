"""Celery Worker任务。"""

from __future__ import annotations

from typing import Any

from app.celery_app import celery_app
from app.services.raster_pipeline import RasterPipeline, RasterTask


@celery_app.task(bind=True, autoretry_for=(OSError,), retry_backoff=2, max_retries=1)
def process_raster(self: Any, task_payload: dict[str, Any]) -> dict[str, Any]:
    task = RasterTask(**task_payload)

    def progress(current: int, total: int, message: str) -> None:
        self.update_state(
            state="PROGRESS",
            meta={"progress": round(current / max(total, 1) * 100, 2), "message": message},
        )

    return RasterPipeline().run(task, on_progress=progress)
