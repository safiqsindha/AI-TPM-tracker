"""Hard filters. A job either passes all of these or is dropped with a reason
(so the report can group dropped counts by which filter killed them)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jobtracker.models import JobPosting

_NON_US_DENYLIST = [
    "united kingdom", "london", "uk", "canada", "toronto", "vancouver",
    "india", "bangalore", "bengaluru", "hyderabad", "germany", "berlin",
    "munich", "europe", "emea", "apac", "singapore", "japan", "tokyo",
    "australia", "sydney", "ireland", "dublin", "france", "paris",
    "netherlands", "amsterdam", "poland", "china", "israel",
]

_YEARS_RE = re.compile(r"(\d+)\+?\s*years?")


@dataclass
class FilterResult:
    passed: bool
    drop_reason: str | None = None
    flags: list[str] = field(default_factory=list)


def _hay(job: JobPosting) -> str:
    return f"{job.title}\n{job.description}".lower()


def _check_location(job: JobPosting, cfg: dict) -> bool:
    loc_cfg = cfg["location"]
    locations_text = job.locations_text.lower()
    remote_policy = (job.remote_policy or "").lower()

    metro_match = any(kw in locations_text for kw in loc_cfg["allowed_metro_keywords"])
    if metro_match:
        return True

    if loc_cfg.get("remote_us_allowed") and "remote" in remote_policy:
        names_non_us_only = any(bad in locations_text for bad in _NON_US_DENYLIST)
        mentions_us = (
            not locations_text
            or "us" == locations_text.strip()
            or "united states" in locations_text
            or "usa" in locations_text
            or re.search(r"\bus\b", locations_text)
        )
        if not names_non_us_only or mentions_us:
            return True

    return False


def _check_function(job: JobPosting, cfg: dict) -> tuple[bool, bool]:
    """Returns (passed, was_unclear)."""
    fn_cfg = cfg["function"]
    title_lower = job.title.lower()
    hay = _hay(job)

    allowed_in_title = any(kw in title_lower for kw in fn_cfg["allowed_keywords"])
    drop_in_title = any(kw in title_lower for kw in fn_cfg["drop_keywords"])

    if allowed_in_title:
        return True, False
    if drop_in_title:
        return False, False

    # Title is ambiguous (e.g. "Program Manager, GPU Fleet" already caught above,
    # but something like a generic "Manager" title) -- fall back to description.
    allowed_in_desc = any(kw in hay for kw in fn_cfg["allowed_keywords"])
    drop_in_desc = any(kw in hay for kw in fn_cfg["drop_keywords"])
    if allowed_in_desc and not drop_in_desc:
        return True, False
    return False, True


def _check_level(job: JobPosting, cfg: dict, estimated_total_high: int) -> tuple[bool, str | None]:
    lvl_cfg = cfg["level"]
    title_lower = job.title.lower()
    hay = _hay(job)

    if any(kw in title_lower for kw in lvl_cfg["junior_titles"]):
        return False, "JUNIOR_LEVEL"

    years_hits = [int(n) for n in _YEARS_RE.findall(hay)]
    if any(y >= lvl_cfg["max_years_required"] for y in years_hits):
        return False, "TOO_MANY_YEARS_REQUIRED"

    is_director_plus = any(kw in title_lower for kw in lvl_cfg["director_plus_titles"])
    if is_director_plus:
        if estimated_total_high >= lvl_cfg["director_exceptional_comp_total"]:
            return True, None
        return False, "DIRECTOR_PLUS_TITLE"

    return True, None


def _check_amazon_pivot(job: JobPosting, cfg: dict) -> bool:
    hay = _hay(job)
    pivot_kws = cfg["companies"]["amazon_ai_pivot_keywords"]
    giveaway_kws = cfg["companies"]["amazon_hardware_qual_giveaway_keywords"]

    has_pivot_signal = any(kw in hay for kw in pivot_kws)
    has_giveaway = any(kw in hay for kw in giveaway_kws)

    return has_pivot_signal and not has_giveaway


def filter_job(job: JobPosting, cfg: dict, estimated_total_high: int) -> FilterResult:
    flags: list[str] = []

    if job.special_rule == "ai_pivot_required":
        if not _check_amazon_pivot(job, cfg):
            return FilterResult(False, "AMAZON_NOT_AI_PIVOT")

    fn_passed, fn_unclear = _check_function(job, cfg)
    if not fn_passed:
        return FilterResult(False, "FUNCTION_MISMATCH" if not fn_unclear else "FUNCTION_UNCLEAR")

    lvl_passed, lvl_reason = _check_level(job, cfg, estimated_total_high)
    if not lvl_passed:
        return FilterResult(False, lvl_reason)

    if not _check_location(job, cfg):
        return FilterResult(False, "LOCATION_MISMATCH")

    base_min = job.comp_min
    if base_min is None:
        flags.append("COMP_UNKNOWN")
    else:
        threshold = (
            cfg["compensation"]["ai_base_min"]
            if job.category == "ai"
            else cfg["compensation"]["hardware_base_min"]
        )
        if base_min < threshold:
            return FilterResult(False, "COMP_TOO_LOW")

    return FilterResult(True, None, flags)
