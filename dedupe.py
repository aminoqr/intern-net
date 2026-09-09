"""Persistent seen-job store.

Layer one of two: per-URL. Once a link has been notified it is never notified
again, which is what lets the bot run every hour without becoming noise.

State lives in a SQLite file that the GitHub Actions workflow commits back to
the repo after each run, because the runner's filesystem is thrown away between
scheduled runs. Two consequences of that design:

- Journal mode is left at the default. WAL would create -wal/-shm sidecar files
  that the workflow would have to commit too, and a half-committed WAL is a
  corrupt database.
- Writes are committed once at the end of a run, not per job.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional

import config
from models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    url           TEXT PRIMARY KEY,
    job_id        TEXT NOT NULL,
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    source        TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to the current schema.

    Runs on every open so a database committed by an older revision of the bot
    keeps working instead of crashing the run.
    """
    conn.executescript(SCHEMA)


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    return conn


def unseen(conn: sqlite3.Connection, jobs: Iterable[Job]) -> list[Job]:
    """The jobs whose URLs are not already in the store."""
    known = {row["url"] for row in conn.execute("SELECT url FROM seen_jobs")}
    fresh = []
    for job in jobs:
        if job.url and job.url not in known:
            fresh.append(job)
            # Guard against the same URL appearing twice within one run.
            known.add(job.url)
    return fresh


def mark_seen(conn: sqlite3.Connection, jobs: Iterable[Job]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (job.url, job.id, job.title, job.company, job.source, now)
        for job in jobs
        if job.url
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO seen_jobs
            (url, job_id, title, company, source, first_seen_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from fetchers import ats, nofluffjobs
    from filter import filter_jobs

    jobs = list(nofluffjobs.fetch())
    for _, fetch_fn in ats.board_sources():
        jobs.extend(fetch_fn())
    jobs = filter_jobs(jobs)

    # A throwaway database, so the smoke test never marks the real one as seen.
    with tempfile.TemporaryDirectory() as tmp:
        db = connect(str(Path(tmp) / "smoke.db"))
        first = unseen(db, jobs)
        mark_seen(db, first)
        print(f"run 1: {len(jobs)} filtered -> {len(first)} new (stored {count(db)})")
        second = unseen(db, jobs)
        print(f"run 2: same input -> {len(second)} new (expected 0)")
        db.close()
