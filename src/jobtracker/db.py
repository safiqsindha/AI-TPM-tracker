"""SQLite persistence: current job state, run history, and new/closed/comp-changed diffing.

Diffing is scoped per company: after scraping company X we only close jobs
that belong to company X and weren't seen in this run. A company that wasn't
scraped this run (e.g. --companies filter, or a scraper failure) never has
its existing jobs closed out from under it.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional

from jobtracker.models import JobPosting

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    job_key TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    ats TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    team TEXT,
    locations TEXT,
    remote_policy TEXT,
    posted_date TEXT,
    comp_min INTEGER,
    comp_max INTEGER,
    comp_currency TEXT,
    comp_raw TEXT,
    url TEXT,
    description TEXT,
    description_hash TEXT,
    category TEXT,
    tier_points INTEGER,
    comp_band TEXT,
    flag TEXT,
    special_rule TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    first_seen_run INTEGER,
    last_seen_run INTEGER,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    job_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT,
    created_at TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (_now(),))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute("UPDATE runs SET finished_at = ? WHERE id = ?", (_now(), run_id))
    conn.commit()


def _row_to_job(row: sqlite3.Row) -> JobPosting:
    return JobPosting(
        company=row["company"],
        external_id=row["external_id"],
        ats=row["ats"],
        title=row["title"],
        url=row["url"],
        category=row["category"],
        tier_points=row["tier_points"],
        comp_band=row["comp_band"],
        team=row["team"],
        locations=json.loads(row["locations"]) if row["locations"] else [],
        remote_policy=row["remote_policy"],
        posted_date=row["posted_date"],
        comp_min=row["comp_min"],
        comp_max=row["comp_max"],
        comp_currency=row["comp_currency"],
        comp_raw=row["comp_raw"],
        description=row["description"] or "",
        flag=row["flag"],
        special_rule=row["special_rule"],
        notes=row["notes"],
    )


def upsert_job(conn: sqlite3.Connection, run_id: int, job: JobPosting) -> Optional[str]:
    """Insert or update a job. Returns an event_type ('new', 'reopened',
    'comp_changed') if something notable happened, else None."""
    existing = conn.execute(
        "SELECT * FROM jobs WHERE job_key = ?", (job.job_key,)
    ).fetchone()

    now = _now()
    locations_json = json.dumps(job.locations)
    desc_hash = str(hash(job.description))

    event_type = None
    detail = None

    if existing is None:
        event_type = "new"
    else:
        if existing["status"] == "closed":
            event_type = "reopened"
        old_min, old_max = existing["comp_min"], existing["comp_max"]
        if (old_min, old_max) != (job.comp_min, job.comp_max) and (
            job.comp_min is not None or job.comp_max is not None
        ):
            event_type = event_type or "comp_changed"
            detail = f"{old_min}-{old_max} -> {job.comp_min}-{job.comp_max}"

    conn.execute(
        """
        INSERT INTO jobs (
            job_key, company, ats, external_id, title, team, locations,
            remote_policy, posted_date, comp_min, comp_max, comp_currency,
            comp_raw, url, description, description_hash, category,
            tier_points, comp_band, flag, special_rule, notes, status,
            first_seen_run, last_seen_run, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', ?,?,?,?)
        ON CONFLICT(job_key) DO UPDATE SET
            title=excluded.title, team=excluded.team, locations=excluded.locations,
            remote_policy=excluded.remote_policy, posted_date=excluded.posted_date,
            comp_min=excluded.comp_min, comp_max=excluded.comp_max,
            comp_currency=excluded.comp_currency, comp_raw=excluded.comp_raw,
            url=excluded.url, description=excluded.description,
            description_hash=excluded.description_hash, category=excluded.category,
            tier_points=excluded.tier_points, comp_band=excluded.comp_band,
            flag=excluded.flag, special_rule=excluded.special_rule, notes=excluded.notes,
            status='open', last_seen_run=excluded.last_seen_run, updated_at=excluded.updated_at
        """,
        (
            job.job_key, job.company, job.ats, job.external_id, job.title, job.team,
            locations_json, job.remote_policy, job.posted_date, job.comp_min,
            job.comp_max, job.comp_currency, job.comp_raw, job.url, job.description,
            desc_hash, job.category, job.tier_points, job.comp_band, job.flag,
            job.special_rule, job.notes, run_id, run_id, now, now,
        ),
    )

    if event_type:
        conn.execute(
            "INSERT INTO job_events (run_id, job_key, event_type, detail, created_at) VALUES (?,?,?,?,?)",
            (run_id, job.job_key, event_type, detail, now),
        )

    conn.commit()
    return event_type


def close_missing(
    conn: sqlite3.Connection, run_id: int, company: str, seen_keys: Iterable[str]
) -> list[str]:
    """Mark open jobs for `company` not in seen_keys as closed. Returns closed job_keys."""
    seen = set(seen_keys)
    rows = conn.execute(
        "SELECT job_key FROM jobs WHERE company = ? AND status = 'open'", (company,)
    ).fetchall()
    closed = []
    now = _now()
    for row in rows:
        key = row["job_key"]
        if key not in seen:
            conn.execute(
                "UPDATE jobs SET status = 'closed', updated_at = ? WHERE job_key = ?",
                (now, key),
            )
            conn.execute(
                "INSERT INTO job_events (run_id, job_key, event_type, detail, created_at) VALUES (?,?,?,?,?)",
                (run_id, key, "closed", None, now),
            )
            closed.append(key)
    conn.commit()
    return closed


def get_jobs(
    conn: sqlite3.Connection, status: Optional[str] = "open", company: Optional[str] = None
) -> list[JobPosting]:
    query = "SELECT * FROM jobs WHERE 1=1"
    params: list = []
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    if company is not None:
        query += " AND company = ?"
        params.append(company)
    rows = conn.execute(query, params).fetchall()
    return [_row_to_job(r) for r in rows]


def get_events_for_run(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM job_events WHERE run_id = ? ORDER BY id", (run_id,)
    ).fetchall()
