"""get_code_analysis orchestrator: run sf code-analyzer over a metadata folder.

No Salesforce session needed — the analyser runs locally against files on
disk (the output of get_metadata).  The metadata folder MUST contain
package.xml (the get_metadata sentinel) as a pre-condition.

Output: HTML + CSV + JSON from the analyser, plus a _summary.json sentinel.
See docs/reference/salesforce-code-analyser.md for the schema reference.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from sf_clean_room.audit import AuditLog
from sf_clean_room.publish import publish, remove_empty_temp
from sf_clean_room.sfcli import SfCliError, run_cli_text

SENTINEL_NAME = "_summary.json"
_METADATA_SENTINEL = "package.xml"
_PLUGIN_INSTALL_HINT = "sf plugins install @salesforce/plugin-code-analyzer"


def _check_plugin(log: AuditLog) -> None:
    """Raise RuntimeError if sf code-analyzer plugin is not installed."""
    try:
        run_cli_text(["sf", "code-analyzer", "run", "--help"])
    except SfCliError:
        raise RuntimeError(
            "sf code-analyzer plugin not installed or not on PATH.\n"
            f"Install with: {_PLUGIN_INSTALL_HINT}\n"
            "Then re-run this command."
        )
    log.write("sf code-analyzer plugin: available")


def _check_metadata(metadata_path: Path) -> None:
    """Raise if metadata_path is missing or has no package.xml sentinel."""
    if not metadata_path.is_dir():
        raise ValueError(
            f"--metadata-path does not exist or is not a directory: {metadata_path}"
        )
    if not (metadata_path / _METADATA_SENTINEL).exists():
        raise ValueError(
            f"--metadata-path has no {_METADATA_SENTINEL} — "
            f"run get_metadata first to populate {metadata_path}"
        )


def _stem(org_alias: str) -> str:
    return f"code_analyser_results_{org_alias}"


def dry_run(org_alias: str, metadata_path: Path, log: AuditLog) -> str:
    """Validate pre-conditions and report what the real run would do."""
    log.section("dry-run validate")
    _check_plugin(log)
    _check_metadata(metadata_path)
    log.write(f"metadata path ok: {metadata_path}")
    stem = _stem(org_alias)
    return (
        f"dry-run: pre-conditions met\n"
        f"  metadata-path : {metadata_path} ({_METADATA_SENTINEL} present)\n"
        f"  output files  :\n"
        f"    {stem}.html\n"
        f"    {stem}.csv\n"
        f"    {stem}.json\n"
        f"    {SENTINEL_NAME}  (sentinel, written last)\n"
        f"Note: violation count is not available in dry-run; "
        f"it requires the full analysis run."
    )


def execute(
    org_alias: str,
    metadata_path: Path,
    publish_path: Path,
    temp_root: Path,
    log: AuditLog,
) -> Path:
    """Run sf code-analyzer over the metadata folder and publish the results."""
    _check_plugin(log)
    _check_metadata(metadata_path)

    run_temp = (temp_root / f"codeanalysis-{uuid.uuid4().hex[:8]}").resolve()
    run_temp.mkdir(parents=True, exist_ok=False)
    log.write(f"per-run temp dir: {run_temp}")

    stem = _stem(org_alias)
    html_path = run_temp / f"{stem}.html"
    csv_path  = run_temp / f"{stem}.csv"
    json_path = run_temp / f"{stem}.json"

    log.section("analyse")
    cmd = [
        "sf", "code-analyzer", "run",
        "--target", str(metadata_path),
        "--output-file", str(html_path),
        "--output-file", str(csv_path),
        "--output-file", str(json_path),
    ]
    log.write(f"command: sf code-analyzer run --target <metadata> (3 output formats)")
    try:
        run_cli_text(cmd, timeout=3600)
    except SfCliError as e:
        raise RuntimeError(f"sf code-analyzer failed: {e}") from e
    except subprocess.TimeoutExpired:
        raise RuntimeError("sf code-analyzer timed out after 1 hour")

    violation_counts: dict = {}
    engine_versions: dict = {}
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            violation_counts = data.get("violationCounts", {})
            engine_versions = data.get("versions", {})
        except (json.JSONDecodeError, OSError):
            pass

    total = violation_counts.get("total", "?")
    log.write(f"analysis complete: {total} violation(s) total")

    summary = {
        "org_alias": org_alias,
        "metadata_path": str(metadata_path),
        "violation_counts": violation_counts,
        "engine_versions": engine_versions,
        "output_files": {
            "html": f"{stem}.html",
            "csv": f"{stem}.csv",
            "json": f"{stem}.json",
        },
    }
    (run_temp / SENTINEL_NAME).write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    log.section("publish")
    publish(run_temp, publish_path, sentinel_name=SENTINEL_NAME)
    log.write(f"published to {publish_path} (sentinel {SENTINEL_NAME} last)")
    remove_empty_temp(run_temp)
    return publish_path
