"""get_event_logs orchestrator: query -> per-record fetch (memory) -> classify ->
transform in flight -> publish an incremental run subfolder.

Fail-closed at the run level; per-record tolerant (a single bad LogFile is
skipped and logged, not fatal). Raw LogFile bodies live only in memory.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import uuid
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Callable

from sf_clean_room.audit import AuditLog
from sf_clean_room.eventlog_classify import DROP, transform_value
from sf_clean_room.eventlog_download import (
    compute_end_date,
    determine_start_date,
    fetch_logfile_text,
    find_completed_folder,
    query_event_log_files,
    safe_date,
)
from sf_clean_room.eventlog_plan import EventLogPlan, emit_plan, load_plan, resolve
from sf_clean_room.publish import publish, remove_empty_temp
from sf_clean_room.session import Session

SENTINEL_NAME = "_field-handling-applied.csv"
SUMMARY_NAME = "_extract-summary.json"

QueryFn = Callable[[Session, dt.date, dt.date, "list[str] | None"], list[dict]]
FetchFn = Callable[[Session, dict], str]


@dataclass
class EventLogRequest:
    only: list[str] | None
    plan_path: Path | None
    dry_run: bool


@dataclass
class _Stats:
    files: int = 0
    skipped: list[str] = dc_field(default_factory=list)
    by_type: dict = dc_field(default_factory=dict)
    actions: dict = dc_field(default_factory=dict)   # column -> (action, recipe, source, downgraded)


def _log_root(base_path: Path, alias: str) -> Path:
    return base_path / "event_logs" / alias


def _parse_field_names(rec: dict) -> list[str]:
    raw = rec.get("LogFileFieldNames") or ""
    return [c.strip() for c in raw.split(",") if c.strip()]


def dry_run(
    session: Session, base_path: Path, alias: str, req: EventLogRequest, log: AuditLog,
    query_fn: QueryFn = query_event_log_files,
) -> str:
    today = dt.datetime.now(dt.timezone.utc).date()
    end = compute_end_date(today)
    log_root = _log_root(base_path, alias)
    existing = find_completed_folder(log_root, end)
    if existing is not None:
        return f"already up to date: {existing} exists (end {end}); nothing to download."
    start = determine_start_date(log_root, today)
    log.section("query")
    log.write(f"window {start}..{end}; querying EventLogFile...")
    records = query_fn(session, start, end, req.only)
    by_type: dict[str, int] = {}
    cols_by_type: dict[str, list[str]] = {}
    for r in records:
        et = r.get("EventType", "Unknown")
        by_type[et] = by_type.get(et, 0) + 1
        if et not in cols_by_type:
            cols_by_type[et] = _parse_field_names(r)
    lines = [f"window: {start} .. {end}", f"{len(records)} EventLogFile record(s):"]
    for et in sorted(by_type):
        lines.append(f"  {et}: {by_type[et]}")
    plan_text = emit_plan(cols_by_type) if cols_by_type else "(no columns advertised; nothing to plan)"
    return "\n".join(lines) + "\n\n" + plan_text


def _anonymise_csv(text: str, plan: EventLogPlan | None, stats: _Stats) -> str:
    reader = csv.reader(io.StringIO(text))
    rows = iter(reader)
    try:
        header = next(rows)
    except StopIteration:
        return ""
    resolved = [(col, resolve(col, plan)) for col in header]
    kept = [(i, col, eff) for i, (col, eff) in enumerate(resolved) if eff.action != DROP]
    for col, eff in resolved:
        stats.actions[col] = (eff.action, eff.recipe, eff.source, eff.downgraded)
    out = io.StringIO()
    w = csv.writer(out, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow([col for _, col, _ in kept])
    for row in rows:
        w.writerow([
            transform_value(eff.action, eff.recipe, row[i] if i < len(row) else "")
            for i, col, eff in kept
        ])
    return out.getvalue()


def execute(
    session: Session, base_path: Path, alias: str, req: EventLogRequest, temp_root: Path, log: AuditLog,
    query_fn: QueryFn = query_event_log_files, fetch_fn: FetchFn = fetch_logfile_text,
) -> Path:
    today = dt.datetime.now(dt.timezone.utc).date()
    end = compute_end_date(today)
    end_str = end.strftime("%Y-%m-%d")
    log_root = _log_root(base_path, alias)

    existing = find_completed_folder(log_root, end)
    if existing is not None:
        log.write(f"idempotent no-op: {existing} already covers through {end_str}")
        return existing

    start = determine_start_date(log_root, today)
    plan = load_plan(req.plan_path) if (req.plan_path and req.plan_path.exists()) else None
    if plan is not None:
        log.write(f"loaded classification plan: {req.plan_path}")

    log.section("query")
    log.write(f"window {start}..{end_str}; querying EventLogFile...")
    records = query_fn(session, start, end, req.only)
    log.write(f"{len(records)} record(s) to download")

    run_temp = (temp_root / f"{alias}-eventlogs-{end_str}-{uuid.uuid4().hex[:8]}").resolve()
    run_temp.mkdir(parents=True, exist_ok=False)
    log.write(f"per-run temp dir: {run_temp}")

    stats = _Stats()
    log.section("download+classify")
    for rec in records:
        rid = rec.get("Id", "?")
        etype = rec.get("EventType", "Unknown")
        ldate = safe_date(rec.get("LogDate", ""))
        try:
            text = fetch_fn(session, rec)
        except Exception as e:  # noqa: BLE001 — per-record tolerance
            stats.skipped.append(f"{etype}/{rid}: fetch failed: {e}")
            log.write(f"  skip {etype}/{rid}: fetch failed")
            continue
        try:
            out_csv = _anonymise_csv(text, plan, stats)
        except Exception as e:  # noqa: BLE001
            stats.skipped.append(f"{etype}/{rid}: parse failed: {e}")
            log.write(f"  skip {etype}/{rid}: parse failed")
            continue
        (run_temp / f"{ldate}_{etype}_{rid}.csv").write_text(out_csv, encoding="utf-8")
        stats.files += 1
        stats.by_type[etype] = stats.by_type.get(etype, 0) + 1

    _write_summary(run_temp / SUMMARY_NAME, start, end_str, stats)
    _write_sentinel(run_temp / SENTINEL_NAME, stats)
    log.write(f"downloaded {stats.files} file(s); {len(stats.skipped)} skipped")

    log.section("publish")
    dest = log_root / f"{start}_to_{end_str}"
    publish(run_temp, dest, sentinel_name=SENTINEL_NAME)
    log.write(f"published run to {dest} (sentinel {SENTINEL_NAME} last)")
    remove_empty_temp(run_temp)
    return dest


def _write_sentinel(path: Path, stats: _Stats) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["column", "action", "recipe", "source", "downgraded"])
        for col in sorted(stats.actions):
            action, recipe, source, downgraded = stats.actions[col]
            w.writerow([col, action, recipe, source, str(downgraded)])


def _write_summary(path: Path, start: dt.date, end_str: str, stats: _Stats) -> None:
    action_counts: dict[str, int] = {}
    for action, *_ in stats.actions.values():
        action_counts[action] = action_counts.get(action, 0) + 1
    summary = {
        "window": {"start": str(start), "end": end_str},
        "files": stats.files,
        "records_by_type": stats.by_type,
        "skipped": stats.skipped,
        "column_action_counts": action_counts,
        "columns": {c: a[0] for c, a in sorted(stats.actions.items())},
    }
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
