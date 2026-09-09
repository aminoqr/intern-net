"""Keyword, seniority and location matching.

Three gates, all applied to diacritic-stripped lowercase text:

1. Role     -- is this actually a software engineering job?
2. Seniority -- is it entry-level, and not secretly a mid/senior ask?
3. Location -- Warsaw or remote-in-Poland?

Matching is whole-word by default rather than substring, because substring
matching is wrong in ways that matter: "intern" appears inside "International"
and "Internal", which would flood the radar with non-engineering roles.
"""

from __future__ import annotations

import re
from typing import Optional

import config
from models import Job, normalize_text


def _compile(keyword: str) -> re.Pattern:
    """Turn a config keyword into a matcher.

    Trailing "*" means prefix match (for Polish inflection). Boundaries are
    only applied on sides where the keyword actually starts/ends with a word
    character, so ".net" and "c++" still match.
    """
    is_prefix = keyword.endswith("*")
    normalized = normalize_text(keyword[:-1] if is_prefix else keyword)
    left = r"(?<!\w)" if normalized[:1].isalnum() else ""
    right = "" if is_prefix or not normalized[-1:].isalnum() else r"(?!\w)"
    return re.compile(left + re.escape(normalized) + right)


def _compile_all(keywords: list[str]) -> list[re.Pattern]:
    return [_compile(keyword) for keyword in keywords]


ENTRY_LEVEL = _compile_all(config.ENTRY_LEVEL_KEYWORDS)
SENIOR = _compile_all(config.SENIOR_KEYWORDS)
ROLE = _compile_all(config.ROLE_KEYWORDS)
ROLE_EXCLUDED = _compile_all(config.ROLE_EXCLUSIONS)
SENIORITY_OK = _compile_all(config.ACCEPTED_SENIORITY)
SENIORITY_BAD = _compile_all(config.REJECTED_SENIORITY)
LOCATIONS = _compile_all(config.ACCEPTED_LOCATIONS)


def _hit(patterns: list[re.Pattern], text: str) -> Optional[str]:
    """The first matched substring, or None."""
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def rejection_reason(job: Job) -> Optional[str]:
    """Why this job was dropped, or None if it passes every gate.

    Returning the reason rather than a bare bool is what makes the filter
    tunable -- see the __main__ block, which prints the drop reasons in bulk.
    """
    title = normalize_text(job.title)
    seniority = normalize_text(job.seniority)
    location = normalize_text(job.location)

    # 1. Role gate.
    if not _hit(ROLE, title):
        return "role: no engineering keyword"
    excluded = _hit(ROLE_EXCLUDED, title)
    if excluded:
        return f"role: excluded by {excluded!r}"

    # 2. Seniority gate. A senior marker in the title always wins, so
    #    "Senior Engineer (mentors juniors)" and "Junior/Mid/Senior" are both
    #    dropped even though they match an entry-level keyword.
    senior_marker = _hit(SENIOR, title)
    if senior_marker:
        return f"seniority: title says {senior_marker!r}"

    accepted_by_source = _hit(SENIORITY_OK, seniority)
    entry_in_title = _hit(ENTRY_LEVEL, title)
    if not (accepted_by_source or entry_in_title):
        return "seniority: no entry-level signal"

    rejected_by_source = _hit(SENIORITY_BAD, seniority)
    if rejected_by_source and not accepted_by_source:
        # "Mid, Senior" -> drop. "Junior, Mid" -> keep, still worth applying to.
        return f"seniority: source says {job.seniority!r}"

    # 3. Location gate.
    if not location:
        return None if config.ALLOW_UNKNOWN_LOCATION else "location: unknown"
    if not _hit(LOCATIONS, location):
        return f"location: {job.location!r} out of scope"

    return None


def matches(job: Job) -> bool:
    return rejection_reason(job) is None


def filter_jobs(jobs: list[Job]) -> list[Job]:
    return [job for job in jobs if matches(job)]


if __name__ == "__main__":
    from collections import Counter

    from fetchers import ats, nofluffjobs

    all_jobs = list(nofluffjobs.fetch())
    for name, fetch_fn in ats.board_sources():
        all_jobs.extend(fetch_fn())

    kept, reasons = [], Counter()
    for candidate in all_jobs:
        reason = rejection_reason(candidate)
        if reason is None:
            kept.append(candidate)
        else:
            reasons[reason.split(":")[0]] += 1

    print(f"{len(all_jobs)} fetched -> {len(kept)} kept")
    print("dropped by gate:", dict(reasons))
    print("\nkept:")
    for candidate in kept:
        print(f"  {candidate}")
