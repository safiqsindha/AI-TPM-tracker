"""Generic config-driven scraper for JS-rendered career pages that don't
expose a documented public API (CoreWeave, Lambda, Nebius, Crusoe, Meta,
Apple, Astera Labs, Anysphere*, Sierra*, xAI, SambaNova, Groq, Amazon).

* Anysphere/Sierra are configured under Ashby in companies.yaml; this
  scraper is the fallback path for everything else.

Per-company `scrape_config` (see companies.yaml) drives selectors:
    url, wait_for_selector, job_list_selector, title_selector (optional),
    location_selector (optional), link_attr, detail_page (bool),
    description_selector.

The HTML parsing (`parse_job_list_html`) is a pure function so it can be
unit-tested with static HTML fixtures without launching a real browser.
Only `fetch_raw` touches Playwright.
"""

from __future__ import annotations

import hashlib
import os
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from jobtracker.comp import parse_comp_from_text
from jobtracker.models import JobPosting
from jobtracker.scrapers.base import Scraper
from jobtracker.scrapers.common import HTTP_HEADERS, infer_remote_policy, strip_html

NAV_TIMEOUT_MS = 45_000
SELECTOR_TIMEOUT_MS = 20_000


def parse_job_list_html(html: str, scrape_config: dict) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    elements = soup.select(scrape_config["job_list_selector"])

    link_attr = scrape_config.get("link_attr", "href")
    title_selector = scrape_config.get("title_selector")
    location_selector = scrape_config.get("location_selector")

    results = []
    for el in elements:
        anchor = el if el.name == "a" else el.select_one("a")
        href = anchor.get(link_attr) if anchor else None
        if not href:
            continue

        if title_selector:
            title_el = el.select_one(title_selector)
            title = title_el.get_text(strip=True) if title_el else el.get_text(strip=True)
        else:
            title = el.get_text(strip=True)

        location = None
        if location_selector:
            loc_el = el.select_one(location_selector)
            location = loc_el.get_text(strip=True) if loc_el else None

        results.append({"title": title, "url": href, "location": location})
    return results


def _dedupe_by_url(items: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for item in items:
        if item["url"] not in seen:
            seen.add(item["url"])
            deduped.append(item)
    return deduped


def _external_id_from_url(url: str) -> str:
    path_part = url.rstrip("/").split("/")[-1]
    if path_part and len(path_part) < 80:
        return path_part
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


class PlaywrightGenericScraper(Scraper):
    ats_name = "custom"

    def fetch_raw(self, company_cfg: dict) -> list[dict]:
        from playwright.sync_api import sync_playwright  # imported lazily: heavy, network-only dependency

        cfg = company_cfg["scrape_config"]
        launch_kwargs = {}
        exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        if exe:
            launch_kwargs["executable_path"] = exe

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, **launch_kwargs)
            try:
                context = browser.new_context(user_agent=HTTP_HEADERS["User-Agent"])
                page = context.new_page()
                page.goto(cfg["url"], timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
                if cfg.get("wait_for_selector"):
                    page.wait_for_selector(cfg["wait_for_selector"], timeout=SELECTOR_TIMEOUT_MS)

                listings = parse_job_list_html(page.content(), cfg)
                for item in listings:
                    item["url"] = urljoin(cfg["url"], item["url"])
                listings = _dedupe_by_url(listings)

                if cfg.get("detail_page"):
                    desc_selector = cfg.get("description_selector", "body")
                    for item in listings:
                        try:
                            page.goto(item["url"], timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
                            page.wait_for_selector(desc_selector, timeout=SELECTOR_TIMEOUT_MS)
                            item["description_html"] = page.inner_html(desc_selector)
                        except Exception:
                            item["description_html"] = ""

                return listings
            finally:
                browser.close()

    def normalize(self, company_cfg: dict, raw: list[dict]) -> list[JobPosting]:
        jobs = []
        for item in raw:
            description = strip_html(item.get("description_html", ""))
            locations = [item["location"]] if item.get("location") else []
            comp_min, comp_max, comp_raw = parse_comp_from_text(description)

            jobs.append(
                JobPosting(
                    company=company_cfg["name"],
                    external_id=_external_id_from_url(item["url"]),
                    ats=self.ats_name,
                    title=(item.get("title") or "").strip() or "(untitled posting)",
                    url=item["url"],
                    category=company_cfg["category"],
                    tier_points=company_cfg["tier_points"],
                    comp_band=company_cfg["comp_band"],
                    team=None,
                    locations=locations,
                    remote_policy=infer_remote_policy(locations, description),
                    posted_date=None,
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
