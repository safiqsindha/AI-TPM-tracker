from jobtracker.scrapers.playwright_generic import PlaywrightGenericScraper, parse_job_list_html

SCRAPE_CONFIG = {
    "url": "https://example.com/careers",
    "job_list_selector": "a.job-link",
    "link_attr": "href",
    "detail_page": False,
    "description_selector": "body",
}

LIST_HTML = """
<html><body>
<a class="job-link" href="/jobs/123">Senior Technical Program Manager <span class="loc">Seattle, WA</span></a>
<a class="job-link" href="/jobs/124">Software Engineer <span class="loc">Remote</span></a>
<a class="job-link" href="/jobs/123">Senior Technical Program Manager <span class="loc">Seattle, WA</span></a>
</body></html>
"""


def test_parse_job_list_html_extracts_and_the_caller_dedupes():
    listings = parse_job_list_html(LIST_HTML, SCRAPE_CONFIG)
    assert len(listings) == 3  # dedup happens in fetch_raw, not in the pure parser
    assert listings[0]["url"] == "/jobs/123"
    assert "Senior Technical Program Manager" in listings[0]["title"]


def test_normalize_builds_job_postings_without_a_browser():
    company_cfg = {
        "name": "CoreWeave",
        "ats": "custom",
        "category": "hardware",
        "tier_points": 18,
        "comp_band": "neocloud",
        "scrape_config": SCRAPE_CONFIG,
    }
    raw = [
        {
            "title": "Senior Technical Program Manager, GPU Fleet",
            "url": "https://example.com/jobs/123",
            "location": "Seattle, WA",
            "description_html": "<p>Own our GPU fleet and vendor management. $210,000 - $250,000.</p>",
        }
    ]

    jobs = PlaywrightGenericScraper().normalize(company_cfg, raw)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.company == "CoreWeave"
    assert job.external_id == "123"
    assert job.comp_min == 210000
    assert job.comp_max == 250000
    assert job.locations == ["Seattle, WA"]
