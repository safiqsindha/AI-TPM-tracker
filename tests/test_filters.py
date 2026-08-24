import pytest

from jobtracker.config import load_config
from jobtracker.filters import filter_job
from jobtracker.models import JobPosting

CFG = load_config().filters


def _job(**overrides):
    base = dict(
        company="Anthropic", external_id="1", ats="greenhouse",
        title="Senior Technical Program Manager, Compute Infrastructure",
        url="https://x", category="ai", tier_points=30, comp_band="frontier_ai_lab",
        locations=["Seattle, WA"], remote_policy="onsite",
        comp_min=200000, comp_max=240000,
        description="Own compute infrastructure and vendor management for our accelerator programs.",
    )
    base.update(overrides)
    return JobPosting(**base)


def test_passes_all_filters():
    result = filter_job(_job(), CFG, estimated_total_high=400000)
    assert result.passed
    assert result.flags == []


def test_comp_unknown_flagged_not_dropped():
    job = _job(comp_min=None, comp_max=None)
    result = filter_job(job, CFG, estimated_total_high=400000)
    assert result.passed
    assert "COMP_UNKNOWN" in result.flags


def test_comp_too_low_dropped():
    job = _job(comp_min=150000, comp_max=160000)
    result = filter_job(job, CFG, estimated_total_high=400000)
    assert not result.passed
    assert result.drop_reason == "COMP_TOO_LOW"


def test_hardware_comp_threshold_is_higher():
    job = _job(category="hardware", comp_min=190000, comp_max=195000)
    result = filter_job(job, CFG, estimated_total_high=400000)
    assert not result.passed
    assert result.drop_reason == "COMP_TOO_LOW"


def test_location_mismatch_dropped():
    job = _job(locations=["London, UK"], remote_policy="onsite")
    result = filter_job(job, CFG, estimated_total_high=400000)
    assert not result.passed
    assert result.drop_reason == "LOCATION_MISMATCH"


def test_us_remote_passes_location():
    job = _job(locations=["Remote - US"], remote_policy="remote")
    result = filter_job(job, CFG, estimated_total_high=400000)
    assert result.passed


def test_non_us_remote_dropped():
    job = _job(locations=["Remote - UK"], remote_policy="remote")
    result = filter_job(job, CFG, estimated_total_high=400000)
    assert not result.passed
    assert result.drop_reason == "LOCATION_MISMATCH"


def test_junior_title_dropped():
    job = _job(title="Associate Program Manager")
    result = filter_job(job, CFG, estimated_total_high=400000)
    assert not result.passed
    assert result.drop_reason == "JUNIOR_LEVEL"


def test_too_many_years_required_dropped():
    job = _job(description="Requires 15+ years of experience in hardware program management.")
    result = filter_job(job, CFG, estimated_total_high=400000)
    assert not result.passed
    assert result.drop_reason == "TOO_MANY_YEARS_REQUIRED"


def test_director_title_dropped_without_exceptional_comp():
    job = _job(title="Director, Technical Program Management")
    result = filter_job(job, CFG, estimated_total_high=400000)
    assert not result.passed
    assert result.drop_reason == "DIRECTOR_PLUS_TITLE"


def test_director_title_passes_with_exceptional_comp():
    job = _job(title="Director, Technical Program Management")
    result = filter_job(job, CFG, estimated_total_high=600000)
    assert result.passed


def test_wrong_function_dropped():
    job = _job(title="Senior Software Engineer, Compute Infrastructure")
    result = filter_job(job, CFG, estimated_total_high=400000)
    assert not result.passed
    assert result.drop_reason == "FUNCTION_MISMATCH"


def test_amazon_ai_pivot_required_drops_lateral_hardware_role():
    job = _job(
        company="Amazon", category="hardware", tier_points=0, comp_band="default",
        title="Senior Technical Program Manager, Annapurna Labs",
        special_rule="ai_pivot_required",
        description="Own silicon validation and hardware qualification for our AI chips.",
    )
    result = filter_job(job, CFG, estimated_total_high=250000)
    assert not result.passed
    assert result.drop_reason == "AMAZON_NOT_AI_PIVOT"


def test_amazon_ai_pivot_required_passes_genuine_pivot():
    job = _job(
        company="Amazon", category="hardware", tier_points=0, comp_band="default",
        title="Senior Technical Program Manager, Bedrock Foundation Models",
        special_rule="ai_pivot_required",
        description="Drive program management for our foundation model training and inference platform.",
    )
    result = filter_job(job, CFG, estimated_total_high=250000)
    assert result.passed
