"""100-point scoring rubric: comp (40) + company tier (30) + role fit (20) + pivot value (10)."""

from __future__ import annotations

from dataclasses import dataclass

from jobtracker.models import JobPosting


@dataclass
class ScoreResult:
    total: int
    comp_points: int
    tier_points: int
    role_fit_points: int
    pivot_points: int
    comp_estimate_low: int
    comp_estimate_high: int
    comp_source: str
    rationale: str


def _score_comp(total_comp_midpoint: float, comp_points_cfg: list[dict]) -> int:
    for band in comp_points_cfg:  # already sorted descending by min in scoring.yaml
        if total_comp_midpoint >= band["min"]:
            return band["points"]
    return comp_points_cfg[-1]["points"]


def _score_role_fit(job: JobPosting, role_fit_cfg: dict) -> tuple[int, float]:
    hay = f"{job.title}\n{job.description}".lower()
    max_points = role_fit_cfg["max_points"]

    pos = role_fit_cfg["positive_keywords"]
    neg = role_fit_cfg["negative_keywords"]

    total_weight = sum(k["weight"] for k in pos)
    hit_weight = sum(k["weight"] for k in pos if k["kw"] in hay)
    neg_weight = sum(k["weight"] for k in neg if k["kw"] in hay)

    hit_ratio = hit_weight / total_weight if total_weight else 0.0
    raw = hit_ratio * max_points - neg_weight
    points = max(0, min(max_points, round(raw)))
    return points, hit_ratio


def _score_pivot(job: JobPosting, hit_ratio: float, pivot_cfg: dict) -> int:
    if job.category == "ai":
        return pivot_cfg["ai_lab_or_platform"]
    # hardware company: does the posting itself read as AI infra work?
    if hit_ratio >= 0.35:
        return pivot_cfg["ai_infra_at_hardware_co"]
    return pivot_cfg["hardware_qualification"]


def _rationale(
    job: JobPosting, comp_pts: int, tier_pts: int, role_pts: int, pivot_pts: int,
    comp_low: int, comp_high: int, comp_source: str,
) -> str:
    parts = []
    comp_label = "disclosed-base-scaled" if comp_source == "estimated_from_disclosed_base" else "estimated"
    parts.append(f"comp ~${comp_low:,}-${comp_high:,} ({comp_label}) -> {comp_pts}/40")
    parts.append(f"company tier {tier_pts}/30")
    parts.append(f"role fit {role_pts}/20")
    parts.append(f"pivot value {pivot_pts}/10")

    total = comp_pts + tier_pts + role_pts + pivot_pts
    if comp_pts >= 33 and (role_pts <= 8 or pivot_pts <= 2):
        parts.append("NOTE: this scores high mostly on comp -- fit/pivot are weak, weigh accordingly")
    if total >= 70 and tier_pts >= 30 and role_pts <= 6:
        parts.append("NOTE: prestige-driven score; role itself may be a weak match for what you actually do")

    return "; ".join(parts)


def score_job(
    job: JobPosting,
    scoring_cfg: dict,
    comp_low: int,
    comp_high: int,
    comp_source: str,
) -> ScoreResult:
    midpoint = (comp_low + comp_high) / 2
    comp_pts = _score_comp(midpoint, scoring_cfg["comp_points"])
    tier_pts = job.tier_points
    role_pts, hit_ratio = _score_role_fit(job, scoring_cfg["role_fit"])
    pivot_pts = _score_pivot(job, hit_ratio, scoring_cfg["pivot_value"])

    total = comp_pts + tier_pts + role_pts + pivot_pts
    rationale = _rationale(job, comp_pts, tier_pts, role_pts, pivot_pts, comp_low, comp_high, comp_source)

    return ScoreResult(
        total=total,
        comp_points=comp_pts,
        tier_points=tier_pts,
        role_fit_points=role_pts,
        pivot_points=pivot_pts,
        comp_estimate_low=comp_low,
        comp_estimate_high=comp_high,
        comp_source=comp_source,
        rationale=rationale,
    )
