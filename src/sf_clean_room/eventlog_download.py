"""EventLogFile REST download + incremental window logic.

Adapted from the proven ai-framework ``salesforce_download_eventlog_files`` tool:
REST query of EventLogFile, then a per-record LogFile fetch. The one change for
sf-clean-room: ``fetch_logfile_text`` returns the body **in memory** (the caller
classifies it before anything is written) — there is no raw-to-disk path here.

Read-only: only HTTP GET against ``/services/data/...`` query and the
``EventLogFile/{id}/LogFile`` blob.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from urllib.parse import quote

import requests

from sf_clean_room.constants import API_VERSION
from sf_clean_room.session import Session

EVENTLOG_LOOKBACK_DAYS = 29  # cold-start window (Salesforce retains ~30 days)


class EventLogError(RuntimeError):
    pass


def _headers(session: Session) -> dict:
    return {"Authorization": f"Bearer {session.session_id}", "Content-Type": "application/json"}


def _rest_get(session: Session, url: str, timeout: int = 120) -> requests.Response:
    return requests.get(url, headers=_headers(session), timeout=timeout)


def supports_interval(session: Session) -> bool:
    """True if EventLogFile.Interval exists in this org (fail-soft False)."""
    url = f"{session.instance_url}/services/data/v{API_VERSION}/sobjects/EventLogFile/describe"
    try:
        r = _rest_get(session, url)
        if r.status_code != 200:
            return False
        return "Interval" in {f.get("name") for f in r.json().get("fields", [])}
    except Exception:
        return False


def _soql_window(start_date: dt.date, end_date: dt.date) -> tuple[str, str]:
    start_dt = dt.datetime.combine(start_date, dt.time.min, tzinfo=dt.timezone.utc)
    end_upper = dt.datetime.combine(end_date + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
    return start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), end_upper.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_query(start_date: dt.date, end_date: dt.date, only: list[str] | None, with_interval: bool) -> str:
    lo, hi = _soql_window(start_date, end_date)
    where = []
    if with_interval:
        where.append("Interval = 'Daily'")
    where.append(f"LogDate >= {lo}")
    where.append(f"LogDate < {hi}")
    if only:
        types = ", ".join("'" + t.replace("'", "") + "'" for t in only)
        where.append(f"EventType IN ({types})")
    return (
        "SELECT Id, EventType, LogDate, LogFileLength, ApiVersion, LogFileFieldNames "
        "FROM EventLogFile WHERE " + " AND ".join(where)
    )


def query_event_log_files(
    session: Session, start_date: dt.date, end_date: dt.date, only: list[str] | None = None
) -> list[dict]:
    """Run the EventLogFile query; return the record dicts. Aborts on query failure."""
    query = build_query(start_date, end_date, only, supports_interval(session))
    url = f"{session.instance_url}/services/data/v{API_VERSION}/query?q={quote(query)}"
    r = _rest_get(session, url)
    if r.status_code != 200:
        raise EventLogError(f"EventLogFile query failed ({r.status_code}): {r.text[:400]}")
    return list(r.json().get("records", []) or [])


def fetch_logfile_text(session: Session, record: dict) -> str:
    """Fetch one record's LogFile body into memory as UTF-8 text. Raises on HTTP error."""
    rid = record["Id"]
    api_ver = record.get("ApiVersion") or API_VERSION
    url = f"{session.instance_url}/services/data/v{api_ver}/sobjects/EventLogFile/{rid}/LogFile"
    r = _rest_get(session, url)
    if r.status_code != 200:
        raise EventLogError(f"LogFile fetch failed for {rid} ({r.status_code})")
    return r.content.decode("utf-8", errors="replace")


# ---------- incremental window / folder logic (pure; from the proven tool) ----------

def compute_end_date(today_utc: dt.date) -> dt.date:
    """Always 'yesterday' — never download today's (incomplete) logs."""
    return today_utc - dt.timedelta(days=1)


def safe_date(logdate: str) -> str:
    try:
        return dt.datetime.strptime((logdate or "")[:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d")
    except Exception:
        return (logdate or "").split("T", 1)[0][:10]


def _existing_end_dates(log_root: Path) -> list[dt.date]:
    out: list[dt.date] = []
    if not log_root.is_dir():
        return out
    for folder in log_root.iterdir():
        if not folder.is_dir() or "_to_" not in folder.name:
            continue
        try:
            _, end_str = folder.name.split("_to_", 1)
            out.append(dt.datetime.strptime(end_str, "%Y-%m-%d").date())
        except Exception:
            continue
    return out


def find_completed_folder(log_root: Path, end_date: dt.date) -> Path | None:
    """Return an existing ``*_to_<end_date>`` subfolder if present (idempotent no-op)."""
    y = end_date.strftime("%Y-%m-%d")
    if not log_root.is_dir():
        return None
    for folder in log_root.iterdir():
        if folder.is_dir() and folder.name.endswith(f"_to_{y}"):
            return folder
    return None


def determine_start_date(log_root: Path, today_utc: dt.date) -> dt.date:
    """max(existing end) + 1 day, or cold-start lookback if none."""
    ends = _existing_end_dates(log_root)
    if not ends:
        return today_utc - dt.timedelta(days=EVENTLOG_LOOKBACK_DAYS)
    return max(ends) + dt.timedelta(days=1)
