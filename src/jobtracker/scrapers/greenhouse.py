"""Greenhouse Job Board API.

Public, unauthenticated, well-documented:
    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

`board_token` is the slug in the company's greenhouse.io/embed URL, e.g.
boards.greenhouse.io/anthropic -> board_token "anthropic".
"""

from __future__ import annotations

import requests

from jobtracker.comp import parse_comp_from_text
from jobtracker.models import JobPosting
from jobtracker.scrapers.base import Scraper
from jobtracker.scrapers.common import HTTP_HEADERS, REQUEST_TIMEOUT_SECONDS, infer_remote_policy, strip_html

API_URL = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"


class GreenhouseScraper(Scraper):
    ats_name = "greenhouse"

    def fetch_raw(self, company_cfg: dict) -> list[dict]:
        url = API_URL.format(board_token=company_cfg["board_token"])
        resp = requests.get(
            url, params={"content": "true"}, timeout=REQUEST_TIMEOUT_SECONDS, headers=HTTP_HEADERS
        )
        resp.raise_for_status()
        return resp.json().get("jobs", [])

    def normalize(self, company_cfg: dict, raw: list[dict]) -> list[JobPosting]:
        jobs = []
        for item in raw:
            description = strip_html(item.get("content", ""))
            locations = []
            if item.get("location", {}).get("name"):
                locations.append(item["location"]["name"])
            for office in item.get("offices") or []:
                name = office.get("name")
                if name and name not in locations:
                    locations.append(name)

            comp_min, comp_max, comp_raw = parse_comp_from_text(description)
            departments = item.get("departments") or []

            jobs.append(
                JobPosting(
                    company=company_cfg["name"],
                    external_id=str(item["id"]),
                    ats=self.ats_name,
                    title=(item.get("title") or "").strip(),
                    url=item.get("absolute_url", ""),
                    category=company_cfg["category"],
                    tier_points=company_cfg["tier_points"],
                    comp_band=company_cfg["comp_band"],
                    team=departments[0].get("name") if departments else None,
                    locations=locations,
                    remote_policy=infer_remote_policy(locations, description),
                    posted_date=item.get("updated_at"),
                    comp_min=comp_min,
                    comp_max=comp_max,
                    comp_currency="USD" if comp_min else None,
                    comp_raw=comp_raw,
                    description=description,
                    flag=company_cfg.get("flag"),
                    special_rule=company_cfg.get("special_rule"),
                    notes=company_cfg.get("notes"),
                )
            )
        return jobs
