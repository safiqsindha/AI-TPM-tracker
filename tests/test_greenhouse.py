import json
import os

import responses

from jobtracker.scrapers.greenhouse import GreenhouseScraper

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "greenhouse_jobs.json")

COMPANY_CFG = {
    "name": "Anthropic",
    "ats": "greenhouse",
    "board_token": "anthropic",
    "category": "ai",
    "tier_points": 30,
    "comp_band": "frontier_ai_lab",
}


@responses.activate
def test_greenhouse_fetch_and_normalize():
    with open(FIXTURE) as f:
        payload = json.load(f)

    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs",
        json=payload,
        status=200,
    )

    scraper = GreenhouseScraper()
    jobs = scraper.scrape(COMPANY_CFG)

    assert len(jobs) == 2

    tpm = next(j for j in jobs if "1234" == j.external_id)
    assert tpm.title == "Senior Technical Program Manager, GPU Fleet"
    assert tpm.company == "Anthropic"
    assert tpm.tier_points == 30
    assert tpm.comp_band == "frontier_ai_lab"
    assert tpm.comp_min == 220000
    assert tpm.comp_max == 260000
    assert "Seattle" in tpm.locations_text
    assert tpm.remote_policy in ("onsite", "hybrid")
    assert "<p>" not in tpm.description

    swe = next(j for j in jobs if j.external_id == "1235")
    assert swe.remote_policy == "remote"
    assert swe.comp_min is None
