from jobtracker.config import load_config
from jobtracker.models import JobPosting
from jobtracker.scoring import score_job

SCORING_CFG = load_config().scoring


def _job(category="ai", tier_points=30, description=""):
    return JobPosting(
        company="Anthropic", external_id="1", ats="greenhouse",
        title="Senior Technical Program Manager", url="https://x",
        category=category, tier_points=tier_points, comp_band="frontier_ai_lab",
        description=description,
    )


def test_comp_points_bands():
    job = _job()
    assert score_job(job, SCORING_CFG, 650000, 700000, "estimated_from_band").comp_points == 40
    assert score_job(job, SCORING_CFG, 500000, 500000, "estimated_from_band").comp_points == 33
    assert score_job(job, SCORING_CFG, 400000, 400000, "estimated_from_band").comp_points == 26
    assert score_job(job, SCORING_CFG, 300000, 300000, "estimated_from_band").comp_points == 19
    assert score_job(job, SCORING_CFG, 250000, 250000, "estimated_from_band").comp_points == 12
    assert score_job(job, SCORING_CFG, 100000, 100000, "estimated_from_band").comp_points == 5


def test_tier_points_pass_through_from_job():
    job = _job(tier_points=14)
    result = score_job(job, SCORING_CFG, 300000, 300000, "estimated_from_band")
    assert result.tier_points == 14


def test_role_fit_rewards_relevant_keywords():
    strong = _job(description="Own GPU fleet operations, data center capacity buildout, and vendor/ODM management for our accelerator programs.")
    weak = _job(description="Coordinate the go-to-market launch for our new product line.")

    strong_score = score_job(strong, SCORING_CFG, 300000, 300000, "estimated_from_band")
    weak_score = score_job(weak, SCORING_CFG, 300000, 300000, "estimated_from_band")

    assert strong_score.role_fit_points > weak_score.role_fit_points
    assert weak_score.role_fit_points == 0


def test_pivot_value_ai_lab_gets_full_points():
    job = _job(category="ai")
    result = score_job(job, SCORING_CFG, 300000, 300000, "estimated_from_band")
    assert result.pivot_points == SCORING_CFG["pivot_value"]["ai_lab_or_platform"]


def test_pivot_value_hardware_qualification_gets_minimal_points():
    job = _job(category="hardware", description="Own board bring-up and hardware qualification schedules.")
    result = score_job(job, SCORING_CFG, 300000, 300000, "estimated_from_band")
    assert result.pivot_points == SCORING_CFG["pivot_value"]["hardware_qualification"]


def test_total_is_sum_of_components():
    job = _job()
    result = score_job(job, SCORING_CFG, 500000, 500000, "estimated_from_band")
    assert result.total == (
        result.comp_points + result.tier_points + result.role_fit_points + result.pivot_points
    )


def test_rationale_flags_comp_driven_weak_fit():
    job = _job(category="hardware", tier_points=0, description="")
    result = score_job(job, SCORING_CFG, 650000, 700000, "estimated_from_band")
    assert "NOTE" in result.rationale
