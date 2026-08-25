from jobtracker.models import JobPosting
from jobtracker.report import ScoredEntry, generate_report
from jobtracker.scoring import ScoreResult


def _entry(external_id, score_total, flags=None, flag=None, company="Anthropic"):
    job = JobPosting(
        company=company, external_id=external_id, ats="greenhouse",
        title=f"Senior TPM {external_id}", url=f"https://x/{external_id}",
        category="ai", tier_points=30, comp_band="frontier_ai_lab",
        comp_min=200000, comp_max=240000, flag=flag,
    )
    score = ScoreResult(
        total=score_total, comp_points=20, tier_points=30, role_fit_points=10, pivot_points=10,
        comp_estimate_low=300000, comp_estimate_high=350000, comp_source="estimated_from_band",
        rationale="test rationale",
    )
    return ScoredEntry(job=job, score=score, flags=flags or [])


def test_top_n_respected_and_sorted_desc():
    entries = [_entry(str(i), score_total=i * 10) for i in range(1, 20)]
    report = generate_report(
        run_date="2026-08-24", all_passed=entries, new_job_keys=set(), dropped_counts={}, top_n=15
    )
    assert "## Top 15 overall" in report
    # highest score (190) should appear before the lowest included (50)
    assert report.index("| 190 |") < report.index("| 50 |")


def test_new_since_last_run_gets_full_detail():
    entries = [_entry("1", 80), _entry("2", 70)]
    report = generate_report(
        run_date="2026-08-24", all_passed=entries, new_job_keys={"Anthropic::1"}, dropped_counts={}
    )
    assert "## New since last run" in report
    assert "### Senior TPM 1 -- Anthropic" in report
    assert "### Senior TPM 2 -- Anthropic" not in report


def test_comp_unknown_section_lists_flagged_entries():
    entries = [_entry("1", 80, flags=["COMP_UNKNOWN"]), _entry("2", 70)]
    report = generate_report(
        run_date="2026-08-24", all_passed=entries, new_job_keys=set(), dropped_counts={}
    )
    assert "Senior TPM 1" in report.split("## Comp unknown")[1].split("## Dropped")[0]
    assert "Senior TPM 2" not in report.split("## Comp unknown")[1].split("## Dropped")[0]


def test_dropped_section_shows_counts_by_reason():
    report = generate_report(
        run_date="2026-08-24", all_passed=[], new_job_keys=set(),
        dropped_counts={"LOCATION_MISMATCH": 5, "COMP_TOO_LOW": 2},
    )
    assert "| Not Seattle metro and not US-remote | 5 |" in report
    assert "| Disclosed base below threshold | 2 |" in report


def test_xai_flag_gets_marker_and_section():
    entries = [_entry("1", 60, flag="xai_culture_note", company="xAI")]
    report = generate_report(
        run_date="2026-08-24", all_passed=entries, new_job_keys=set(), dropped_counts={}
    )
    assert "xAI matches" in report
    assert "⚠️ xAI" in report
