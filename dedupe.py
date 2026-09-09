"""Persistent seen-job store, two dedup layers deep.

Layer one is per-URL: once a link has been notified it is never notified again,
which is what lets the bot run every hour without becoming noise.

Layer two is cross-source: company and title are normalized into a fingerprint,
so one role cross-posted to NoFluffJobs and Pracuj.pl (or listed once per city
on the same board) collapses into a single ping instead of three.

State lives in a SQLite file that the GitHub Actions workflow commits back to
the repo after each run, because the runner's filesystem is thrown away between
scheduled runs. Two consequences of that design:

- Journal mode is left at the default. WAL would create -wal/-shm sidecar files
  that the workflow would have to commit too, and a half-committed WAL is a
  corrupt database.
- Writes are committed once at the end of a run, not per job.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional

import config
from models import Job, normalize_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    url           TEXT PRIMARY KEY,
    job_id        TEXT NOT NULL,
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    source        TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
);

-- Per-run result counts, kept so the fail-loud check has a baseline to compare
-- against. "Returned zero when it normally returns dozens" is unanswerable
-- without history, and the runner's filesystem does not survive between runs.
CREATE TABLE IF NOT EXISTS source_stats (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source    TEXT NOT NULL,
    run_at    TEXT NOT NULL,
    job_count INTEGER NOT NULL,
    ok        INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_source_stats_source ON source_stats(source, id);
"""

# Legal forms carry no identity. "Mindbox Sp. z o.o." and "Mindbox" are one
# employer, and boards are inconsistent about including them.
LEGAL_FORMS = re.compile(
    r"(?<!\w)(sp\.?\s*z\s*o\.?\s*o\.?|spolka\s+z\s+ograniczona\s+odpowiedzialnoscia"
    r"|spolka\s+akcyjna|s\.\s*a\.|z\s*o\.?\s*o\.?|gmbh|s\.?a\.?r\.?l\.?|ltd\.?"
    r"|limited|llc|l\.l\.c\.|inc\.?|incorporated|plc|corp\.?|corporation"
    r"|b\.?v\.?|n\.?v\.?|s\.?r\.?l\.?|oyj?|a\/s)(?!\w)"
)

# Polish job ads decorate titles for gender inclusivity in several formats:
# "(K/M)", "(f/m)", "(m/f/d)", "Tester/-ka", "Analityk(czka)", "Programista/tka".
GENDER_MARKERS = re.compile(
    r"\(?(?<!\w)[kmf]\s*/\s*[kmfd](\s*/\s*[kmfd])?(?!\w)\)?"
    r"|\(\s*(czka|ka|tka|ki)\s*\)"
    r"|/\s*-?\s*(czka|tka|ka|ki)(?!\w)"
)

NON_ALNUM = re.compile(r"[^a-z0-9]+")


def company_key(company: str) -> str:
    text = normalize_text(company)
    text = re.sub(r"\([^)]*\)", " ", text)  # "AVENGA (Agencja Pracy, nr KRAZ: 8448)"
    text = LEGAL_FORMS.sub(" ", text)
    return NON_ALNUM.sub(" ", text).strip()


def title_key(title: str) -> str:
    text = normalize_text(title)
    text = GENDER_MARKERS.sub(" ", text)
    return NON_ALNUM.sub(" ", text).strip()


def make_fingerprint(company: str, title: str) -> str:
    return f"{company_key(company)}|{title_key(title)}"


