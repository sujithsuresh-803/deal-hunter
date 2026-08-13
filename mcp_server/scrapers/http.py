"""Shared HTTP fetch layer: realistic headers, retries, timeouts.

Live e-commerce sites (especially Amazon.in / Flipkart) run aggressive bot
detection. This layer does the polite best-effort things — real browser headers,
a small retry with backoff — but it will still get CAPTCHA-walled sometimes.
When that happens the caller decides whether to fall back to sample data.
"""
from __future__ import annotations

import os
import random
import time

import httpx

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _headers() -> dict:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


class BlockedError(RuntimeError):
    """Raised when a site returns a bot-wall / CAPTCHA / 503 we can't get past."""


def fetch(url: str, *, retries: int = 2) -> str:
    """GET a URL and return HTML text, or raise BlockedError."""
    timeout = float(os.getenv("DEAL_HUNTER_TIMEOUT", "20"))
    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        try:
            with httpx.Client(
                timeout=timeout, follow_redirects=True, headers=_headers()
            ) as client:
                resp = client.get(url)
            if resp.status_code in (403, 429, 503):
                raise BlockedError(f"{url} -> HTTP {resp.status_code}")
            resp.raise_for_status()
            body = resp.text
            # Heuristic bot-wall detection.
            lowered = body[:5000].lower()
            if "captcha" in lowered or "enter the characters you see" in lowered:
                raise BlockedError(f"{url} -> CAPTCHA wall")
            return body
        except (httpx.HTTPError, BlockedError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1) + random.random())

    raise BlockedError(str(last_exc))
