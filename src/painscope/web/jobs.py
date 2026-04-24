from __future__ import annotations

import logging
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import yaml

from painscope.topics import TopicConfig, load_profile
from painscope.web.schemas import JobSnapshot, JobStatus, StartScanRequest

logger = logging.getLogger(__name__)
TARGET_PATTERN = re.compile(r"^[\w\s./:@#?=&+\-]+$")
MAX_SOURCES = 10
MAX_LIMIT_PER_SOURCE = 500
MAX_TOP_N = 50
ALLOWED_CONFIG_KEYS = {
    "name",
    "description",
    "language",
    "limit",
    "limit_per_source",
    "top_n",
    "scan_type",
    "model",
    "sources",
}


@dataclass
class ScanJob:
    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    profile: str | None = None
    topic_name: str | None = None
    scan_id: str | None = None
    error: str | None = None

    def snapshot(self) -> JobSnapshot:
        return JobSnapshot(
            job_id=self.job_id,
            status=self.status,
            created_at=self.created_at.isoformat(),
            started_at=self.started_at.isoformat() if self.started_at else None,
            completed_at=self.completed_at.isoformat() if self.completed_at else None,
            profile=self.profile,
            topic_name=self.topic_name,
            scan_id=self.scan_id,
            error=self.error,
        )


class ScanJobRunner:
    """Very small in-memory runner for a personal, single-user web UI."""

    def __init__(self, *, max_workers: int = 1, max_jobs: int = 100) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="painscope-web")
        self._jobs: dict[str, ScanJob] = {}
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def start(self, request: StartScanRequest) -> JobSnapshot:
        config = build_topic_config(request)
        job = ScanJob(
            job_id=uuid.uuid4().hex,
            status="queued",
            created_at=datetime.now(timezone.utc),
            profile=request.profile,
            topic_name=config.name,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._trim_locked()
        self._executor.submit(self._run, job.job_id, config)
        return job.snapshot()

    def get(self, job_id: str) -> JobSnapshot | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot() if job else None

    def _run(self, job_id: str, config: TopicConfig) -> None:
        from painscope.output.markdown import save_report
        from painscope.pipeline.orchestrator import run_topic_scan
        from painscope.storage import save_scan

        self._update(job_id, status="running", started_at=datetime.now(timezone.utc))
        try:
            result = run_topic_scan(config)
            save_scan(result, topic_name=config.name)
            try:
                save_report(result)
            except Exception as exc:
                logger.warning("Markdown report save failed for %s: %s", result.scan_id, exc)
            self._update(
                job_id,
                status="completed",
                completed_at=datetime.now(timezone.utc),
                scan_id=result.scan_id,
            )
        except Exception:
            logger.exception("Scan job %s failed", job_id)
            self._update(
                job_id,
                status="failed",
                completed_at=datetime.now(timezone.utc),
                error="Scan failed. Check server logs for details.",
            )

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            self._trim_locked()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def _trim_locked(self) -> None:
        if len(self._jobs) <= self._max_jobs:
            return
        removable = [
            job
            for job in sorted(self._jobs.values(), key=lambda item: item.created_at)
            if job.status in {"completed", "failed"}
        ]
        for job in removable[: len(self._jobs) - self._max_jobs]:
            self._jobs.pop(job.job_id, None)


def build_topic_config(request: StartScanRequest) -> TopicConfig:
    if request.config_yaml:
        raw = yaml.safe_load(request.config_yaml)
        if not isinstance(raw, dict):
            raise ValueError("config_yaml must be a YAML mapping.")
        unknown_keys = set(raw) - ALLOWED_CONFIG_KEYS
        if unknown_keys:
            raise ValueError(f"Unsupported config keys: {', '.join(sorted(unknown_keys))}")
        data: dict[str, Any] = raw
    else:
        data = load_profile(request.profile or "tr").model_dump(exclude_none=True)

    if request.topic_name:
        data["name"] = request.topic_name
    if request.scan_type:
        data["scan_type"] = request.scan_type
    if request.language:
        data["language"] = request.language

    if "sources" not in data:
        raise ValueError("Topic config must include a sources list.")

    data["limit_per_source"] = _bounded_int(
        data.get("limit_per_source", data.get("limit", 200)),
        default=200,
        minimum=1,
        maximum=MAX_LIMIT_PER_SOURCE,
        field="limit_per_source",
    )
    data["top_n"] = _bounded_int(
        data.get("top_n", 20),
        default=20,
        minimum=1,
        maximum=MAX_TOP_N,
        field="top_n",
    )
    _validate_sources(data["sources"])
    return TopicConfig.model_validate(data)


def _validate_sources(sources: Any) -> None:
    from painscope.adapters import available_sources

    allowed = set(available_sources())
    if not isinstance(sources, list) or not sources:
        raise ValueError("Topic config must include at least one source.")
    if len(sources) > MAX_SOURCES:
        raise ValueError(f"Topic config can include at most {MAX_SOURCES} sources.")

    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Each source must be a YAML mapping.")
        source_type = str(source.get("type", ""))
        target = str(source.get("target", ""))

        if source_type not in allowed:
            raise ValueError(f"Unsupported source type: {source_type!r}. Available: {', '.join(sorted(allowed))}")
        if not target or len(target) > 200:
            raise ValueError("Each source target must be between 1 and 200 characters.")
        if "://" in target or target.startswith("//") or not TARGET_PATTERN.match(target):
            raise ValueError(f"Invalid target for source {source_type!r}.")


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int, field: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer.") from exc
    if parsed < minimum:
        raise ValueError(f"{field} must be at least {minimum}.")
    if parsed > maximum:
        raise ValueError(f"{field} must be at most {maximum}.")
    return parsed

