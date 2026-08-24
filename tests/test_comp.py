from jobtracker.comp import estimate_total_comp_for_job, infer_level_from_title, parse_comp_from_text
from jobtracker.models import JobPosting


def test_parse_comp_from_text_dollar_range():
    lo, hi, raw = parse_comp_from_text("The base pay range for this role is $180,000 - $220,000 per year.")
    assert (lo, hi) == (180000, 220000)
    assert raw


def test_parse_comp_from_text_k_shorthand():
    lo, hi, raw = parse_comp_from_text("Compensation: $180K-$220K depending on level.")
    assert (lo, hi) == (180000, 220000)


def test_parse_comp_from_text_single_value():
    lo, hi, raw = parse_comp_from_text("Target base salary of $200,000.")
    assert (lo, hi) == (200000, 200000)


def test_parse_comp_from_text_none_found():
    lo, hi, raw = parse_comp_from_text("We are a fast-growing startup building the future.")
    assert (lo, hi, raw) == (None, None, None)


def test_infer_level_from_title():
    assert infer_level_from_title("Principal Technical Program Manager") == "principal"
    assert infer_level_from_title("Staff TPM, Infra") == "staff"
    assert infer_level_from_title("Program Manager") == "senior"
    assert infer_level_from_title("Manager, Technical Programs") == "manager"


def _job(comp_min=None, comp_max=None, comp_band="neocloud", title="Senior TPM"):
    return JobPosting(
        company="Test Co", external_id="1", ats="custom", title=title, url="https://x",
        category="hardware", tier_points=18, comp_band=comp_band,
        comp_min=comp_min, comp_max=comp_max,
    )


def test_estimate_total_comp_uses_band_when_not_disclosed():
    job = _job()
    lo, hi, source = estimate_total_comp_for_job(job, {
        "neocloud": {"base_to_total_multiplier": 1.5, "senior": {"low": 220000, "high": 320000}},
        "default": {"base_to_total_multiplier": 1.3, "senior": {"low": 180000, "high": 250000}},
    })
    assert (lo, hi, source) == (220000, 320000, "estimated_from_band")


def test_estimate_total_comp_scales_disclosed_base():
    job = _job(comp_min=200000, comp_max=200000)
    lo, hi, source = estimate_total_comp_for_job(job, {
        "neocloud": {"base_to_total_multiplier": 1.5, "senior": {"low": 220000, "high": 320000}},
        "default": {"base_to_total_multiplier": 1.3, "senior": {"low": 180000, "high": 250000}},
    })
    assert (lo, hi, source) == (300000, 300000, "estimated_from_disclosed_base")
