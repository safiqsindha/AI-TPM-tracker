"""CLI entrypoint.

    tpm-tracker run [--companies Anthropic,OpenAI] [--db PATH] [--reports-dir DIR]
    tpm-tracker rescore [--db PATH] [--reports-dir DIR]

`run` scrapes every active company in config/companies.yaml (or the subset
named by --companies), diffs against the DB, then filters/scores/reports.
`rescore` skips scraping entirely and just re-applies the current
filters.yaml/scoring.yaml rubric to whatever is already cached in the DB --
useful after tweaking the rubric, with zero network calls.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone

from jobtracker import db as dbmod
from jobtracker.comp import estimate_total_comp_for_job
from jobtracker.config import load_config
from jobtracker.filters import filter_job
from jobtracker.report import ScoredEntry, generate_report
from jobtracker.scoring import score_job
from jobtracker.scrapers import get_scraper

DEFAULT_DB_PATH = "data/jobs.db"
DEFAULT_REPORTS_DIR = "reports"


def _score_all_open_jobs(conn, cfg) -> tuple[list[ScoredEntry], dict[str, int]]:
    all_passed: list[ScoredEntry] = []
    dropped_counts: dict[str, int] = {}

    for job in dbmod.get_jobs(conn, status="open"):
        comp_low, comp_high, comp_source = estimate_total_comp_for_job(job, cfg.comp_bands)
        result = filter_job(job, cfg.filters, comp_high)
        if not result.passed:
            dropped_counts[result.drop_reason] = dropped_counts.get(result.drop_reason, 0) + 1
            continue
        score = score_job(job, cfg.scoring, comp_low, comp_high, comp_source)
        all_passed.append(ScoredEntry(job=job, score=score, flags=result.flags))

    return all_passed, dropped_counts


def _new_job_keys_for_run(conn, run_id: int | None) -> set[str]:
    if run_id is None:
        row = conn.execute("SELECT MAX(run_id) AS run_id FROM job_events").fetchone()
        run_id = row["run_id"] if row else None
    if run_id is None:
        return set()
    events = dbmod.get_events_for_run(conn, run_id)
    return {e["job_key"] for e in events if e["event_type"] in ("new", "reopened")}


def _write_report(reports_dir: str, run_date: str, markdown: str) -> str:
    os.makedirs(reports_dir, exist_ok=True)
    path = os.path.join(reports_dir, f"{run_date}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    return path


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config_dir)
    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    conn = dbmod.init_db(args.db)
    run_id = dbmod.start_run(conn)

    wanted = set(args.companies.split(",")) if args.companies else None
    companies = [
        c for c in cfg.active_companies() if wanted is None or c["name"] in wanted
    ]

    for company in companies:
        print(f"[{company['name']}] scraping via {company['ats']}...", file=sys.stderr)
        try:
            scraper = get_scraper(company["ats"])
            jobs = scraper.scrape(company)
        except Exception as exc:  # noqa: BLE001 -- one bad company must not kill the run
            print(f"[{company['name']}] FAILED: {exc} -- leaving existing jobs untouched", file=sys.stderr)
            continue

        seen_keys = set()
        for job in jobs:
            dbmod.upsert_job(conn, run_id, job)
            seen_keys.add(job.job_key)
        closed = dbmod.close_missing(conn, run_id, company["name"], seen_keys)
        print(f"[{company['name']}] {len(jobs)} open, {len(closed)} closed", file=sys.stderr)

    dbmod.finish_run(conn, run_id)

    all_passed, dropped_counts = _score_all_open_jobs(conn, cfg)
    new_job_keys = _new_job_keys_for_run(conn, run_id)

    run_date = date.today().isoformat()
    markdown = generate_report(
        run_date=run_date,
        all_passed=all_passed,
        new_job_keys=new_job_keys,
        dropped_counts=dropped_counts,
    )
    path = _write_report(args.reports_dir, run_date, markdown)
    print(f"Report written to {path}", file=sys.stderr)
    return 0


def cmd_rescore(args: argparse.Namespace) -> int:
    cfg = load_config(args.config_dir)
    conn = dbmod.init_db(args.db)

    all_passed, dropped_counts = _score_all_open_jobs(conn, cfg)
    new_job_keys = _new_job_keys_for_run(conn, None)

    run_date = date.today().isoformat()
    markdown = generate_report(
        run_date=run_date,
        all_passed=all_passed,
        new_job_keys=new_job_keys,
        dropped_counts=dropped_counts,
    )
    path = _write_report(args.reports_dir, run_date, markdown)
    print(f"Report written to {path} (rescored from cache, no network calls)", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tpm-tracker")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite DB path")
    parser.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR, help="Where to write the markdown report")
    parser.add_argument("--config-dir", default=None, help="Override the config/ directory")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Scrape, diff, filter, score, and report")
    p_run.add_argument("--companies", default=None, help="Comma-separated company names to scrape (default: all active)")
    p_run.set_defaults(func=cmd_run)

    p_rescore = sub.add_parser("rescore", help="Re-apply filters/scoring to cached jobs, no scraping")
    p_rescore.set_defaults(func=cmd_rescore)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
