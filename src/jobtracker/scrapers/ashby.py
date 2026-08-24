"""Ashby Job Posting API.

Public, unauthenticated:
    GET https://api.ashbyhq.com/posting-api/job-board/{board_name}?includeCompensation=true

`board_name` is the slug from the company's jobs.ashbyhq.com/{board_name} URL.
"""

from __future__ import annotations

import requests

from jobtracker.comp import parse_comp_from_text
from jobtracker.models import JobPosting
from jobtracker.scrapers.base import Scraper
from jobtracker.scrapers.common import HTTP_HEADERS, REQUEST_TIMEOUT_SECONDS, infer_remote_policy, strip_html

API_URL = "https://api.ashbyhq.com/posting-api/job-board/{board_name}"


class AshbyScraper(Scraper):
    ats_name = "ashby"

    def fetch_raw(self, company_cfg: dict) -> list[dict]:
        url = API_URL.format(board_name=company_cfg["board_name"])
        resp = requests.get(
            url,
            params={"includeCompensation": "true"},
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers=HTTP_HEADERS,
        )
        resp.raise_for_status()
        return resp.json().get("jobs", [])

    def _comp_from_payload(self, item: dict, description: str):
        comp = item.get("compensation") or {}
        components = comp.get("summaryComponents") or []
        for component in components:
            lo, hi = component.get("minValue"), component.get("maxValue")
            if lo or hi:
                currency = component.get("currencyCode", "USD")
                return (
                    int(lo) if lo else None,
                    int(hi) if hi else (int(lo) if lo else None),
                    currency,
                    comp.get("compensationTierSummary") or f"{lo}-{hi}",
                )
        # Fall back to scraping the disclosed range out of the description text.
        lo, hi, raw = parse_comp_from_text(description)
        return lo, hi, ("USD" if lo else None), raw

    def normalize(self, company_cfg: dict, raw: list[dict]) -> list[JobPosting]:
        jobs = []
        for item in raw:
            description = strip_html(item.get("descriptionHtml") or item.get("descriptionPlain") or "")
            locations = []
            if item.get("location"):
                locations.append(item["location"])
            for extra in item.get("secondaryLocations") or []:
                name = extra.get("location") if isinstance(extra, dict) else extra
                if name and name not in locations:
                    locations.append(name)

            comp_min, comp_max, currency, comp_raw = self._comp_from_payload(item, description)

            remote_policy = "remote" if item.get("isRemote") else infer_remote_policy(locations, description)

            jobs.append(
                JobPosting(
                    company=company_cfg["name"],
                    external_id=str(item.get("id")),
                    ats=self.ats_name,
                    title=(item.get("title") or "").strip(),
                    url=item.get("jobUrl") or item.get("applyUrl") or "",
                    category=company_cfg["category"],
                    tier_points=company_cfg["tier_points"],
                    comp_band=company_cfg["comp_band"],
                    team=item.get("team") or item.get("department"),
                    locations=locations,
                    remote_policy=remote_policy,
                    posted_date=item.get("publishedAt"),
                    comp_min=comp_min,
                    comp_max=comp_max,
                    comp_currency=currency,
                    comp_raw=str(comp_raw) if comp_raw else None,
                    description=description,
                    flag=company_cfg.get("flag"),
                    special_rule=company_cfg.get("special_rule"),
                    notes=company_cfg.get("notes"),
                )
            )
        return jobs
