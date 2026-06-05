"""get_records orchestrator: probe → scan + classify → (plan) → extract → publish.

Mirrors the v1 metadata pipeline's discipline: work lands in a per-run temp
directory; the publish path is mutated only at the final step; the sentinel
(``_field-handling-applied.csv``) is moved last. Fail-closed: any error before
publish leaves the publish path untouched and the temp dir retained.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sf_clean_room.audit import AuditLog
from sf_clean_room.plan import Plan, emit_plan, load_plan
from sf_clean_room.probe import probe, write_probe_json
from sf_clean_room.publish import publish, remove_empty_temp
from sf_clean_room.records_extract import (
    AUDIT_SENTINEL,
    SUMMARY_NAME,
    QueryFn,
    extract_object,
    query_records_sf,
    validate_where,
    write_audit_csv,
    write_summary_json,
)
from sf_clean_room.pipeline import RunPaths
from sf_clean_room.schema_scan import (
    DescribeFn,
    describe_object_sf,
    scan_objects,
    write_schema_csv,
)
from sf_clean_room.session import Session


@dataclass(frozen=True)
class RecordsRequest:
    objects: list[str]
    where: str | None
    plan_path: Path | None
    dry_run: bool


def resolve_scope(only: list[str] | None, plan: Plan | None) -> list[str]:
    """Object scope is explicit: --only, or [scope].objects in the plan."""
    objs: list[str] = list(only or [])
    if not objs and plan is not None:
        objs = list(plan.objects)
    if not objs:
        raise ValueError(
            "no objects in scope: pass --only <Object> ... or set [scope].objects in the plan"
        )
    # De-dupe, preserve order.
    seen: set[str] = set()
    ordered: list[str] = []
    for o in objs:
        if o not in seen:
            seen.add(o)
            ordered.append(o)
    return ordered


def dry_run(
    session: Session,
    objects: list[str],
    out_plan_path: Path | None,
    log: AuditLog,
    describe_fn: DescribeFn = describe_object_sf,
) -> str:
    """Probe + scan + classify; emit the annotated plan. No values, no publish."""
    log.section("scan")
    log.write(f"describing {len(objects)} object(s): {', '.join(objects)}")
    scan = scan_objects(session.alias or session.username, objects, describe_fn)
    for obj, fields in scan.items():
        log.write(f"  {obj}: {len(fields)} fields")
    plan_text = emit_plan(scan)
    if out_plan_path is not None:
        out_plan_path.write_text(plan_text, encoding="utf-8")
        log.write(f"annotated plan written to {out_plan_path}")
    return plan_text


def execute(
    session: Session,
    req: RecordsRequest,
    paths: RunPaths,
    log: AuditLog,
    describe_fn: DescribeFn = describe_object_sf,
    query_fn: QueryFn = query_records_sf,
) -> None:
    """Full run: produce a published folder of TSVs at ``paths.publish_path``."""
    alias = session.alias or session.username

    plan: Plan | None = None
    if req.plan_path is not None and req.plan_path.exists():
        plan = load_plan(req.plan_path)
        log.write(f"loaded classification plan: {req.plan_path}")

    where = validate_where(req.where) if req.where else None
    if where and not req.objects:
        raise ValueError("--where requires --only")

    log.section("probe")
    probe_result = probe(session, req.objects[0], query_fn)
    log.write(f"probe: {probe_result.detail} (object {probe_result.probed_object})")

    log.section("scan")
    log.write(f"describing {len(req.objects)} object(s): {', '.join(req.objects)}")
    scan = scan_objects(alias, req.objects, describe_fn)
    for obj, fields in scan.items():
        log.write(f"  {obj}: {len(fields)} fields")

    log.section("temp")
    paths.run_temp_dir.mkdir(parents=True, exist_ok=False)
    log.write(f"per-run temp dir: {paths.run_temp_dir}")
    write_probe_json(probe_result, paths.run_temp_dir / "_capability-probe.json")
    write_schema_csv(scan, paths.run_temp_dir / "_schema-scan.csv")

    log.section("extract")
    results = []
    for obj in req.objects:
        log.write(f"extracting {obj}...")
        res = extract_object(alias, obj, scan[obj], plan, where, paths.run_temp_dir, query_fn)
        log.write(
            f"  {obj}: {res.rows_out} rows, {len(res.columns)} columns "
            f"({dict(sorted(res.action_counts.items()))})"
        )
        if res.downgraded:
            log.write(f"  {obj}: special-category kept WITHOUT justification -> DROPPED: {res.downgraded}")
        if res.drift:
            log.write(f"  {obj}: schema drift (not in plan, classified by default): {res.drift}")
        results.append(res)

    write_summary_json(results, where, paths.run_temp_dir / SUMMARY_NAME)
    # Audit sentinel written into temp like everything else; publish moves it last.
    write_audit_csv(results, where, paths.run_temp_dir / AUDIT_SENTINEL)

    log.section("publish")
    log.write(f"clearing publish path and moving temp tree into {paths.publish_path}...")
    publish(paths.run_temp_dir, paths.publish_path, sentinel_name=AUDIT_SENTINEL)
    log.write(f"published to {paths.publish_path} (sentinel {AUDIT_SENTINEL} placed last)")
    remove_empty_temp(paths.run_temp_dir)
    log.write("per-run temp dir removed")
