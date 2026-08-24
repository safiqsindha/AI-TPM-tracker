"""Markdown report generator."""

from __future__ import annotations

from dataclasses import dataclass

from jobtracker.models import JobPosting
from jobtracker.scoring import ScoreResult

DROP_REASON_LABELS = {
    "AMAZON_NOT_AI_PIVOT": "Amazon posting not a genuine AI pivot (lateral hardware role)",
    "FUNCTION_MISMATCH": "Wrong function (not TPM/PM/product ops)",
    "FUNCTION_UNCLEAR": "Function unclear from title/description",
    "JUNIOR_LEVEL": "Junior/associate level",
    "TOO_MANY_YEARS_REQUIRED": "Requires 12+ years",
    "DIRECTOR_PLUS_TITLE": "Director+ title without exceptional comp",
    "LOCATION_MISMATCH": "Not Seattle metro and not US-remote",
    "COMP_TOO_LOW": "Disclosed base below threshold",
}


@dataclass
class ScoredEntry:
    job: JobPosting
    score: ScoreResult
    flags: list[str]


def _money(v: int | None) -> str:
    return f"${v:,}" if v is not None else "?"


def _comp_cell(entry: ScoredEntry) -> str:
    job, score = entry.job, entry.score
    if job.comp_min is not None:
        disclosed = f"{_money(job.comp_min)}-{_money(job.comp_max)} base"
    else:
        disclosed = "not posted"
    est = f"est. total {_money(score.comp_estimate_low)}-{_money(score.comp_estimate_high)}"
    return f"{disclosed} ({est})"


def _xai_marker(job: JobPosting) -> str:
    return " ⚠️ xAI" if job.flag == "xai_culture_note" else ""


def _full_detail_block(entry: ScoredEntry) -> str:
    job, score = entry.job, entry.score
    lines = [
        f"### {job.title} -- {job.company}{_xai_marker(job)}",
        f"- **Score:** {score.total}/100 (comp {score.comp_points}/40, tier {score.tier_points}/30, "
        f"role fit {score.role_fit_points}/20, pivot {score.pivot_points}/10)",
        f"- **Location(s):** {job.locations_text or 'unspecified'} ({job.remote_policy or 'unknown'})",
        f"- **Comp:** {_comp_cell(entry)}",
        f"- **Team:** {job.team or 'n/a'}",
        f"- **Posted:** {job.posted_date or 'unknown'}",
        f"- **URL:** {job.url}",
        f"- **Why it scored where it did:** {score.rationale}",
    ]
    if entry.flags:
        lines.append(f"- **Flags:** {', '.join(entry.flags)}")
    if job.notes:
        lines.append(f"- **Company note:** {job.notes}")
    return "\n".join(lines)


def _top_table(entries: list[ScoredEntry]) -> str:
    header = "| Score | Company | Title | Location | Comp | Why |\n|---|---|---|---|---|---|\n"
    rows = []
    for entry in entries:
        job, score = entry.job, entry.score
        title = f"{job.title}{_xai_marker(job)}"
        rows.append(
            f"| {score.total} | {job.company} | [{title}]({job.url}) | "
            f"{job.locations_text or 'unspecified'} | {_comp_cell(entry)} | {score.rationale} |"
        )
    return header + "\n".join(rows)


def generate_report(
    *,
    run_date: str,
    all_passed: list[ScoredEntry],
    new_job_keys: set[str],
    dropped_counts: dict[str, int],
    top_n: int = 15,
) -> str:
    all_passed_sorted = sorted(all_passed, key=lambda e: e.score.total, reverse=True)
    new_entries = [e for e in all_passed_sorted if e.job.job_key in new_job_keys]
    top_entries = all_passed_sorted[:top_n]
    comp_unknown_entries = [e for e in all_passed_sorted if "COMP_UNKNOWN" in e.flags]
    xai_entries = [e for e in all_passed_sorted if e.job.flag == "xai_culture_note"]

    parts = [f"# TPM Role Tracker -- {run_date}", ""]
    parts.append(
        f"{len(all_passed_sorted)} matches passed all filters "
        f"({len(new_entries)} new since last run, {sum(dropped_counts.values())} dropped)."
    )
    parts.append("")

    parts.append("## New since last run")
    if new_entries:
        parts.append("")
        for entry in new_entries:
            parts.append(_full_detail_block(entry))
            parts.append("")
    else:
        parts.append("\nNone.\n")

    parts.append(f"## Top {top_n} overall")
    parts.append("")
    if top_entries:
        parts.append(_top_table(top_entries))
    else:
        parts.append("No matches passed all filters this run.")
    parts.append("")

    if xai_entries:
        parts.append("## xAI matches (flagged for the culture/hours call, not scored on it)")
        parts.append("")
        for entry in xai_entries:
            parts.append(f"- [{entry.job.title}]({entry.job.url}) -- score {entry.score.total}/100")
        parts.append("")

    parts.append("## Comp unknown -- needs a manual look")
    parts.append("")
    if comp_unknown_entries:
        for entry in comp_unknown_entries:
            parts.append(
                f"- [{entry.job.title}]({entry.job.url}) -- {entry.job.company} -- "
                f"score {entry.score.total}/100, {_comp_cell(entry)}"
            )
    else:
        parts.append("None -- every match had disclosed comp.")
    parts.append("")

    parts.append("## Dropped")
    parts.append("")
    if dropped_counts:
        parts.append("| Reason | Count |\n|---|---|")
        for reason, count in sorted(dropped_counts.items(), key=lambda kv: kv[1], reverse=True):
            label = DROP_REASON_LABELS.get(reason, reason)
            parts.append(f"| {label} | {count} |")
    else:
        parts.append("Nothing was dropped this run.")
    parts.append("")

    return "\n".join(parts)
