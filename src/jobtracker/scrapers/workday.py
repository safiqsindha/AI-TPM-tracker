"""Workday CXS API.

Workday-hosted career sites expose an unauthenticated JSON search API at:
    POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    body: {"appliedFacets": {}, "limit": N, "offset": N, "searchText": "..."}

and a per-posting detail endpoint:
    GET https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{externalPath}

`tenant`, `dc` (data-center subdomain like wd1/wd3/wd5) and `site` vary per
company and must be read off the real careers page (see companies.yaml
`verify: true` notes) -- there's no way to guess `dc` reliably.
"""

from __future__ import annotations

import requests

from jobtracker.comp import parse_comp_from_text
from jobtracker.models import JobPosting
from jobtracker.scrapers.base import Scraper
from jobtracker.scrapers.common import HTTP_HEADERS, REQUEST_TIMEOUT_SECONDS, infer_remote_policy, strip_html

PAGE_SIZE = 20
MAX_OFFSET = 500  # safety cap so a mis-scoped search can't page forever


class WorkdayScraper(Scraper):
    ats_name = "workday"

    def _base_url(self, company_cfg: dict) -> str:
        return (
            f"https://{company_cfg['tenant']}.{company_cfg['dc']}.myworkdayjobs.com"
            f"/wday/cxs/{company_cfg['tenant']}/{company_cfg['site']}"
        )

    def fetch_raw(self, company_cfg: dict) -> list[dict]:
        base = self._base_url(company_cfg)
        search_text = company_cfg.get("search_text", "program manager")

        summaries: list[dict] = []
        offset = 0
        while offset <= MAX_OFFSET:
            resp = requests.post(
                f"{base}/jobs",
                json={"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": search_text},
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={**HTTP_HEADERS, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("jobPostings", [])
            summaries.extend(batch)
            offset += PAGE_SIZE
            if not batch or offset >= data.get("total", len(summaries)):
                break

        combined = []
        for summary in summaries:
            path = summary.get("externalPath")
            detail = {}
            if path:
                try:
                    dresp = requests.get(f"{base}{path}", timeout=REQUEST_TIMEOUT_SECONDS, headers=HTTP_HEADERS)
                    dresp.raise_for_status()
                    detail = dresp.json().get("jobPostingInfo", {})
                except requests.RequestException:
                    detail = {}
            combined.append({"summary": summary, "detail": detail})
        return combined

    def normalize(self, company_cfg: dict, raw: list[dict]) -> list[JobPosting]:
        jobs = []
        for item in raw:
            summary = item["summary"]
            detail = item.get("detail") or {}

            description = strip_html(detail.get("jobDescription", ""))
            title = (detail.get("title") or summary.get("title") or "").strip()

            locations = []
            loc_text = detail.get("location") or summary.get("locationsText")
            if loc_text:
                locations = [l.strip() for l in loc_text.split(",")] if "," in loc_text else [loc_text]
            for extra in detail.get("additionalLocations") or []:
                if extra and extra not in locations:
                    locations.append(extra)

            comp_min, comp_max, comp_raw = parse_comp_from_text(description)
            external_id = str(detail.get("jobReqId") or summary.get("jobPostingId") or summary.get("externalPath"))

            jobs.append(
                JobPosting(
                    company=company_cfg["name"],
                    external_id=external_id,
                    ats=self.ats_name,
                    title=title,
                    url=f"{self._base_url(company_cfg)}{summary.get('externalPath', '')}",
                    category=company_cfg["category"],
                    tier_points=company_cfg["tier_points"],
                    comp_band=company_cfg["comp_band"],
                    team=None,
                    locations=locations,
                    remote_policy=infer_remote_policy(locations, description),
                    posted_date=summary.get("postedOn"),
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
