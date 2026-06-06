"""End-to-end pipeline orchestrator: enumerate → filter → batch → retrieve
+ extract (to temp) → scrub → publish.

The orchestrator is the only place where every stage's lifecycle is visible.
The pipeline is fail-closed: any error before publish leaves the published
path untouched and the per-run temp directory retained for inspection.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from pathlib import Path

from sf_clean_room.audit import AuditLog
from sf_clean_room.batch import build_batches, describe_plan
from sf_clean_room.constants import API_VERSION
from sf_clean_room.enumerate_md import enumerate_all_members
from sf_clean_room.extract import extract_zip_to
from sf_clean_room.filter_md import apply_deny_list
from sf_clean_room.manifest import build_package_xml, retrieved_members_from_zip
from sf_clean_room.publish import SENTINEL_NAME, publish, remove_empty_temp
from sf_clean_room.retrieve import run_batch
from sf_clean_room.scrub import default_stages, run_stages
from sf_clean_room.session import Session
from sf_clean_room.skip_log import SkipLog
from sf_clean_room.soap import SoapClient

SKIPPED_TYPES_NAME = "_skipped-types.csv"


def _log_skips(log: AuditLog, skip: SkipLog) -> None:
    """One-line skip summary to the tee; full verbatim detail to the file only."""
    if not len(skip):
        return
    counts = ", ".join(f"{b}={n}" for b, n in sorted(skip.bucket_counts().items()))
    log.write(f"skipped: {len(skip)} ({counts})")
    for line in skip.audit_lines():
        log.write_file_only(line)


@dataclass(frozen=True)
class RunPaths:
    temp_root: Path
    publish_path: Path
    run_temp_dir: Path  # <temp_root>/<alias>-<utc>-<short_uuid>


def make_run_paths(temp_root: Path, publish_path: Path, org_alias: str) -> RunPaths:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    safe_alias = "".join(c if c.isalnum() or c in "-_." else "_" for c in org_alias)
    run_dir = (temp_root / f"{safe_alias}-{stamp}-{short}").resolve()
    return RunPaths(
        temp_root=temp_root.resolve(),
        publish_path=publish_path.resolve(),
        run_temp_dir=run_dir,
    )


def plan_only(session: Session, log: AuditLog) -> str:
    """``--dry-run``: enumerate, filter, batch, report. No retrieve, no temp,
    no publish-path mutation. Also reports the would-be skip log."""
    client = SoapClient.for_instance(session.session_id, session.instance_url)

    log.section("enumerate")
    log.write("enumerating metadata types via describeMetadata + listMetadata...")
    members, skip = enumerate_all_members(client)
    raw_total = sum(len(v) for v in members.values())
    log.write(f"enumerated {len(members)} types, {raw_total} components")
    _log_skips(log, skip)

    log.section("filter")
    filtered = apply_deny_list(members)
    for tname, n in sorted(filtered.excluded_counts.items()):
        log.write(f"excluded type {tname}: {n} components")
    log.write(
        f"after filter: {len(filtered.kept)} types, "
        f"{sum(len(v) for v in filtered.kept.values())} components "
        f"(excluded {filtered.excluded_total})"
    )

    log.section("batch")
    batches = build_batches(filtered.kept)
    log.write(f"{len(batches)} batch(es) planned")
    plan = describe_plan(batches)
    for line in plan.splitlines():
        log.write_file_only(line)

    # The would-be _skipped-types.csv contents (enumeration skips only; partial
    # retrieves cannot be known without retrieving).
    skip_lines = [f"  {r.type}: {r.bucket}" for r in skip]
    skip_block = (
        "\n\nwould-be _skipped-types.csv:\n" + "\n".join(skip_lines)
        if skip_lines else "\n\nwould-be _skipped-types.csv: (empty)"
    )
    return plan + skip_block


def _build_published_manifest(retrieved_by_type: dict[str, set[str]]) -> str:
    return build_package_xml({t: sorted(ms) for t, ms in retrieved_by_type.items() if ms})


def execute(session: Session, paths: RunPaths, log: AuditLog) -> None:
    """Full run: produce a published folder at ``paths.publish_path``.

    On any failure before publish, the publish path is left untouched and the
    per-run temp directory is retained for inspection.
    """
    client = SoapClient.for_instance(session.session_id, session.instance_url)

    log.section("enumerate")
    log.write("enumerating metadata types via describeMetadata + listMetadata...")
    members, skip = enumerate_all_members(client)
    raw_total = sum(len(v) for v in members.values())
    log.write(f"enumerated {len(members)} types, {raw_total} components")
    _log_skips(log, skip)

    log.section("filter")
    filtered = apply_deny_list(members)
    for tname, n in sorted(filtered.excluded_counts.items()):
        log.write(f"excluded type {tname}: {n} components")
    log.write(
        f"after filter: {len(filtered.kept)} types, "
        f"{sum(len(v) for v in filtered.kept.values())} components "
        f"(excluded {filtered.excluded_total})"
    )

    log.section("batch")
    batches = build_batches(filtered.kept)
    log.write(f"{len(batches)} batch(es) planned")
    for line in describe_plan(batches).splitlines():
        log.write_file_only(line)

    log.section("temp")
    paths.run_temp_dir.mkdir(parents=True, exist_ok=False)
    log.write(f"per-run temp dir: {paths.run_temp_dir}")

    # What Salesforce actually returned, merged across batches (component-accurate).
    retrieved_by_type: dict[str, set[str]] = {}

    log.section("retrieve")
    if not batches:
        log.write("no batches after filtering; manifest will be empty")
    else:
        for i, batch in enumerate(batches, 1):
            log.write(
                f"submitting batch {i}/{len(batches)}: "
                f"{batch.total_count} components, weight {batch.total_weight:,}"
            )

            def _on_submit(async_id: str, _i: int = i) -> None:
                log.write(f"batch {_i} submitted, async_id={async_id}; polling...")

            def _on_poll(elapsed: float, async_id: str, _i: int = i) -> None:
                log.write(f"batch {_i} still running ({elapsed:.0f}s elapsed, async_id={async_id})")

            result = run_batch(client, batch, on_submit=_on_submit, on_poll=_on_poll)
            log.write(
                f"batch {i} {result.status} in {result.duration_secs:.1f}s "
                f"(async_id={result.async_id})"
            )
            # Component-accurate: the returned package.xml is what SF actually gave us.
            for t, ms in retrieved_members_from_zip(result.zip_b64).items():
                retrieved_by_type.setdefault(t, set()).update(ms)
            log.write(f"extracting batch {i} zip to temp...")
            renames = extract_zip_to(result.zip_b64, paths.run_temp_dir)
            if renames:
                log.write(f"batch {i}: {len(renames)} path(s) rewritten during extract (see _path_renames.csv)")

    # Partial-retrieve detection: requested (kept) vs retrieved, per type.
    log.section("verify")
    for tname, requested in sorted(filtered.kept.items()):
        req_n = len(set(requested))
        got_n = len(retrieved_by_type.get(tname, set()))
        if got_n < req_n:
            skip.add(
                type=tname, bucket="partial_retrieve",
                detail="fewer components returned than requested",
                requested=req_n, retrieved=got_n,
            )
            log.write(f"partial retrieve {tname}: requested {req_n}, retrieved {got_n}")

    # Authoritative published manifest = what was actually retrieved (never overstates).
    (paths.run_temp_dir / SENTINEL_NAME).write_text(
        _build_published_manifest(retrieved_by_type), encoding="utf-8"
    )
    # Published skip log (always written; header-only when empty).
    skip.write_csv(paths.run_temp_dir / SKIPPED_TYPES_NAME)
    _log_skips(log, skip)

    log.section("scrub")
    results = run_stages(paths.run_temp_dir, default_stages())
    for r in results:
        if r.clean:
            log.write(f"stage {r.stage_name}: clean")
        else:
            log.write(f"stage {r.stage_name}: {len(r.findings)} finding(s) — aborting publish")
            for f in r.findings:
                log.write(f"  {f.category} at {f.path}: {f.detail}")
    if any(not r.clean for r in results):
        raise RuntimeError("scrub stage produced findings; publish aborted")

    log.section("publish")
    log.write(f"clearing publish path and moving temp tree into {paths.publish_path}...")
    publish(
        paths.run_temp_dir, paths.publish_path,
        sentinel_name=SENTINEL_NAME,
        preceding_artefacts=(SKIPPED_TYPES_NAME,),
    )
    log.write(
        f"published to {paths.publish_path} "
        f"({SKIPPED_TYPES_NAME} then sentinel {SENTINEL_NAME} placed last)"
    )
    remove_empty_temp(paths.run_temp_dir)
    log.write("per-run temp dir removed")
