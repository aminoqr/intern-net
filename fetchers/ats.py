"""Generic Greenhouse / Ashby / Lever fetcher, parameterized by board slug.

All three expose a public JSON job board API that needs no key. Only the
response shape differs, so there is one normalizer per provider and everything
else is shared.

Board slugs must be verified before being enabled in config -- a wrong slug is
a 404, which would fire the fail-loud alert on every run.
"""

from __future__ import annotations

from typing import Callable, Optional

import config
from fetchers.base import FetchError, fetch_json
from models import Job, iso_from_epoch_ms

BOARD_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
}


def _clean_join(values: list) -> str:
    """Join location fragments, dropping blanks and duplicates."""
    out: list[str] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("name") or value.get("location") or value.get("locationName")
        if value and isinstance(value, str) and value not in out:
            out.append(value.strip())
    return ", ".join(out)


def _greenhouse(job: dict, company: str, source: str) -> Job:
    return Job(
        id=f"{source}:{job.get('id')}",
        title=(job.get("title") or "").strip(),
        company=(job.get("company_name") or company).strip(),
        location=_clean_join([job.get("location")]),
        # Greenhouse exposes no seniority field; the filter falls back to title.
        seniority="",
        url=job.get("absolute_url") or "",
        source=source,
        posted_at=job.get("first_published") or job.get("updated_at"),
    )


def _ashby(job: dict, company: str, source: str) -> Job:
    locations = [job.get("location")] + list(job.get("secondaryLocations") or [])
    if job.get("isRemote") or job.get("workplaceType") == "Remote":
        locations.append("Remote")
    return Job(
        id=f"{source}:{job.get('id')}",
        title=(job.get("title") or "").strip(),
        company=company,
        location=_clean_join(locations),
        # employmentType is "Intern" for internships, a real seniority signal.
        seniority=job.get("employmentType") or "",
        url=job.get("jobUrl") or job.get("applyUrl") or "",
        source=source,
        posted_at=job.get("publishedAt"),
    )


def _lever(job: dict, company: str, source: str) -> Job:
    categories = job.get("categories") or {}
    locations = list(categories.get("allLocations") or [categories.get("location")])
    if job.get("workplaceType") == "remote":
        locations.append("Remote")
    return Job(
        id=f"{source}:{job.get('id')}",
        title=(job.get("text") or "").strip(),
        company=company,
        location=_clean_join(locations),
        seniority=categories.get("commitment") or "",
        url=job.get("hostedUrl") or job.get("applyUrl") or "",
        source=source,
        posted_at=iso_from_epoch_ms(job.get("createdAt")),
    )


NORMALIZERS: dict[str, Callable[[dict, str, str], Job]] = {
    "greenhouse": _greenhouse,
    "ashby": _ashby,
    "lever": _lever,
}


def _extract_list(payload, ats: str, source: str) -> list:
    # Lever returns a bare array; Greenhouse and Ashby wrap it in {"jobs": [...]}.
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        return payload["jobs"]
    raise FetchError(
        f"{source}: unexpected {ats} response shape "
        f"({type(payload).__name__}, keys: {sorted(payload)[:8] if isinstance(payload, dict) else 'n/a'})"
    )


def fetch_board(company: str, ats: str, slug: str) -> list[Job]:
    """Every listed posting on one company's board."""
    if ats not in BOARD_URLS:
        raise FetchError(f"unsupported ATS type {ats!r} for {company}")

    source = f"{ats}:{slug}"
    payload = fetch_json(BOARD_URLS[ats].format(slug=slug))
    normalize = NORMALIZERS[ats]

    jobs = []
    for raw in _extract_list(payload, ats, source):
        # Ashby flags unlisted postings that should not be surfaced.
        if raw.get("isListed") is False:
            continue
        job = normalize(raw, company, source)
        if job.url and job.title:
            jobs.append(job)
    return jobs


def board_sources() -> list[tuple[str, Callable[[], list[Job]]]]:
    """One (source_name, fetch_fn) pair per enabled board.

    Each board is its own source so that a single broken slug raises for that
    board alone instead of taking out every other company.
    """
    sources = []
    for board in config.enabled_boards():
        company, ats, slug = board["company"], board["ats"], board["slug"]
        sources.append(
            (
                f"{ats}:{slug}",
                lambda c=company, a=ats, s=slug: fetch_board(c, a, s),
            )
        )
    return sources


if __name__ == "__main__":
    for name, fetch_fn in board_sources():
        try:
            found = fetch_fn()
            print(f"{name}: {len(found)} postings")
            for job in found[:3]:
                print(f"  {job}\n    {job.seniority!r} | {job.posted_at} | {job.url}")
        except FetchError as exc:
            print(f"{name}: FAILED -- {exc}")
