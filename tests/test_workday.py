import responses

from jobtracker.scrapers.workday import WorkdayScraper

COMPANY_CFG = {
    "name": "NVIDIA",
    "ats": "workday",
    "tenant": "nvidia",
    "dc": "wd5",
    "site": "NVIDIAExternalCareerSite",
    "category": "hardware",
    "tier_points": 30,
    "comp_band": "frontier_ai_lab",
}

BASE = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"


@responses.activate
def test_workday_fetch_and_normalize():
    responses.add(
        responses.POST,
        f"{BASE}/jobs",
        json={
            "total": 1,
            "jobPostings": [
                {
                    "title": "Senior Program Manager, Silicon Bring-Up",
                    "externalPath": "/job/Santa-Clara/Senior-PM_R12345",
                    "postedOn": "Posted 3 Days Ago",
                    "jobPostingId": "R12345",
                }
            ],
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/job/Santa-Clara/Senior-PM_R12345",
        json={
            "jobPostingInfo": {
                "title": "Senior Program Manager, Silicon Bring-Up",
                "jobDescription": (
                    "<p>Own silicon bring-up program management across ARM and x86 "
                    "compute platforms, working with ODM vendors. Base pay range: "
                    "$190,000 - $230,000.</p>"
                ),
                "location": "Santa Clara, CA",
                "jobReqId": "R12345",
            }
        },
        status=200,
    )

    scraper = WorkdayScraper()
    jobs = scraper.scrape(COMPANY_CFG)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "R12345"
    assert job.comp_min == 190000
    assert job.comp_max == 230000
    assert "Santa Clara" in job.locations_text
    assert job.url == f"{BASE}/job/Santa-Clara/Senior-PM_R12345"
