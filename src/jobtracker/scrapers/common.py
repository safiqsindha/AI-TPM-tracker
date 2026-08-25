"""Helpers shared across scrapers."""

from __future__ import annotations

import re

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; tpm-job-tracker/0.1; "
        "personal job search tool; +https://github.com/)"
    )
}

REQUEST_TIMEOUT_SECONDS = 30


def infer_remote_policy(locations: list[str], description: str) -> str:
    locs_text = " ".join(locations).lower()
    desc = (description or "").lower()

    if re.search(r"\bremote\b", locs_text):
        return "remote"
    if "hybrid" in locs_text or "hybrid" in desc:
        return "hybrid"
    if re.search(r"\bremote\b", desc) and not locations:
        return "remote"
    return "onsite" if locations else "unknown"


def strip_html(html: str) -> str:
    from bs4 import BeautifulSoup

    return BeautifulSoup(html or "", "html.parser").get_text("\n")
