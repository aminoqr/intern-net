"""Telegram delivery.

Runs in one of two modes:

- configured: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are present, messages go
  to Telegram.
- dry run: they are not, messages are printed to the console instead.

The dry-run path is not a stub. It means main.py can be run end-to-end and
reviewed before a bot exists, and it means CI can execute the whole pipeline
without secrets.
"""

from __future__ import annotations

import html
import os
import time
from pathlib import Path
from typing import Iterable, Optional

from fetchers.base import FetchError, fetch_json
from models import Job

API_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram rejects messages over 4096 characters. Batch well under it so a
# single long job title can never push a message over the edge.
MAX_MESSAGE_CHARS = 3500
SEND_DELAY_SECONDS = 0.5


class NotifyError(Exception):
    """A message could not be delivered."""


def load_env(path: str = ".env") -> None:
    """Read KEY=VALUE lines from .env without adding a dependency.

    Existing environment variables win, so GitHub Actions secrets are never
    overridden by a stray local file.
    """
    env_file = Path(path)
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _credentials() -> tuple[Optional[str], Optional[str]]:
    load_env()
    return os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")


def is_configured() -> bool:
    if os.environ.get("JOB_RADAR_DRY_RUN"):
        return False
    token, chat_id = _credentials()
    return bool(token and chat_id)


def send_message(text: str) -> None:
    """Deliver one message, or print it if Telegram is not configured."""
    if not is_configured():
        print("--- telegram (dry run) ---")
        print(text)
        print("--- end ---")
        return

    token, chat_id = _credentials()
    try:
        response = fetch_json(
            API_TEMPLATE.format(token=token),
            method="POST",
            json_body={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
    except FetchError as exc:
        raise NotifyError(f"Telegram send failed: {exc}") from exc

    if not response.get("ok"):
        raise NotifyError(f"Telegram rejected the message: {response}")


def format_job(job: Job) -> str:
    parts = [f'<a href="{html.escape(job.url, quote=True)}">{html.escape(job.title)}</a>']
    parts.append(f"<b>{html.escape(job.company)}</b>")

    details = [detail for detail in (job.location, job.seniority) if detail]
    if details:
        parts.append(html.escape(" · ".join(details)))
    parts.append(f"<i>{html.escape(job.source)}</i>")
    return "\n".join(parts)


def _batch(blocks: list[str], header: str) -> list[str]:
    """Pack formatted blocks into as few messages as the size limit allows."""
    messages, current = [], header
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > MAX_MESSAGE_CHARS and current:
            messages.append(current)
            current = block
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


def notify_jobs(jobs: Iterable[Job]) -> int:
    """Send the new matches. Returns the number of messages sent."""
    jobs = list(jobs)
    if not jobs:
        return 0

    header = f"<b>{len(jobs)} new job{'s' if len(jobs) != 1 else ''}</b>"
    messages = _batch([format_job(job) for job in jobs], header)
    for index, message in enumerate(messages):
        send_message(message)
        if index < len(messages) - 1:
            time.sleep(SEND_DELAY_SECONDS)
    return len(messages)


def notify_problems(problems: dict[str, str]) -> int:
    """Send the fail-loud alert for suspect sources.

    Sent as its own message rather than appended to the job list: the whole
    point is that it is visible when there are no jobs to report.
    """
    if not problems:
        return 0

    lines = ["<b>Job Radar: a source might be broken</b>", ""]
    for source, problem in sorted(problems.items()):
        lines.append(f"<b>{html.escape(source)}</b>\n{html.escape(problem)}")
    send_message("\n".join(lines))
    return 1


if __name__ == "__main__":
    sample = [
        Job(
            id="nofluffjobs:demo",
            title="Junior Python Developer <test>",
            company="Example Sp. z o.o.",
            location="Warszawa, Remote",
            seniority="Junior",
            url="https://example.com/job/1?a=b&c=d",
            source="nofluffjobs",
        ),
        Job(
            id="ashby:snowflake:demo",
            title="Software Engineer Intern - Warsaw Security",
            company="Snowflake",
            location="PL-Warsaw",
            seniority="Intern",
            url="https://example.com/job/2",
            source="ashby:snowflake",
        ),
    ]
    print(f"configured: {is_configured()}")
    print(f"messages sent: {notify_jobs(sample)}")
    notify_problems(
        {
            "pracujpl": "returned 0 results (previously up to 197)",
            "justjoinit": "fetch failed: HTTP 503",
        }
    )
