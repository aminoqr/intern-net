"""Just Join IT fetcher.

The internal JSON API (api.justjoin.it/v2/user-panel/offers) is not usable: it
answers 503 to every header combination tried, from a plain call up to a full
browser header set with Origin and Referer. So this reads the data the page
already ships instead.

Just Join IT is a Next.js App Router site, so the server-rendered payload
arrives as a sequence of self.__next_f.push([1, "<chunk>"]) calls. Joining the
chunks yields the React Flight payload, which contains the offer list verbatim
as {"meta": {...}, "data": [{"applyUrl": ..., "slug": ..., "title": ...}]}.

As an integrity check the extracted count is compared against the ld+json
ItemList the page also publishes. If the RSC format changes and extraction
silently degrades, that mismatch raises instead of quietly returning nothing.
"""

from __future__ import annotations

import json
import re

import config
from fetchers.base import FetchError, fetch_text
from models import Job

SOURCE = "justjoinit"
JOB_URL_TEMPLATE = "https://justjoin.it/job-offer/{slug}"
PUSH_MARKER = "self.__next_f.push("
DATA_MARKER = '"data":['
LD_JSON = re.compile(
    r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)

_decoder = json.JSONDecoder()


def _rsc_payload(html: str) -> str:
    """Concatenate every streamed RSC chunk into one string."""
    chunks = []
    index = 0
    while True:
        index = html.find(PUSH_MARKER, index)
        if index < 0:
            break
        try:
            pushed, _ = _decoder.raw_decode(html, index + len(PUSH_MARKER))
        except ValueError:
            pushed = None
        if isinstance(pushed, list) and len(pushed) > 1 and isinstance(pushed[1], str):
            chunks.append(pushed[1])
        index += len(PUSH_MARKER)

    if not chunks:
        raise FetchError(f"{SOURCE}: no {PUSH_MARKER}... chunks in page")
    return "".join(chunks)


def _offer_records(payload: str) -> list[dict]:
    """The first "data" array that actually holds offer records."""
    index = 0
    while True:
        index = payload.find(DATA_MARKER, index)
        if index < 0:
            return []
        try:
            records, _ = _decoder.raw_decode(payload, index + len(DATA_MARKER) - 1)
        except ValueError:
            records = None
        if isinstance(records, list) and records and isinstance(records[0], dict):
            if {"slug", "title", "companyName"} <= set(records[0]):
                return records
        index += len(DATA_MARKER)


def _ld_json_count(html: str) -> int:
    """How many job URLs the page advertises in its structured data."""
    for block in LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        parts = data.get("hasPart")
        if isinstance(parts, list) and parts:
            return len(parts)
    return 0


def _to_jobs(record: dict) -> list[Job]:
    title = (record.get("title") or record.get("body") or "").strip()
    company = (record.get("companyName") or "").strip()
    seniority = record.get("experienceLevel") or ""
    posted_at = record.get("publishedAt") or record.get("lastPublishedAt")
    is_remote = record.get("workplaceType") == "remote"

    # multilocation carries one slug per city; fall back to the top-level pair.
    places = record.get("multilocation") or [
        {"slug": record.get("slug"), "city": record.get("city")}
    ]

    jobs = []
    for place in places:
        slug = place.get("slug") or record.get("slug")
        if not slug:
            continue
        location = (place.get("city") or record.get("city") or "").strip()
        if is_remote and location:
            location = f"{location}, Remote"
        jobs.append(
            Job(
                id=f"{SOURCE}:{slug}",
                title=title,
                company=company,
                location=location,
                seniority=seniority,
                url=JOB_URL_TEMPLATE.format(slug=slug),
                source=SOURCE,
                posted_at=posted_at,
            )
        )
    return jobs


def fetch() -> list[Job]:
    jobs: dict[str, Job] = {}

    for search_url in config.JUSTJOINIT_SEARCH_URLS:
        html = fetch_text(search_url)
        records = _offer_records(_rsc_payload(html))
        advertised = _ld_json_count(html)

        if not records:
            raise FetchError(
                f"{SOURCE}: found no offer records in the RSC payload "
                f"(page advertises {advertised} offers) -- the embedded format likely changed"
            )
        # Half is a generous floor; it catches a broken extractor without
        # firing on the normal small drift between the two representations.
        if advertised and len(records) < advertised / 2:
            raise FetchError(
                f"{SOURCE}: extracted only {len(records)} of {advertised} advertised "
                f"offers -- the embedded format likely changed"
            )

        for record in records:
            for job in _to_jobs(record):
                jobs[job.id] = job

    return list(jobs.values())


if __name__ == "__main__":
    found = fetch()
    print(f"{SOURCE}: {len(found)} postings")
    for job in found[:5]:
        print(f"  {job}\n    {job.seniority!r} | {job.posted_at} | {job.url}")
