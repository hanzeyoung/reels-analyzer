from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB_PATH = Path("user_reels") / "jobs.sqlite3"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            result_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            progress INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            dedupe_key TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        )
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
    if "owner_id" not in columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local'")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_dedupe ON jobs(dedupe_key)")
    return connection


def _decode(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    item["payload"] = json.loads(item.pop("payload_json") or "{}")
    item["result"] = json.loads(item.pop("result_json") or "{}")
    return item


def enqueue_job(
    kind: str,
    payload: dict,
    dedupe_key: str = "",
    max_attempts: int = 3,
    owner_id: str = "local",
    path: Path = DEFAULT_DB_PATH,
) -> dict:
    with _connect(path) as connection:
        if dedupe_key:
            existing = connection.execute(
                "SELECT * FROM jobs WHERE dedupe_key = ? AND owner_id = ? AND status IN ('pending', 'running') ORDER BY created_at DESC LIMIT 1",
                (dedupe_key, owner_id),
            ).fetchone()
            if existing:
                return _decode(existing) or {}
        job_id = str(uuid.uuid4())
        now = _now()
        connection.execute(
            """INSERT INTO jobs
               (id, kind, payload_json, status, progress, attempts, max_attempts, dedupe_key, owner_id, created_at, updated_at)
               VALUES (?, ?, ?, 'pending', 0, 0, ?, ?, ?, ?, ?)""",
            (job_id, kind, json.dumps(payload, ensure_ascii=False), max(1, max_attempts), dedupe_key or None, owner_id, now, now),
        )
        return get_job(job_id, path) or {}


def get_job(job_id: str, path: Path = DEFAULT_DB_PATH) -> dict | None:
    with _connect(path) as connection:
        return _decode(connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())


def list_jobs(limit: int = 20, owner_id: str = "", path: Path = DEFAULT_DB_PATH) -> list[dict]:
    with _connect(path) as connection:
        if owner_id:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?",
                (owner_id, limit),
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_decode(row) or {} for row in rows]


def claim_next_job(path: Path = DEFAULT_DB_PATH, kinds: tuple[str, ...] = ()) -> dict | None:
    connection = _connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        params: list[object] = []
        kind_clause = ""
        if kinds:
            kind_clause = f" AND kind IN ({','.join('?' for _ in kinds)})"
            params.extend(kinds)
        row = connection.execute(
            f"SELECT * FROM jobs WHERE status = 'pending' AND attempts < max_attempts{kind_clause} ORDER BY created_at LIMIT 1",
            params,
        ).fetchone()
        if not row:
            connection.execute("COMMIT")
            return None
        now = _now()
        connection.execute(
            "UPDATE jobs SET status='running', progress=1, attempts=attempts+1, started_at=?, updated_at=? WHERE id=?",
            (now, now, row["id"]),
        )
        connection.execute("COMMIT")
        return get_job(row["id"], path)
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def update_progress(job_id: str, progress: int, path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(path) as connection:
        connection.execute(
            "UPDATE jobs SET progress=?, updated_at=? WHERE id=? AND status='running'",
            (max(0, min(99, int(progress))), _now(), job_id),
        )


def is_job_cancelled(job_id: str, path: Path = DEFAULT_DB_PATH) -> bool:
    job = get_job(job_id, path)
    return bool(job and job.get("status") == "cancelled")


def complete_job(job_id: str, result: dict, path: Path = DEFAULT_DB_PATH) -> bool:
    now = _now()
    with _connect(path) as connection:
        result_row = connection.execute(
            "UPDATE jobs SET status='completed', progress=100, result_json=?, error=NULL, updated_at=?, finished_at=? WHERE id=? AND status='running'",
            (json.dumps(result, ensure_ascii=False), now, now, job_id),
        )
        return result_row.rowcount > 0


def fail_job(job_id: str, error: str, path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(path) as connection:
        row = connection.execute("SELECT attempts, max_attempts, status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return
        if row["status"] == "cancelled":
            return
        retry = int(row["attempts"]) < int(row["max_attempts"])
        status = "pending" if retry else "failed"
        now = _now()
        connection.execute(
            "UPDATE jobs SET status=?, progress=0, error=?, updated_at=?, finished_at=? WHERE id=?",
            (status, str(error)[:2000], now, None if retry else now, job_id),
        )


def cancel_job(job_id: str, owner_id: str = "", path: Path = DEFAULT_DB_PATH) -> bool:
    now = _now()
    with _connect(path) as connection:
        owner_clause = " AND owner_id = ?" if owner_id else ""
        params = (now, now, job_id, owner_id) if owner_id else (now, now, job_id)
        result = connection.execute(
            f"UPDATE jobs SET status='cancelled', updated_at=?, finished_at=? WHERE id=? AND status IN ('pending', 'running'){owner_clause}",
            params,
        )
        return result.rowcount > 0
