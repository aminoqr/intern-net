"""The normalized job record every fetcher must produce."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Job:
    """A single posting, normalized across all sources.

    Fetchers translate their source's payload into this and nothing else, so
    main.py never has to know where a job came from.
    """

    id: str  # source + slug, used for dedup
    title: str
    company: str
    location: str
    seniority: str
    url: str
    source: str  # e.g. "nofluffjobs", "greenhouse:point72", "ashby:nord-security"
    posted_at: Optional[str] = None  # ISO 8601 where the source provides it

    def __str__(self) -> str:
        return f"{self.title} @ {self.company} ({self.location}) [{self.source}]"


def normalize_text(value: Optional[str]) -> str:
    """Lowercase, strip Polish diacritics, collapse whitespace.

    Both the filter and the cross-source dedup compare on this, so "Młodszy
    Programista" and "mlodszy programista" are the same string by the time any
    matching happens.
    """
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    # ł has no combining form, so NFKD leaves it intact.
    ascii_only = ascii_only.replace("ł", "l").replace("Ł", "L")
    return re.sub(r"\s+", " ", ascii_only).strip().lower()