def fingerprint(job: Job) -> str:
    return make_fingerprint(job.company, job.title)


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to the current schema.

    Runs on every open so a database committed by an older revision of the bot
    keeps working instead of crashing the run.
    """
    conn.executescript(SCHEMA)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(seen_jobs)")}
    if "fingerprint" not in columns:
        conn.execute(
            "ALTER TABLE seen_jobs ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''"
        )
        # Backfill from the titles and companies already stored, so upgrading
        # does not resurface every job we have ever seen.
        backfill = [
            (make_fingerprint(row["company"], row["title"]), row["url"])
            for row in conn.execute("SELECT url, title, company FROM seen_jobs")
        ]
        conn.executemany(
            "UPDATE seen_jobs SET fingerprint = ? WHERE url = ?", backfill
        )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_seen_jobs_fingerprint "
        "ON seen_jobs(fingerprint)"
    )
    conn.commit()


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    return conn


def unseen(conn: sqlite3.Connection, jobs: Iterable[Job]) -> list[Job]:
    """The jobs that are new by URL *and* by company+title fingerprint.

    Both sets are also updated as we go, so duplicates appearing twice within a
    single run collapse too -- which happens in practice, since boards list one
    role once per city.
    """
    known_urls = {row["url"] for row in conn.execute("SELECT url FROM seen_jobs")}
    known_prints = {
        row["fingerprint"]
        for row in conn.execute("SELECT fingerprint FROM seen_jobs")
        if row["fingerprint"]
    }

    fresh = []
    for job in jobs:
        if not job.url or job.url in known_urls:
            continue
        print_ = fingerprint(job)
        if print_ in known_prints:
            continue
        fresh.append(job)
        known_urls.add(job.url)
        known_prints.add(print_)
    return fresh


def mark_seen(conn: sqlite3.Connection, jobs: Iterable[Job]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (job.url, job.id, job.title, job.company, job.source, fingerprint(job), now)
        for job in jobs
        if job.url
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO seen_jobs
            (url, job_id, title, company, source, fingerprint, first_seen_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]


def record_source_run(
    conn: sqlite3.Connection, source: str, job_count: int, ok: bool = True
) -> None:
    """Log what a source returned this run, for the fail-loud baseline."""
    conn.execute(
        "INSERT INTO source_stats (source, run_at, job_count, ok) VALUES (?, ?, ?, ?)",
        (source, datetime.now(timezone.utc).isoformat(), job_count, 1 if ok else 0),
    )
    conn.commit()


def recent_counts(
    conn: sqlite3.Connection, source: str, limit: int = 10
) -> list[int]:
    """Result counts from this source's last successful runs, newest first."""
    rows = conn.execute(
        """
        SELECT job_count FROM source_stats
        WHERE source = ? AND ok = 1
        ORDER BY id DESC
        LIMIT ?
        """,
        (source, limit),
    )
    return [row["job_count"] for row in rows]


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from fetchers import ats, nofluffjobs
    from filter import filter_jobs

    jobs = list(nofluffjobs.fetch())
    for _, fetch_fn in ats.board_sources():
        jobs.extend(fetch_fn())
    jobs = filter_jobs(jobs)

    print("fingerprint normalization:")
    for company, title in [
        ("Falck Digital Technology Poland Sp. z o.o.", "Working Student – IT Support"),
        ("Falck Digital Technology Poland", "Working Student - IT Support"),
        ("Connectis_", "Analityk(czka) AML/KYC"),
        ("AVENGA (Agencja Pracy, nr KRAZ: 8448)", "Junior IT Analyst"),
        ("Mindbox Sp. z o.o.", "Tester/ -ka Oprogramowania _ Junior"),
        ("PracBaza", "Junior Programista/tka Helpdesk k/m"),
    ]:
        print(f"  {company!r:48} {title!r:40} -> {make_fingerprint(company, title)!r}")

    # A throwaway database, so the smoke test never marks the real one as seen.
    with tempfile.TemporaryDirectory() as tmp:
        db = connect(str(Path(tmp) / "smoke.db"))
        first = unseen(db, jobs)
        mark_seen(db, first)
        collapsed = len(jobs) - len(first)
        print(
            f"\nrun 1: {len(jobs)} filtered -> {len(first)} new "
            f"({collapsed} collapsed cross-source), stored {count(db)}"
        )
        second = unseen(db, jobs)
        print(f"run 2: same input -> {len(second)} new (expected 0)")
        db.close()
