"""Runs analyses on a background thread and exposes live progress for the UI to poll."""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Step:
    key: str
    label: str
    status: str = "pending"  # pending | running | done | skipped | failed
    detail: str = ""


@dataclass
class Job:
    id: str
    project_id: str
    kind: str
    steps: list[Step] = field(default_factory=list)
    status: str = "running"  # running | done | failed
    message: str = ""  # live note, e.g. rate-limit pacing
    error: str = ""
    error_kind: str = ""
    started: float = field(default_factory=time.time)
    finished: float | None = None
    llm_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set_steps(self, steps: list[tuple[str, str]]) -> None:
        with self._lock:
            self.steps = [Step(k, label) for k, label in steps]

    def begin(self, key: str) -> None:
        with self._lock:
            for step in self.steps:
                if step.key == key:
                    step.status = "running"
            self.message = ""

    def end(self, key: str, detail: str = "", skipped: bool = False) -> None:
        with self._lock:
            for step in self.steps:
                if step.key == key:
                    step.status = "skipped" if skipped else "done"
                    step.detail = detail

    def fail_step(self, key: str, detail: str) -> None:
        with self._lock:
            for step in self.steps:
                if step.key == key:
                    step.status = "failed"
                    step.detail = detail

    def note(self, message: str) -> None:
        self.message = message

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.id,
                "project_id": self.project_id,
                "kind": self.kind,
                "status": self.status,
                "message": self.message,
                "error": self.error,
                "error_kind": self.error_kind,
                "elapsed": round((self.finished or time.time()) - self.started, 1),
                "steps": [step.__dict__.copy() for step in self.steps],
            }


class JobRegistry:
    """Keeps the latest job per project; at most one job runs per project at a time."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def latest(self, project_id: str) -> Job | None:
        return self._jobs.get(project_id)

    def is_running(self, project_id: str) -> bool:
        job = self._jobs.get(project_id)
        return job is not None and job.status == "running"

    def start(self, project_id: str, kind: str, work: Callable[[Job], None]) -> Job:
        """Starts ``work(job)`` on a thread. Raises RuntimeError if one is already running."""
        with self._lock:
            if self.is_running(project_id):
                raise RuntimeError("An analysis is already running for this project.")
            job = Job(id=uuid.uuid4().hex[:10], project_id=project_id, kind=kind)
            self._jobs[project_id] = job

        def runner() -> None:
            from src.agents.llm_client import RateLimitedError, set_status_sink
            from src.models.audit import set_audit_project

            set_status_sink(job.note)
            set_audit_project(project_id)
            try:
                work(job)
                job.status = "done"
            except RateLimitedError as exc:
                job.status, job.error, job.error_kind = "failed", str(exc), "rate_limited"
            except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
                job.status, job.error, job.error_kind = "failed", f"{type(exc).__name__}: {exc}", "error"
                traceback.print_exc()
            finally:
                job.finished = time.time()
                job.message = ""
                set_status_sink(None)

        threading.Thread(target=runner, name=f"job-{job.id}", daemon=True).start()
        return job


registry = JobRegistry()
