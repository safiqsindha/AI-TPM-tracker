from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from jobtracker.models import JobPosting


class Scraper(ABC):
    ats_name: str

    @abstractmethod
    def fetch_raw(self, company_cfg: dict) -> Any:
        """Fetch the raw payload for a company. May be a list of dicts, or
        whatever shape normalize() below expects for this ATS."""

    @abstractmethod
    def normalize(self, company_cfg: dict, raw: Any) -> list[JobPosting]:
        """Turn the raw payload into the shared JobPosting schema."""

    def scrape(self, company_cfg: dict) -> list[JobPosting]:
        raw = self.fetch_raw(company_cfg)
        return self.normalize(company_cfg, raw)
