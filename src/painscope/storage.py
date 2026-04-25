"""SQLite-backed storage for scan history and recurring schedules.

Tables:
  scans     - stores every ScanResult, indexed by topic_name for trend queries
  schedules - recurring scan schedules with APScheduler-friendly metadata
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from painscope.config import get_settings

if TYPE_CHECKING:
    from painscope.pipeline.orchestrator import ScanResult

logger = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    db_path = get_settings().db_path
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scans (
                scan_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                scan_type TEXT NOT NULL,
                language TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                model_used TEXT,
                total_posts_fetched INTEGER,
                total_posts_used INTEGER,
                num_clusters INTEGER,
                duration_seconds REAL,
                insights_json TEXT NOT NULL,
                sources_json TEXT,
                topic_name TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_scans_source_target
                ON scans(source, target);
            CREATE INDEX IF NOT EXISTS idx_scans_started_at
                ON scans(started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_scans_topic_name
                ON scans(topic_name);

            CREATE TABLE IF NOT EXISTS schedules (
                schedule_id TEXT PRIMARY KEY,
                topic_name TEXT NOT NULL,
                config_yaml TEXT NOT NULL,
                interval_days INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                next_run_at TEXT NOT NULL,
                last_run_at TEXT,
                run_count INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_schedules_next_run
                ON schedules(next_run_at);
            CREATE INDEX IF NOT EXISTS idx_schedules_topic
                ON schedules(topic_name);
            """
        )
        # Migration: add topic_name column to older DBs that lack it
        try:
            conn.execute("ALTER TABLE scans ADD COLUMN topic_name TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: add sources_json column to older DBs that lack it
        try:
            conn.execute("ALTER TABLE scans ADD COLUMN sources_json TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists


def save_scan(result: "ScanResult", *, topic_name: str | None = None) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO scans (
                scan_id, source, target, scan_type, language,
                started_at, completed_at, model_used,
                total_posts_fetched, total_posts_used, num_clusters,
                duration_seconds, insights_json, sources_json, topic_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.scan_id,
                result.source,
                result.target,
                result.scan_type,
                result.language,
                result.started_at.isoformat(),
                result.completed_at.isoformat(),
                result.model_used,
                result.total_posts_fetched,
                result.total_posts_used,
                result.num_clusters,
                result.duration_seconds,
                json.dumps(result.insights, ensure_ascii=False),
                json.dumps(getattr(result, "sources", []), ensure_ascii=False),
                topic_name,
            ),
        )
    logger.info(f"Saved scan {result.scan_id} (topic={topic_name!r})")


def get_scan(scan_id: str) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM scans WHERE scan_id = ?", (scan_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["insights"] = json.loads(result.pop("insights_json"))
        sources_raw = result.pop("sources_json", None)
        result["sources"] = json.loads(sources_raw) if sources_raw else []
        return result


def list_scans(
    *,
    source: str | None = None,
    target: str | None = None,
    scan_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    init_db()
    clauses = []
    params: list[Any] = []
    if source:
        clauses.append("source = ?")
        params.append(source)
    if target:
        clauses.append("target = ?")
        params.append(target)
    if scan_type:
        clauses.append("scan_type = ?")
        params.append(scan_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT scan_id, source, target, scan_type, language,
                   started_at, completed_at, total_posts_used,
                   num_clusters, duration_seconds, topic_name
            FROM scans
            {where}
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_scans_for_topic(topic_name: str, *, limit: int = 20) -> list[dict]:
    """Return full scan records (including insights) for a given topic_name."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM scans
            WHERE topic_name = ?
            ORDER BY started_at ASC
            LIMIT ?
            """,
            (topic_name, limit),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["insights"] = json.loads(d.pop("insights_json"))
            sources_raw = d.pop("sources_json", None)
            d["sources"] = json.loads(sources_raw) if sources_raw else []
            results.append(d)
        return results


# ---------------------------------------------------------------------------
# Schedule management
# ---------------------------------------------------------------------------

def save_schedule(
    schedule_id: str,
    topic_name: str,
    config_yaml: str,
    interval_days: int,
) -> dict:
    init_db()
    now = datetime.now(timezone.utc)
    next_run = now + timedelta(days=interval_days)
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO schedules (
                schedule_id, topic_name, config_yaml, interval_days,
                created_at, next_run_at, last_run_at, run_count, active
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, 0, 1)
            """,
            (
                schedule_id,
                topic_name,
                config_yaml,
                interval_days,
                now.isoformat(),
                next_run.isoformat(),
            ),
        )
    return {
        "schedule_id": schedule_id,
        "topic_name": topic_name,
        "interval_days": interval_days,
        "next_run_at": next_run.isoformat(),
        "active": True,
    }


def list_schedules(*, active_only: bool = True) -> list[dict]:
    init_db()
    where = "WHERE active = 1" if active_only else ""
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT schedule_id, topic_name, interval_days,
                   created_at, next_run_at, last_run_at, run_count, active
            FROM schedules
            {where}
            ORDER BY next_run_at ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_overdue_schedules() -> list[dict]:
    """Return active schedules whose next_run_at is in the past."""
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM schedules
            WHERE active = 1 AND next_run_at <= ?
            ORDER BY next_run_at ASC
            """,
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_schedule_after_run(schedule_id: str) -> None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT interval_days FROM schedules WHERE schedule_id = ?",
            (schedule_id,),
        ).fetchone()
        if not row:
            return
        interval = row["interval_days"]
        now = datetime.now(timezone.utc)
        next_run = now + timedelta(days=interval)
        conn.execute(
            """
            UPDATE schedules
            SET last_run_at = ?, next_run_at = ?, run_count = run_count + 1
            WHERE schedule_id = ?
            """,
            (now.isoformat(), next_run.isoformat(), schedule_id),
        )


def deactivate_schedule(schedule_id: str) -> bool:
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE schedules SET active = 0 WHERE schedule_id = ?",
            (schedule_id,),
        )
        return cur.rowcount > 0
