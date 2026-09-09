"""Job Radar entry point: fetch -> normalize -> filter -> dedupe -> notify.

Two ordering decisions in here are deliberate:

- Each source is fetched inside its own try/except. One broken board must not
  take out the other five, and its failure becomes a fail-loud alert.
- Jobs are notified *before* being marked as seen. If delivery fails, they stay
  unseen and get retried next run rather than being silently dropped.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Callable, Optional

import dedupe
import health
import notify
from fetchers import ats, justjoinit, nofluffjobs, pracujpl
from fetchers.base import FetchError
from filter import filter_jobs
from models import Job

Source = tuple[str, Callable[[], list[Job]]]


def build_sources() -> list[Source]:
    """Every source, one entry per job board or company board."""
    sources: list[Source] = [
        ("nofluffjobs", nofluffjobs.fetch),
        ("pracujpl", pracujpl.fetch),
        ("justjoinit", justjoinit.fetch),
    ]
    sources.extend(ats.board_sources())
    return sources


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def collect(conn) -> tuple[list[Job], dict[str, str]]:
    """Fetch every source, isolating failures into fail-loud problems."""
    jobs: list[Job] = []
    problems: dict[str, str] = {}

    for name, fetch_fn in build_sources():
        error: Optional[str] = None
        found: list[Job] = []
        try:
            found = fetch_fn()
        except FetchError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - a fetcher bug must not end the run
            error = f"unexpected {type(exc).__name__}: {exc}"

        problem = health.check_and_record(conn, name, len(found), error)
        if problem:
            problems[name] = problem
            log(f"{name}: PROBLEM -- {problem}")
        else:
            log(f"{name}: {len(found)} postings")

        jobs.extend(found)

    return jobs, problems


def run(db_path: Optional[str] = None, seed: bool = False) -> int:
    conn = dedupe.connect(db_path)
    try:
        fetched, problems = collect(conn)
        matched = filter_jobs(fetched)
        fresh = dedupe.unseen(conn, matched)
        log(
            f"{len(fetched)} fetched -> {len(matched)} matched filters -> "
            f"{len(fresh)} new after dedup"
        )

        if seed:
            # Adopt the current backlog without notifying, so the first real
            # run reports genuinely new postings instead of everything at once.
            dedupe.mark_seen(conn, fresh)
            log(f"seeded {len(fresh)} jobs as already seen, sent nothing")
            return 0

        exit_code = 0
        if fresh:
            try:
                sent = notify.notify_jobs(fresh)
                dedupe.mark_seen(conn, fresh)
                log(f"sent {sent} message(s), marked {len(fresh)} jobs as seen")
            except notify.NotifyError as exc:
                # Leave them unseen so the next run retries.
                log(f"DELIVERY FAILED, jobs left unseen for retry: {exc}")
                exit_code = 1
        else:
            log("no new jobs")

        if problems:
            try:
                notify.notify_problems(problems)
                log(f"alerted on {len(problems)} suspect source(s)")
            except notify.NotifyError as exc:
                log(f"could not deliver source alert: {exc}")
                exit_code = 1

        return exit_code
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Job Radar")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print messages to the console instead of sending them to Telegram",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="mark everything currently matching as seen without notifying",
    )
    parser.add_argument("--db", default=None, help="path to the SQLite state file")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["JOB_RADAR_DRY_RUN"] = "1"

    log(f"starting (telegram configured: {notify.is_configured()})")
    return run(db_path=args.db, seed=args.seed)


if __name__ == "__main__":
    sys.exit(main())
