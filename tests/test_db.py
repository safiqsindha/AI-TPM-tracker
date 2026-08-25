import os

from jobtracker import db as dbmod
from jobtracker.models import JobPosting


def _job(external_id="1", comp_min=200000, comp_max=240000, company="Anthropic"):
    return JobPosting(
        company=company, external_id=external_id, ats="greenhouse",
        title="Senior TPM", url="https://x", category="ai", tier_points=30,
        comp_band="frontier_ai_lab", comp_min=comp_min, comp_max=comp_max,
    )


def test_new_job_creates_new_event(tmp_path):
    conn = dbmod.init_db(str(tmp_path / "jobs.db"))
    run_id = dbmod.start_run(conn)

    event = dbmod.upsert_job(conn, run_id, _job())
    assert event == "new"

    open_jobs = dbmod.get_jobs(conn, status="open")
    assert len(open_jobs) == 1
    assert open_jobs[0].external_id == "1"


def test_unchanged_job_produces_no_event(tmp_path):
    conn = dbmod.init_db(str(tmp_path / "jobs.db"))
    run_id_1 = dbmod.start_run(conn)
    dbmod.upsert_job(conn, run_id_1, _job())

    run_id_2 = dbmod.start_run(conn)
    event = dbmod.upsert_job(conn, run_id_2, _job())
    assert event is None


def test_comp_change_produces_comp_changed_event(tmp_path):
    conn = dbmod.init_db(str(tmp_path / "jobs.db"))
    run_id_1 = dbmod.start_run(conn)
    dbmod.upsert_job(conn, run_id_1, _job(comp_min=200000, comp_max=240000))

    run_id_2 = dbmod.start_run(conn)
    event = dbmod.upsert_job(conn, run_id_2, _job(comp_min=210000, comp_max=250000))
    assert event == "comp_changed"


def test_close_missing_only_affects_named_company(tmp_path):
    conn = dbmod.init_db(str(tmp_path / "jobs.db"))
    run_id = dbmod.start_run(conn)
    dbmod.upsert_job(conn, run_id, _job(external_id="1", company="Anthropic"))
    dbmod.upsert_job(conn, run_id, _job(external_id="2", company="OpenAI"))

    # Anthropic's job "1" wasn't seen this run -> should close; OpenAI untouched.
    closed = dbmod.close_missing(conn, run_id, "Anthropic", seen_keys=set())
    assert closed == ["Anthropic::1"]

    open_jobs = {j.job_key for j in dbmod.get_jobs(conn, status="open")}
    assert "OpenAI::2" in open_jobs
    assert "Anthropic::1" not in open_jobs


def test_reopened_job_after_being_closed(tmp_path):
    conn = dbmod.init_db(str(tmp_path / "jobs.db"))
    run_id_1 = dbmod.start_run(conn)
    dbmod.upsert_job(conn, run_id_1, _job())
    dbmod.close_missing(conn, run_id_1, "Anthropic", seen_keys=set())

    run_id_2 = dbmod.start_run(conn)
    event = dbmod.upsert_job(conn, run_id_2, _job())
    assert event == "reopened"

    open_jobs = dbmod.get_jobs(conn, status="open")
    assert len(open_jobs) == 1


def test_scraper_failure_leaves_existing_jobs_untouched(tmp_path):
    """Simulates cli.py's behavior: a company that fails to scrape this run
    must never have close_missing called for it, so its cached jobs survive."""
    conn = dbmod.init_db(str(tmp_path / "jobs.db"))
    run_id_1 = dbmod.start_run(conn)
    dbmod.upsert_job(conn, run_id_1, _job(company="Anthropic"))

    run_id_2 = dbmod.start_run(conn)
    # Scrape "fails" -- close_missing is simply never called for Anthropic this run.

    open_jobs = dbmod.get_jobs(conn, status="open", company="Anthropic")
    assert len(open_jobs) == 1
