"""Pracuj.pl fetcher.

No HTML parsing. The page ships its entire React Query cache in the
__NEXT_DATA__ script tag, so the offers come out as clean JSON:

    props.pageProps.dehydratedState.queries[] -> the query whose queryKey
    starts with "jobOffers" -> state.data.groupedOffers[]

Two things worth knowing:

- The cache also holds a "positionedJobOffers" query with the same shape. That
  one is promoted/sponsored placements, so we select the query by key rather
  than by index.
- An offer is "grouped": one posting advertised in five cities is one
  groupedOffers entry with five nested offers[], each with its own URL. We
  flatten to one Job per city so the location filter can match a specific city
  and link to that city's posting. The cross-source dedup then collapses them.
"""

from __future__ import annotations

import json
import re

import config
from fetchers.base import FetchError, fetch_text
from models import Job

SOURCE = "pracujpl"
NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
OFFERS_PER_PAGE = 50
# Bounded so a filter change that widens the result set cannot turn one run
# into hundreds of requests.
MAX_PAGES = 4


def _offers_payload(html: str) -> dict:
    match = NEXT_DATA.search(html)
    if not match:
        raise FetchError(f"{SOURCE}: no __NEXT_DATA__ script in page")
    try:
        data = json.loads(match.group(1))
    except ValueError as exc:
        raise FetchError(f"{SOURCE}: __NEXT_DATA__ was not valid JSON: {exc}") from exc

    try:
        queries = data["props"]["pageProps"]["dehydratedState"]["queries"]
    except (KeyError, TypeError) as exc:
        raise FetchError(f"{SOURCE}: unexpected __NEXT_DATA__ layout ({exc})") from exc

    for query in queries:
        key = query.get("queryKey") or []
        if key and key[0] == "jobOffers":
            payload = (query.get("state") or {}).get("data") or {}
            if "groupedOffers" in payload:
                return payload

    raise FetchError(
        f"{SOURCE}: no 'jobOffers' query with groupedOffers "
        f"(saw {[str((q.get('queryKey') or [None])[0]) for q in queries][:6]})"
    )


def _seniority(group: dict) -> str:
    levels = group.get("positionLevels") or []
    return ", ".join(level for level in levels if level)


def _to_jobs(group: dict) -> list[Job]:
    """One Job per advertised city."""
    title = (group.get("jobTitle") or "").strip()
    company = (group.get("companyName") or "").strip()
    seniority = _seniority(group)
    posted_at = group.get("initialPublicated")
    remote_allowed = bool(group.get("isRemoteWorkAllowed")) or "Praca zdalna" in (
        group.get("workModes") or []
    )

    jobs = []
    for offer in group.get("offers") or []:
        url = offer.get("offerAbsoluteUri")
        if not url:
            continue
        location = (offer.get("displayWorkplace") or "").strip()
        # isWholePoland is deliberately ignored: it is set even on plainly
        # on-site, per-city postings, so treating it as nationwide would append
        # "Poland" to every city and defeat the location filter entirely.
        if remote_allowed and location:
            location = f"{location}, Remote"
        jobs.append(
            Job(
                id=f"{SOURCE}:{offer.get('partitionId') or group.get('groupId')}",
                title=title,
                company=company,
                location=location,
                seniority=seniority,
                url=url,
                source=SOURCE,
                posted_at=posted_at,
            )
        )
    return jobs


def fetch() -> list[Job]:
    """Every offer across the configured searches, paginated."""
    jobs: dict[str, Job] = {}

    for search_url in config.PRACUJPL_SEARCH_URLS:
        for page in range(1, MAX_PAGES + 1):
            payload = _offers_payload(fetch_text(search_url, params={"pn": page}))
            groups = payload.get("groupedOffers") or []
            for group in groups:
                for job in _to_jobs(group):
                    jobs[job.id] = job

            total = payload.get("offersTotalCount") or 0
            if len(groups) < OFFERS_PER_PAGE or page * OFFERS_PER_PAGE >= total:
                break

    return list(jobs.values())


if __name__ == "__main__":
    found = fetch()
    print(f"{SOURCE}: {len(found)} postings")
    for job in found[:5]:
        print(f"  {job}\n    {job.seniority!r} | {job.posted_at} | {job.url}")
