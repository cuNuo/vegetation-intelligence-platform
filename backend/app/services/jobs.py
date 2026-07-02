# backend/app/services/jobs.py
# 文件说明：本地与 Celery 异步栅格任务记录、进度估算和结果管理。
"""本地任务管理器。

开发模式使用线程池，部署模式可由Celery任务包装同一RasterPipeline。
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from time import perf_counter
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
    started_at: str | None = None
    finished_at: str | None = None
    eta_seconds: float | None = None
    throughput: float | None = None
    current: int = 0
    total: int = 0
    engine: str = "auto"
    index_count: int = 0
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
        record = JobRecord(id=uuid.uuid4().hex, engine=task.engine, index_count=len(task.indices))
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
        record.started_at = datetime.now(UTC).isoformat()
        record.updated_at = record.started_at
        started_tick = perf_counter()

        def progress(current: int, total: int, message: str) -> None:
            elapsed = max(perf_counter() - started_tick, 1e-6)
            throughput = current / elapsed if current > 0 else None
            record.progress = round(current / max(total, 1) * 100, 2)
            record.message = message
            record.current = current
            record.total = total
            record.throughput = round(throughput, 4) if throughput else None
            record.eta_seconds = (
                round((total - current) / throughput, 2)
                if throughput and current < total
                else 0 if current >= total else None
            )
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
            record.current = record.total or record.current
            record.eta_seconds = 0
            record.result = result
            record.engine = str(result.get("actualEngine") or record.engine)
        except Exception as error:  # noqa: BLE001 - 任务边界需要持久化错误
            record.status = "dismissed" if record.cancelled else "failed"
            record.message = "任务已取消" if record.cancelled else "执行失败"
            record.eta_seconds = None
            record.error = str(error)
        finally:
            record.finished_at = datetime.now(UTC).isoformat()
            record.updated_at = record.finished_at

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
        record = JobRecord(id=async_result.id, engine=task.engine, index_count=len(task.indices))
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
        now = datetime.now(UTC).isoformat()
        if record.status == "running" and not record.started_at:
            record.started_at = now
        if result.state == "PROGRESS" and isinstance(result.info, dict):
            record.progress = float(result.info.get("progress", record.progress))
            record.message = str(result.info.get("message", record.message))
            record.current = int(result.info.get("current", record.current))
            record.total = int(result.info.get("total", record.total))
            throughput = result.info.get("throughput", record.throughput)
            eta_seconds = result.info.get("eta_seconds", record.eta_seconds)
            record.throughput = float(throughput) if throughput is not None else None
            record.eta_seconds = float(eta_seconds) if eta_seconds is not None else None
        elif result.successful():
            record.progress = 100
            record.message = "执行成功"
            record.result = result.result
            record.finished_at = record.finished_at or now
            record.eta_seconds = 0
            if isinstance(record.result, dict):
                record.engine = str(record.result.get("actualEngine") or record.engine)
        elif result.failed():
            record.message = "执行失败"
            record.error = str(result.result)
            record.finished_at = record.finished_at or now
        record.updated_at = now


job_manager = JobManager()
