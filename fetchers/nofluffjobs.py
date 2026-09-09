"""NoFluffJobs fetcher.

Public JSON search endpoint, no login. Two non-obvious things, both found by
probing the live API:

- salaryCurrency is a *required* query param. Without it the endpoint returns
  400 "Required parameter 'salaryCurrency' is not present", regardless of body.
- posting["url"] is only a slug; the job page is /pl/job/<slug>.
"""

from __future__ import annotations

import config
from fetchers.base import FetchError, fetch_json
from models import Job, iso_from_epoch_ms

API_URL = "https://nofluffjobs.com/api/search/posting"
JOB_URL_TEMPLATE = "https://nofluffjobs.com/pl/job/{slug}"
SOURCE = "nofluffjobs"

# The trainee/junior + Warsaw slice is ~40 postings, so one page covers it.
PAGE_LIMIT = 100


def _location(posting: dict) -> str:
    places = posting.get("location", {}).get("places") or []
    cities = []
    for place in places:
        city = place.get("city")
        # places[] is padded with entries that carry a province but no city.
        if city and city not in cities:
            cities.append(city)
    if posting.get("fullyRemote") and "Remote" not in cities:
        cities.append("Remote")
    return ", ".join(cities)


def _to_job(posting: dict) -> Job:
    slug = posting.get("url") or posting.get("id")
    seniority = posting.get("seniority") or []
    return Job(
        id=f"{SOURCE}:{slug}",
        title=(posting.get("title") or "").strip(),
        company=(posting.get("name") or "").strip(),
        location=_location(posting),
        seniority=", ".join(seniority) if isinstance(seniority, list) else str(seniority),
        url=JOB_URL_TEMPLATE.format(slug=slug),
        source=SOURCE,
        posted_at=iso_from_epoch_ms(posting.get("posted")),
    )


def fetch() -> list[Job]:
    """Every trainee/junior posting in the configured cities."""
    jobs: dict[str, Job] = {}
    for city in config.NOFLUFFJOBS_CITIES:
        payload = fetch_json(
            API_URL,
            method="POST",
            params={
                "limit": PAGE_LIMIT,
                "salaryCurrency": "PLN",
                "salaryPeriod": "month",
                "region": "pl",
            },
            json_body={
                "criteriaSearch": {
                    "seniority": config.NOFLUFFJOBS_SENIORITY,
                    "city": [city],
                }
            },
        )
        postings = payload.get("postings")
        if postings is None:
            raise FetchError(
                f"{SOURCE}: response had no 'postings' key (keys: {sorted(payload)[:8]})"
            )
        for posting in postings:
            job = _to_job(posting)
            # A posting listed for several cities comes back once per query.
            jobs[job.id] = job
    return list(jobs.values())


if __name__ == "__main__":
    found = fetch()
    print(f"{SOURCE}: {len(found)} postings")
    for job in found[:5]:
        print(f"  {job}\n    {job.seniority} | {job.posted_at} | {job.url}")
