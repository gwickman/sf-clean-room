"""get_technical_objects orchestrator: describe -> classify -> page -> transform -> publish.

Fail-closed at the run level; per-object tolerant (a describe or query failure
for one object is skipped and logged, not fatal).  Every row is classified in
flight before writing — raw values never reach disk.
"""
from __future__ import annotations

import csv
import json
import uuid
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from sf_clean_room.audit import AuditLog
from sf_clean_room.publish import publish, remove_empty_temp
from sf_clean_room.session import Session
from sf_clean_room.technical_catalog import CATALOGUE, CATALOGUE_BY_NAME, CATALOGUE_NAMES, CatalogueEntry
from sf_clean_room.technical_classify import DROP, FieldMeta, transform_value
from sf_clean_room.technical_download import (
    GetFn,
    TechnicalDownloadError,
    _default_get,
    describe_fields,
    fetch_limits,
    fetch_recordcount,
    page_entitydefinition,
    page_soql,
    query_tooling,
)
from sf_clean_room.technical_plan import (
    Effective,
    TechnicalPlan,
    emit_plan,
    load_plan,
    resolve,
)

SENTINEL_NAME = "_field-handling-applied.csv"
SUMMARY_NAME = "_extract-summary.json"


@dataclass
class TechnicalRequest:
    only: list[str] | None      # None = all catalogue objects
    limit: int | None
    plan_path: Path | None
    dry_run: bool


# Per-object accumulator (action tuple: type, action, recipe, source, downgraded).
@dataclass
class _ObjStats:
    rows: int = 0
    columns: int = 0
    actions: dict = dc_field(default_factory=dict)  # field_name -> (type, action, recipe, source, downgraded)


def _resolve_scope(req: TechnicalRequest, plan: TechnicalPlan | None) -> list[CatalogueEntry]:
    names: list[str] = []
    if req.only:
        names = req.only
    elif plan and plan.objects:
        names = plan.objects
    else:
        return list(CATALOGUE)
    unknown = [n for n in names if n not in CATALOGUE_BY_NAME]
    if unknown:
        valid = ", ".join(CATALOGUE_NAMES)
        raise ValueError(f"unknown object(s): {unknown}. Valid names: {valid}")
    return [CATALOGUE_BY_NAME[n] for n in names]


def _load_plan_safe(plan_path: Path | None, log: AuditLog) -> TechnicalPlan | None:
    if plan_path and plan_path.exists():
        plan = load_plan(plan_path)
        log.write(f"loaded classification plan: {plan_path}")
        return plan
    return None


# ---------------------------------------------------------------------------
# Fixed-schema REST endpoints — no describe needed
# ---------------------------------------------------------------------------

def _fixed_schema_fields(transport: str) -> list[FieldMeta]:
    if transport == "rest_limits":
        return [
            FieldMeta("LimitName",   "string"),
            FieldMeta("Max",         "int"),
            FieldMeta("Remaining",   "int"),
        ]
    return [  # rest_recordcount
        FieldMeta("ObjectName",  "string"),
        FieldMeta("RecordCount", "int"),
    ]


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------

def dry_run(
    session: Session,
    publish_path: Path,
    req: TechnicalRequest,
    log: AuditLog,
    get_fn: GetFn = _default_get,
) -> str:
    """Describe + classify all in-scope objects; return an annotated plan string.

    No record values are fetched; publish path is untouched.
    """
    plan = _load_plan_safe(req.plan_path, log)
    entries = _resolve_scope(req, plan)
    log.section("dry-run describe")
    fields_by_object: dict[str, list[FieldMeta]] = {}
    skipped: list[str] = []

    for entry in entries:
        try:
            if entry.transport in ("rest_limits", "rest_recordcount"):
                fields = _fixed_schema_fields(entry.transport)
            else:
                transport_mode = "tooling" if entry.transport == "tooling" else "soql"
                fields = describe_fields(session, entry.api_name, transport_mode, get_fn)
            fields_by_object[entry.api_name] = fields
            log.write(f"  {entry.api_name}: {len(fields)} column(s)")
        except TechnicalDownloadError as e:
            skipped.append(f"{entry.api_name}: {e}")
            log.write(f"  {entry.api_name}: describe failed — {e}")

    plan_text = emit_plan(fields_by_object) if fields_by_object else "(no columns available)"

    if req.plan_path is not None:
        req.plan_path.write_text(plan_text, encoding="utf-8")
        log.write(f"plan written: {req.plan_path}")

    lines = [f"dry-run: {len(entries)} object(s) in scope"]
    if skipped:
        lines.append(f"{len(skipped)} object(s) could not be described:")
        for s in skipped:
            lines.append(f"  {s}")
    return "\n".join(lines) + "\n\n" + plan_text


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

def execute(
    session: Session,
    publish_path: Path,
    req: TechnicalRequest,
    temp_root: Path,
    log: AuditLog,
    get_fn: GetFn = _default_get,
) -> Path:
    """Extract, classify in flight, and publish the technical objects snapshot."""
    plan = _load_plan_safe(req.plan_path, log)
    entries = _resolve_scope(req, plan)

    run_temp = (temp_root / f"techobj-{uuid.uuid4().hex[:8]}").resolve()
    run_temp.mkdir(parents=True, exist_ok=False)
    log.write(f"per-run temp dir: {run_temp}")

    all_actions: dict[str, list[tuple]] = {}  # obj -> list of (field, type, action, recipe, source, downgraded)
    skipped: list[dict] = []
    per_object: list[dict] = []
    success_count = 0

    log.section("extract")
    for entry in entries:
        try:
            stats = _extract_object(session, entry, plan, req.limit, run_temp, log, get_fn)
            all_actions[entry.api_name] = list(stats.actions.items())
            per_object.append({
                "object": entry.api_name,
                "rows": stats.rows,
                "columns": stats.columns,
                "action_counts": _count_actions(stats.actions),
            })
            success_count += 1
        except TechnicalDownloadError as e:
            msg = str(e)[:400]
            log.write(f"  skip {entry.api_name}: {msg}")
            skipped.append({"object": entry.api_name, "reason": msg})

    if success_count == 0 and entries:
        raise RuntimeError(
            "every object failed; aborting — publish path is untouched"
        )

    _write_summary(run_temp / SUMMARY_NAME, per_object, skipped, req.limit)
    _write_sentinel(run_temp / SENTINEL_NAME, all_actions)
    log.write(f"extracted {success_count} object(s); {len(skipped)} skipped")

    log.section("publish")
    publish(run_temp, publish_path, sentinel_name=SENTINEL_NAME)
    log.write(f"published to {publish_path} (sentinel {SENTINEL_NAME} last)")
    remove_empty_temp(run_temp)
    return publish_path


