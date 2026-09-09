"""Telegram delivery: one message per job.

Per-job messages instead of digests, because they are what make Telegram's own
tools work for you: each posting can be forwarded, replied to ("applied"), or
found again on its own. Every message also carries hashtags -- the category
(#internship / #junior), the work mode (#remote / #hybrid / #onsite) and the
city -- and tapping a hashtag in Telegram filters the chat down to just the
messages that carry it. That is the filtering UI, with no bot server needed.

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
import re
import time
from pathlib import Path
from typing import Optional

import config
from fetchers.base import FetchError, fetch_json
from filter import category
from models import Job, normalize_text

API_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"


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


# One message per job means a burst after a quiet weekend can be dozens of
# sends. Telegram tolerates ~1 msg/sec sustained per chat, so sends are spaced
# out here rather than trusting every caller to remember to sleep.
_last_send_at = 0.0


def _throttle() -> None:
    global _last_send_at
    wait = config.TELEGRAM_SEND_INTERVAL - (time.monotonic() - _last_send_at)
    if wait > 0:
        time.sleep(wait)
    _last_send_at = time.monotonic()


def send_message(text: str, chat_id: Optional[str] = None) -> None:
    """Deliver one message, or print it if Telegram is not configured."""
    if not is_configured():
        print("--- telegram (dry run) ---")
        print(text)
        print("--- end ---")
        return

    token, default_chat = _credentials()
    _throttle()
    try:
        response = fetch_json(
            API_TEMPLATE.format(token=token),
            method="POST",
            json_body={
                "chat_id": chat_id or default_chat,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
    except FetchError as exc:
        raise NotifyError(f"Telegram send failed: {exc}") from exc

    if not response.get("ok"):
        raise NotifyError(f"Telegram rejected the message: {response}")


# Hashtags must be a single run of word characters to be tappable in Telegram.
_TAG_JUNK = re.compile(r"[^a-z0-9]+")
# Only plain city names become tags. ATS strings like "PL-Warsaw-Lixa C" would
# collapse into unreadable mush (#plwarsawlixac), so they are skipped.
_PLAIN_CITY = re.compile(r"[a-z]+( [a-z]+)*")


def _tag(text: str) -> Optional[str]:
    word = _TAG_JUNK.sub("", normalize_text(text))
    return f"#{word}" if len(word) >= 2 else None


def hashtags(job: Job) -> list[str]:
    tags = [f"#{category(job)}"]
    for mode in job.work_mode.split(","):
        tag = _tag(mode)
        if tag and tag not in tags:
            tags.append(tag)
    first_city = normalize_text(job.location.split(",")[0])
    if _PLAIN_CITY.fullmatch(first_city):
        tag = _tag(first_city)
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def format_job(job: Job) -> str:
    parts = [f'<a href="{html.escape(job.url, quote=True)}">{html.escape(job.title)}</a>']
    parts.append(f"<b>{html.escape(job.company)}</b>")

    details = [detail for detail in (job.location, job.seniority) if detail]
    if details:
        parts.append(html.escape(" · ".join(details)))
    parts.append(
        f"{html.escape(' '.join(hashtags(job)))} · <i>{html.escape(job.source)}</i>"
    )
    return "\n".join(parts)


def notify_job(job: Job) -> None:
    """Send one job as its own message."""
    send_message(format_job(job))


def notify_problems(problems: dict[str, str]) -> int:
    """Send the fail-loud alert for suspect sources.

    Sent as its own message rather than appended to the job list: the whole
    point is that it is visible when there are no jobs to report. Always goes
    to the main chat, whatever category channels exist.
    """
    if not problems:
        return 0

    lines = ["<b>Job Radar: a source might be broken</b>", ""]
    for source, problem in sorted(problems.items()):
        lines.append(f"<b>{html.escape(source)}</b>\n{html.escape(problem)}")
    send_message("\n".join(lines))
    return 1


if __name__ == "__main__":
    samples = [
        Job(
            id="nofluffjobs:demo",
            title="Junior Python Developer <test>",
            company="Example Sp. z o.o.",
            location="Warszawa",
            seniority="Junior",
            url="https://example.com/job/1?a=b&c=d",
            source="nofluffjobs",
            work_mode="remote, hybrid",
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
    for sample in samples:
        notify_job(sample)
    notify_problems(
        {
            "pracujpl": "returned 0 results (previously up to 197)",
            "justjoinit": "fetch failed: HTTP 503",
        }
    )
