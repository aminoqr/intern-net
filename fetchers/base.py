"""Shared HTTP plumbing for every fetcher.

Two things here are the result of testing against the live sources rather than
preference:

1. The browser header set is load-bearing. Pracuj.pl answers a bare request
   with 403 and this header set with 200.
2. This uses stdlib urllib rather than requests. Pracuj.pl fingerprints the
   client below the HTTP layer and returns 403 to requests/urllib3 even with
   byte-identical headers and a stock SSL context, while stdlib urllib gets
   200. urllib also handles the other four endpoints fine, so standardizing on
   it means one client, and no third-party runtime dependency at all.
"""

from __future__ import annotations

import gzip
import json as jsonlib
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Any, Optional

import config

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="120", "Not(A:Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# Worth retrying: rate limits and transient upstream failures.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class FetchError(Exception):
    """A source could not be fetched or parsed.

    Fetchers raise this instead of returning an empty list. main.py turns it
    into a fail-loud Telegram alert -- swallowing it is exactly the silent
    failure the design principles forbid.
    """


def _decode_body(raw: bytes, encoding: Optional[str]) -> bytes:
    if encoding == "gzip":
        return gzip.decompress(raw)
    if encoding == "deflate":
        return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def _open(
    url: str,
    method: str = "GET",
    params: Optional[dict] = None,
    body: Optional[bytes] = None,
    headers: Optional[dict] = None,
) -> bytes:
    if params:
        separator = "&" if urllib.parse.urlparse(url).query else "?"
        url = f"{url}{separator}{urllib.parse.urlencode(params, doseq=True)}"

    merged = dict(BROWSER_HEADERS)
    if headers:
        merged.update(headers)

    last_error = "unknown error"
    for attempt in range(config.MAX_RETRIES):
        request = urllib.request.Request(url, data=body, headers=merged, method=method)
        try:
            with urllib.request.urlopen(request, timeout=config.REQUEST_TIMEOUT) as resp:
                return _decode_body(resp.read(), resp.headers.get("Content-Encoding"))
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code not in RETRY_STATUSES:
                raise FetchError(f"{method} {url} returned {last_error}") from exc
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            last_error = str(exc)

        if attempt < config.MAX_RETRIES - 1:
            time.sleep(1.5 * (2**attempt))

    raise FetchError(f"{method} {url} failed after {config.MAX_RETRIES} attempts: {last_error}")


def fetch_json(
    url: str,
    method: str = "GET",
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> Any:
    merged = {"Accept": "application/json"}
    body = None
    if json_body is not None:
        body = jsonlib.dumps(json_body).encode("utf-8")
        merged["Content-Type"] = "application/json"
    if headers:
        merged.update(headers)

    raw = _open(url, method=method, params=params, body=body, headers=merged)
    try:
        return jsonlib.loads(raw)
    except ValueError as exc:
        raise FetchError(f"{url} did not return JSON: {exc}") from exc


def fetch_text(
    url: str, params: Optional[dict] = None, headers: Optional[dict] = None
) -> str:
    return _open(url, params=params, headers=headers).decode("utf-8", "replace")
