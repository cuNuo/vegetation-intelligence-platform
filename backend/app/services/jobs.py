"""本地任务管理器。

开发模式使用线程池，部署模式可由Celery任务包装同一RasterPipeline。
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.raster_pipeline import RasterPipeline, RasterTask
from app.settings import settings


@dataclass(slots=True)
class JobRecord:
    id: str
    status: str = "accepted"
    progress: float = 0.0
    message: str = "等待执行"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    result: dict[str, Any] | None = None
    error: str | None = None
    cancelled: bool = False

    def public(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("cancelled", None)
        return payload


class JobManager:
    def __init__(self, max_workers: int = 3) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="raster-job"
        )

    def submit(self, task: RasterTask, priority: int = 3) -> JobRecord:
        if not settings.celery_always_eager:
            return self._submit_celery(task, priority)
        record = JobRecord(id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[record.id] = record
        self._executor.submit(self._run, record.id, task)
        return record

    def execute_sync(self, task: RasterTask) -> dict[str, Any]:
        task.synchronous = True
        return RasterPipeline().run(task)

    def get(self, job_id: str) -> JobRecord:
        with self._lock:
            try:
                record = self._jobs[job_id]
            except KeyError as error:
                raise KeyError(f"任务不存在: {job_id}") from error
        if not settings.celery_always_eager:
            self._refresh_celery(record)
        return record

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [record.public() for record in reversed(list(self._jobs.values()))]

    def cancel(self, job_id: str) -> JobRecord:
        record = self.get(job_id)
        if not settings.celery_always_eager:
            from app.celery_app import celery_app

            celery_app.control.revoke(job_id, terminate=True)
        record.cancelled = True
        record.message = "正在取消"
        record.updated_at = datetime.now(UTC).isoformat()
        return record

    def _run(self, job_id: str, task: RasterTask) -> None:
        record = self.get(job_id)
        record.status = "running"
        record.updated_at = datetime.now(UTC).isoformat()

        def progress(current: int, total: int, message: str) -> None:
            record.progress = round(current / max(total, 1) * 100, 2)
            record.message = message
            record.updated_at = datetime.now(UTC).isoformat()

        try:
            result = RasterPipeline().run(
                task,
                on_progress=progress,
                is_cancelled=lambda: record.cancelled,
            )
            record.status = "successful"
            record.progress = 100
            record.message = "执行成功"
            record.result = result
        except Exception as error:  # noqa: BLE001 - 任务边界需要持久化错误
            record.status = "dismissed" if record.cancelled else "failed"
            record.message = "任务已取消" if record.cancelled else "执行失败"
            record.error = str(error)
        finally:
            record.updated_at = datetime.now(UTC).isoformat()

    def _submit_celery(self, task: RasterTask, priority: int) -> JobRecord:
        from app.celery_app import celery_app
        from app.services.raster_pipeline import task_as_dict

        queues = {1: "urgent", 2: "high", 3: "normal", 4: "low", 5: "batch"}
        async_result = celery_app.send_task(
            "app.worker_tasks.process_raster",
            args=[task_as_dict(task)],
            queue=queues[priority],
            priority=max(0, priority - 1),
        )
        record = JobRecord(id=async_result.id)
        with self._lock:
            self._jobs[record.id] = record
        return record

    @staticmethod
    def _refresh_celery(record: JobRecord) -> None:
        from app.celery_app import celery_app

        result = celery_app.AsyncResult(record.id)
        state_mapping = {
            "PENDING": "accepted",
            "STARTED": "running",
            "PROGRESS": "running",
            "RETRY": "running",
            "SUCCESS": "successful",
            "FAILURE": "failed",
            "REVOKED": "dismissed",
        }
        record.status = state_mapping.get(result.state, result.state.lower())
        if result.state == "PROGRESS" and isinstance(result.info, dict):
            record.progress = float(result.info.get("progress", record.progress))
            record.message = str(result.info.get("message", record.message))
        elif result.successful():
            record.progress = 100
            record.message = "执行成功"
            record.result = result.result
        elif result.failed():
            record.message = "执行失败"
            record.error = str(result.result)
        record.updated_at = datetime.now(UTC).isoformat()


job_manager = JobManager()
