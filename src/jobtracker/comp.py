"""Comp parsing (from posted text) and total-comp estimation (from comp_bands.yaml)."""

from __future__ import annotations

import re
from typing import Optional

_RANGE_RE = re.compile(
    r"\$?\s*([\d,]{3,})(?:\s*(k|K))?\s*(?:-|to|–|—)\s*\$?\s*([\d,]{2,})(?:\s*(k|K))?",
)
_SINGLE_RE = re.compile(r"\$\s*([\d,]{3,})(?:\s*(k|K))?\b")


def _to_int(num_str: str, is_k: bool) -> int:
    val = int(num_str.replace(",", ""))
    if is_k:
        val *= 1000
    return val


def parse_comp_from_text(text: str) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Best-effort extraction of a disclosed base/total comp range from free text
    (many US postings must disclose a pay range under state pay-transparency laws).
    Returns (min, max, raw_matched_text) or (None, None, None)."""
    if not text:
        return None, None, None

    m = _RANGE_RE.search(text)
    if m:
        lo = _to_int(m.group(1), bool(m.group(2)))
        hi = _to_int(m.group(3), bool(m.group(4)))
        if lo > hi:
            lo, hi = hi, lo
        # Sanity bound: comp ranges below $10k or above $2M are almost
        # certainly a mis-match on some other number in the description.
        if 10_000 <= lo <= 2_000_000 and 10_000 <= hi <= 2_000_000:
            return lo, hi, m.group(0)

    m = _SINGLE_RE.search(text)
    if m:
        val = _to_int(m.group(1), bool(m.group(2)))
        if 10_000 <= val <= 2_000_000:
            return val, val, m.group(0)

    return None, None, None


# "Manager" alone is ambiguous: "Program Manager" / "Product Manager" are IC
# job-function titles at senior/staff/principal level, not first-line-manager
# titles. Only treat "manager" as a level marker when the title ISN'T one of
# these IC-function titles (e.g. "Manager, Technical Program Management").
_IC_FUNCTION_TITLES = [
    "technical program manager", "program manager",
    "technical product manager", "product manager", "tpm",
]


def infer_level_from_title(title: str) -> str:
    t = (title or "").lower()
    if "principal" in t:
        return "principal"
    if "staff" in t:
        return "staff"

    is_ic_title = any(p in t for p in _IC_FUNCTION_TITLES)
    if not is_ic_title and ("manager" in t or "head of" in t):
        return "manager"

    return "senior"  # default assumption for an unqualified/IC TPM title


def estimate_total_comp_for_job(job, comp_bands_cfg: dict) -> tuple[int, int, str]:
    """Returns (low, high, source).

    If the posting discloses a number, it's almost always base salary (state
    pay-transparency law compliance) -- scale it by the company-tier's
    base_to_total_multiplier to approximate total comp. Otherwise fall back
    to the static band estimate for the inferred level.
    """
    band = comp_bands_cfg.get(job.comp_band) or comp_bands_cfg["default"]
    multiplier = band.get("base_to_total_multiplier", 1.4)

    if job.comp_min is not None:
        low = round(job.comp_min * multiplier)
        high = round((job.comp_max or job.comp_min) * multiplier)
        return low, high, "estimated_from_disclosed_base"

    level = infer_level_from_title(job.title)
    rung = band.get(level) or band.get("senior") or comp_bands_cfg["default"]["senior"]
    return rung["low"], rung["high"], "estimated_from_band"
