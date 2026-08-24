"""Normalized job posting schema shared by every scraper."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class JobPosting:
    company: str
    external_id: str
    ats: str
    title: str
    url: str
    category: str  # "ai" | "hardware"
    tier_points: int
    comp_band: str

    team: Optional[str] = None
    locations: list[str] = field(default_factory=list)
    remote_policy: Optional[str] = None  # "remote" | "hybrid" | "onsite" | "unknown"
    posted_date: Optional[str] = None  # ISO date string, best-effort

    comp_min: Optional[int] = None
    comp_max: Optional[int] = None
    comp_currency: Optional[str] = None
    comp_raw: Optional[str] = None

    description: str = ""

    flag: Optional[str] = None  # e.g. "xai_culture_note"
    special_rule: Optional[str] = None  # e.g. "ai_pivot_required"
    notes: Optional[str] = None

    @property
    def job_key(self) -> str:
        return f"{self.company}::{self.external_id}"

    @property
    def locations_text(self) -> str:
        return "; ".join(self.locations) if self.locations else ""

    def to_row(self) -> dict:
        d = asdict(self)
        return d
