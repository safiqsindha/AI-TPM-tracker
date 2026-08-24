# TPM Role Tracker

Scrapes career pages across a fixed list of AI/hardware companies, filters
for roles worth taking, scores them against a 100-point rubric, and writes a
ranked markdown shortlist to `reports/`. Runs on demand or on a Mon/Thu
schedule via GitHub Actions.

## How it works

```
config/companies.yaml  -- which companies, which ATS, tier/comp-band per company
config/filters.yaml    -- hard filter thresholds (location, comp, level, function)
config/scoring.yaml    -- the 100-point rubric's weights/keywords
config/comp_bands.yaml -- static total-comp reference bands (see "Comp estimation" below)

src/jobtracker/
  scrapers/    -- one module per ATS type (greenhouse, ashby, workday, custom/Playwright)
  db.py        -- SQLite persistence + new/closed/comp-changed diffing, scoped per company
  filters.py   -- hard filters
  scoring.py   -- the rubric
  comp.py      -- comp parsing + total-comp estimation
  report.py    -- markdown report
  cli.py        -- `tpm-tracker run` / `tpm-tracker rescore`
```

Run it:

```bash
pip install -r requirements.txt
playwright install chromium   # only needed once, for the custom/JS-rendered scrapers

python -m jobtracker.cli run                          # scrape everything active, then report
python -m jobtracker.cli run --companies Anthropic,OpenAI  # just these
python -m jobtracker.cli rescore                       # re-apply filters/scoring to cached jobs, no network calls
```

Both commands accept `--db PATH` (default `data/jobs.db`) and
`--reports-dir DIR` (default `reports/`). The report lands at
`reports/<YYYY-MM-DD>.md`.

## Adding or dropping a company

Edit `config/companies.yaml` only -- no code changes. Each entry needs:
`name`, `ats` (`greenhouse` | `ashby` | `workday` | `custom`), `active`,
`category` (`ai` | `hardware`), `tier_points` (from the scoring rubric),
`comp_band` (a key in `config/comp_bands.yaml`), plus whatever the ATS needs
(`board_token` for Greenhouse, `board_name` for Ashby, `tenant`/`dc`/`site`
for Workday, or `scrape_config` for a custom Playwright scrape). Set
`active: false` to pause a company without deleting its config.

## IMPORTANT: this needs verification before you trust it

This project was built in a sandboxed environment with **no general
outbound network access** -- direct requests to Greenhouse, Ashby, and every
company's own career page were blocked by the sandbox's egress policy. So
none of the scrapers below have been run against the real, live endpoints.
What's here is built against:

- **Greenhouse and Ashby**: documented, stable public JSON APIs. High
  confidence these work as written; `board_token`/`board_name` values in
  `companies.yaml` are still guesses and need a one-time check.
- **Workday**: a well-known JSON API pattern (`/wday/cxs/{tenant}/{site}/jobs`),
  but the `dc` (data-center subdomain: `wd1`, `wd3`, `wd5`, ...) is
  per-tenant and impossible to guess reliably.
- **Everything under `ats: custom`** (CoreWeave, Lambda, Nebius, Crusoe,
  Meta, Apple, Astera Labs, xAI, SambaNova, Groq, Amazon): the CSS selectors
  in `scrape_config` are placeholders. These pages are JS-rendered and their
  DOM structure needs to be inspected by hand.

**Every company entry in `companies.yaml` marked `verify: true` needs this
before its first real run:**

1. Open the company's real careers page in a browser.
2. For Greenhouse/Ashby: confirm the board slug by checking
   `boards.greenhouse.io/<slug>` or `jobs.ashbyhq.com/<slug>` resolves.
3. For Workday: open dev tools -> Network tab, reload the careers search,
   and find the request to `<tenant>.<dc>.myworkdayjobs.com`. Copy `tenant`,
   `dc`, and the site slug into `companies.yaml`.
4. For custom/Playwright: view source (or inspect element) on the job list
   and update `job_list_selector` / `title_selector` / `location_selector`
   / `description_selector` in `scrape_config` to match the real DOM.
