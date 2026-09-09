"""Fail-loud source health checks.

The whole point of this bot is to stop checking job sites by hand, which only
works if a silently broken fetcher is impossible. A source that starts
returning nothing looks exactly like "no new jobs today" unless something
actively compares against what it normally returns.

So every run records its per-source result count, and a source is called
suspect when it:

- raised an exception,
- returned zero results, or
- returned far below its own trailing median.

The verdict is deliberately separate from the job notification, so a broken
source produces its own alert instead of an absence of messages.
"""

from __future__ import annotations

import sqlite3
import statistics
from typing import Optional

import config
import dedupe


def verdict(
    conn: sqlite3.Connection,
    source: str,
    job_count: int,
    error: Optional[str] = None,
) -> Optional[str]:
    """A human-readable problem description, or None if the source looks fine.

    Call before recording this run, so the comparison uses prior runs only.
    """
    if error:
        return f"fetch failed: {error}"

    history = dedupe.recent_counts(conn, source)

    if job_count == 0:
        if history and max(history) > 0:
            return f"returned 0 results (previously up to {max(history)})"
        # Nothing to compare against yet. A genuinely empty board on a first
        # run is not evidence of breakage, so stay quiet rather than cry wolf.
        return None

    if len(history) < config.SOURCE_HISTORY_MIN_RUNS:
        return None

    median = statistics.median(history)
    if median and job_count < median * config.SOURCE_DROP_THRESHOLD:
        return (
            f"returned {job_count}, far below its median of {median:g} "
            f"over the last {len(history)} runs"
        )

    return None


def check_and_record(
    conn: sqlite3.Connection,
    source: str,
    job_count: int,
    error: Optional[str] = None,
) -> Optional[str]:
    """Evaluate a source's result, then log the run. Returns any problem."""
    problem = verdict(conn, source, job_count, error)
    dedupe.record_source_run(conn, source, job_count, ok=error is None)
    return problem


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        db = dedupe.connect(str(Path(tmp) / "health.db"))

        print("first run, empty source (no history to judge against):")
        print("  ->", check_and_record(db, "demo", 0))

        print("three healthy runs of ~40:")
        for value in (40, 38, 42):
            print(f"  {value} ->", check_and_record(db, "demo", value))

        print("now a collapse to 2:")
        print("  ->", check_and_record(db, "demo", 2))

        print("now zero:")
        print("  ->", check_and_record(db, "demo", 0))

        print("now an exception:")
        print("  ->", check_and_record(db, "demo", 0, error="HTTP 403"))

        print("a mild dip to 30 is not an alert:")
        print("  ->", check_and_record(db, "demo", 30))
        db.close()
