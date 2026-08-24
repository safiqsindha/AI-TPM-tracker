from jobtracker.scrapers.greenhouse import GreenhouseScraper
from jobtracker.scrapers.ashby import AshbyScraper
from jobtracker.scrapers.workday import WorkdayScraper
from jobtracker.scrapers.playwright_generic import PlaywrightGenericScraper

SCRAPER_REGISTRY = {
    "greenhouse": GreenhouseScraper,
    "ashby": AshbyScraper,
    "workday": WorkdayScraper,
    "custom": PlaywrightGenericScraper,
}


def get_scraper(ats: str):
    cls = SCRAPER_REGISTRY.get(ats)
    if cls is None:
        raise ValueError(f"No scraper registered for ats={ats!r}")
    return cls()