5. Run `python -m jobtracker.cli run --companies <Name>` and read the
   stderr output plus the report -- 0 jobs back usually means a wrong
   selector/slug, not an empty board.

GitHub Actions runners have full internet access (this sandbox does not),
so the scheduled workflow will actually be able to reach these sites --
it just needs the configs above to be correct first.

## Comp estimation

Compensation scoring uses **estimated total comp** (base + bonus + equity),
not base. When a posting discloses a number, it's almost always base salary
(state pay-transparency law compliance) -- `comp.py` scales it by a
per-company-tier `base_to_total_multiplier` in `config/comp_bands.yaml` to
approximate total comp. When nothing is disclosed, the job is flagged
`COMP_UNKNOWN` in the report (never dropped for it) and scored off a static
level-based band in the same file.

Those bands are **not live-scraped from levels.fyi** -- there's no public
API, scraping it isn't something this project does, and the sandbox this
was built in couldn't reach it anyway. They're a manually maintained,
editable approximation of the Seattle/remote-US market. Re-check them
against levels.fyi/Blind by hand periodically and edit
`config/comp_bands.yaml` -- everything downstream picks up the change
automatically, no code touches needed.

## Filters, scoring, and the report

- **Hard filters** (`config/filters.yaml`): location (Seattle metro or
  US-remote), comp floor (by AI vs. hardware category, comp-unknown is
  flagged not dropped), level (drops junior and 12+ years/Director+ unless
  comp clears an "exceptional" bar), function (TPM/PM/product-ops only).
  Amazon gets a special `ai_pivot_required` rule: dropped unless the
  posting reads as genuine AI training/inference work, not a lateral
  hardware-qualification role. Tesla is excluded entirely -- there's no
  Tesla entry in `companies.yaml` and none should be added.
- **Scoring** (`config/scoring.yaml`): comp 40 pts + company tier 30 pts
  (straight from `tier_points` in `companies.yaml`) + role fit 20 pts
  (keyword-weighted) + pivot value 10 pts. Every score comes with a
  one-line rationale, and the code calls out when a score is
  comp/prestige-driven but the underlying role fit is weak -- read that
  line, don't just trust the number.
- **Report** (`reports/<date>.md`): new-since-last-run in full detail, top
  15 overall, a comp-unknown callout list, an xAI callout (flagged, never
  auto-scored on the culture question), and dropped counts grouped by which
  filter killed them -- so you can tell if a filter's too aggressive.

## Data persistence and diffing

`data/jobs.db` (SQLite) is **committed to the repo**, not gitignored --
GitHub Actions runners are ephemeral, so this is how new/closed/comp-changed
diffing survives across scheduled runs. The scheduled workflow commits it
back after each run. Diffing is scoped per company: if a company's scraper
fails or is skipped (`--companies` filter) this run, its existing postings
are left untouched rather than being marked closed.

## Cadence

`.github/workflows/tpm-tracker.yml` runs Monday and Thursday at 15:00 UTC
(~8am PDT / 7am PST). GitHub Actions cron is fixed UTC and doesn't shift for
daylight saving, so the actual Pacific local time drifts by an hour across
the DST boundary -- nudge the cron expression twice a year if that matters
to you, or just treat "morning-ish, Pacific" as good enough. Trigger it
manually anytime from the Actions tab (`workflow_dispatch`).

## Tests

```bash
python -m pytest
```

Greenhouse/Ashby/Workday scrapers are tested against recorded fixture JSON
(via the `responses` library, no real network calls). The custom/Playwright
scraper's HTML-parsing logic (`parse_job_list_html`) is tested the same way,
decoupled from actually launching a browser. Filters, scoring, comp
estimation, DB diffing, and report generation all have direct unit tests.

## Ethical/legal note on scraping

Career pages generally don't require login and this only reads public job
postings, but scraping frequency and terms-of-service vary by company. The
scheduled cadence here (twice a week) is deliberately light. If you add a
company, a quick look at its `robots.txt` and ToS is worth doing before
pointing a scraper at it on a schedule.