# ---------------------------------------------------------------------------
# Per-object extraction
# ---------------------------------------------------------------------------

def _extract_object(
    session: Session,
    entry: CatalogueEntry,
    plan: TechnicalPlan | None,
    limit: int | None,
    run_temp: Path,
    log: AuditLog,
    get_fn: GetFn,
) -> _ObjStats:
    stats = _ObjStats()

    # --- fixed-schema REST endpoints (limits / recordCount) ---
    if entry.transport in ("rest_limits", "rest_recordcount"):
        fields = _fixed_schema_fields(entry.transport)
        effectives = [resolve(entry.api_name, f, plan) for f in fields]
        for f, eff in zip(fields, effectives):
            stats.actions[f.name] = (f.type, eff.action, eff.recipe, eff.source, eff.downgraded)
        kept = [(f, eff) for f, eff in zip(fields, effectives) if eff.action != DROP]
        if entry.transport == "rest_limits":
            rows = fetch_limits(session, get_fn)
        else:
            rows = fetch_recordcount(session, get_fn)
        _write_rows(run_temp / f"{entry.api_name}.csv", kept, rows)
        stats.rows = len(rows)
        stats.columns = len(kept)
        log.write(f"  {entry.api_name}: {stats.rows} row(s) (fixed schema)")
        return stats

    # --- describe-driven path (soql / tooling / entitydef) ---
    transport_mode = "tooling" if entry.transport == "tooling" else "soql"
    fields = describe_fields(session, entry.api_name, transport_mode, get_fn)
    effectives = [resolve(entry.api_name, f, plan) for f in fields]

    for f, eff in zip(fields, effectives):
        stats.actions[f.name] = (f.type, eff.action, eff.recipe, eff.source, eff.downgraded)
        if eff.downgraded:
            log.write(
                f"  {entry.api_name}.{f.name}: exposing override without justification "
                f"— downgraded to {eff.action}"
            )

    kept = [(f, eff) for f, eff in zip(fields, effectives) if eff.action != DROP]

    if not kept:
        # Write header-only CSV; still a success.
        (run_temp / f"{entry.api_name}.csv").write_text("", encoding="utf-8")
        stats.rows = 0
        stats.columns = 0
        log.write(f"  {entry.api_name}: no non-DROP columns; empty CSV")
        return stats

    # Build SELECT from non-DROP columns only.
    select_cols = ", ".join(f.name for f, _ in kept)
    soql = f"SELECT {select_cols} FROM {entry.api_name}"
    if limit is not None:
        soql += f" LIMIT {limit}"

    out_path = run_temp / f"{entry.api_name}.csv"
    row_count = 0

    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow([f.name for f, _ in kept])

        if entry.transport == "tooling":
            for rec in query_tooling(session, soql, limit, get_fn):
                w.writerow([
                    transform_value(eff.action, eff.recipe, rec.get(f.name))
                    for f, eff in kept
                ])
                row_count += 1
        elif entry.transport == "entitydef":
            for rec in page_entitydefinition(session, [f for f, _ in kept], limit, get_fn):
                w.writerow([
                    transform_value(eff.action, eff.recipe, rec.get(f.name))
                    for f, eff in kept
                ])
                row_count += 1
        else:  # soql
            for rec in page_soql(session, soql, limit, get_fn):
                w.writerow([
                    transform_value(eff.action, eff.recipe, rec.get(f.name))
                    for f, eff in kept
                ])
                row_count += 1

    stats.rows = row_count
    stats.columns = len(kept)
    log.write(f"  {entry.api_name}: {row_count} row(s), {len(kept)} column(s)")
    return stats


def _write_rows(path: Path, kept: list[tuple], rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow([f.name for f, _ in kept])
        for row in rows:
            w.writerow([
                transform_value(eff.action, eff.recipe, row.get(f.name))
                for f, eff in kept
            ])


def _count_actions(actions: dict) -> dict:
    counts: dict[str, int] = {}
    for _ftype, action, *_ in actions.values():
        counts[action] = counts.get(action, 0) + 1
    return counts


def _write_sentinel(
    path: Path,
    all_actions: dict[str, list[tuple]],
) -> None:
    """Write the sentinel CSV: object, column, type, action, recipe, source, downgraded."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(["object", "column", "type", "action", "recipe", "source", "downgraded"])
        for obj in sorted(all_actions):
            for field_name, (ftype, action, recipe, source, downgraded) in all_actions[obj]:
                w.writerow([obj, field_name, ftype, action, recipe, source, str(downgraded)])


def _write_summary(
    path: Path,
    per_object: list[dict],
    skipped: list[dict],
    limit: int | None,
) -> None:
    summary = {
        "objects": per_object,
        "skipped": skipped,
        "limit": limit,
    }
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


