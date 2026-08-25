import json
import os

import responses

from jobtracker.scrapers.ashby import AshbyScraper

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "ashby_jobs.json")

COMPANY_CFG = {
    "name": "OpenAI",
    "ats": "ashby",
    "board_name": "openai",
    "category": "ai",
    "tier_points": 30,
    "comp_band": "frontier_ai_lab",
}


@responses.activate
def test_ashby_fetch_and_normalize():
    with open(FIXTURE) as f:
        payload = json.load(f)

    responses.add(
        responses.GET,
        "https://api.ashbyhq.com/posting-api/job-board/openai",
        json=payload,
        status=200,
    )

    scraper = AshbyScraper()
    jobs = scraper.scrape(COMPANY_CFG)

    assert len(jobs) == 2

    tpm = next(j for j in jobs if j.external_id == "abc123")
    assert tpm.title == "Staff Technical Program Manager, Infrastructure"
    assert tpm.comp_min == 300000
    assert tpm.comp_max == 400000
    assert tpm.comp_currency == "USD"
    assert tpm.remote_policy == "remote"
    assert tpm.team == "Infrastructure"

    recruiter = next(j for j in jobs if j.external_id == "def456")
    assert recruiter.comp_min is None
    assert recruiter.remote_policy != "remote"
