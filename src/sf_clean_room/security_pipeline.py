"""get_security_health_check orchestrator: Tooling API query -> JSON publish.

No field classification: the artefact contains only org configuration data
(scores, enabled/disabled settings) — no user identifiers, no PII, no
customer record data.  See docs/ideation/salesforce-security-health-check.md.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import requests

from sf_clean_room.audit import AuditLog
from sf_clean_room.constants import API_VERSION
from sf_clean_room.publish import publish, remove_empty_temp
from sf_clean_room.session import Session

GetFn = Callable[..., requests.Response]


def _default_get(url: str, **kwargs) -> requests.Response:
    return requests.get(url, **kwargs)


def _headers(session: Session) -> dict:
    return {
        "Authorization": f"Bearer {session.session_id}",
        "Content-Type": "application/json",
    }


def _tooling_query(session: Session, soql: str, get_fn: GetFn) -> dict:
    encoded = urlencode({"q": soql})
    url = (
        f"{session.instance_url}/services/data/v{API_VERSION}"
        f"/tooling/query?{encoded}"
    )
    r = get_fn(url, headers=_headers(session), timeout=60)
    if r.status_code != 200:
        raise RuntimeError(
            f"Tooling API query failed ({r.status_code}): {r.text[:300]}\n"
            f"SOQL: {soql[:120]}"
        )
    return r.json()


def _collect_risks(session: Session, get_fn: GetFn) -> list[dict]:
    """Fetch all SecurityHealthCheckRisks rows, handling nextRecordsUrl pagination."""
    result = _tooling_query(
        session,
        "SELECT RiskType, Setting, SettingGroup, OrgValue, StandardValue "
        "FROM SecurityHealthCheckRisks",
        get_fn,
    )
    risks: list[dict] = list(result.get("records", []))
    while not result.get("done", True) and result.get("nextRecordsUrl"):
        url = session.instance_url + result["nextRecordsUrl"]
        r = get_fn(url, headers=_headers(session), timeout=60)
        if r.status_code != 200:
            raise RuntimeError(
                f"Pagination failed ({r.status_code}): {r.text[:300]}"
            )
        result = r.json()
        risks.extend(result.get("records", []))
    return risks


def sentinel_name(org_alias: str) -> str:
    return f"securityhealthcheck_{org_alias}.json"


def dry_run(
    session: Session,
    log: AuditLog,
    get_fn: GetFn = _default_get,
) -> str:
    """Query the health-check score only (fast); report what a real run would write."""
    log.section("dry-run query")
    result = _tooling_query(
        session, "SELECT Id, Score FROM SecurityHealthCheck", get_fn
    )
    records = result.get("records", [])
    if not records:
        return "dry-run: SecurityHealthCheck returned 0 records (feature unavailable in this org)"
    score = records[0].get("Score", "n/a")
    log.write(f"SecurityHealthCheck score={score}")
    return (
        f"dry-run: SecurityHealthCheck score={score}\n"
        f"real run would also fetch SecurityHealthCheckRisks and write:\n"
        f"  securityhealthcheck_<org_alias>.json  (sentinel, written last)\n"
        f"\nJSON structure:\n"
        f"  SecurityHealthCheck: {{Id, Score}}\n"
        f"  Risks: [{{RiskType, Setting, SettingGroup, OrgValue, StandardValue}}, ...]\n"
        f"  risk_count: <int>"
    )


def execute(
    session: Session,
    publish_path: Path,
    org_alias: str,
    temp_root: Path,
    log: AuditLog,
    get_fn: GetFn = _default_get,
) -> Path:
    """Fetch the security health check and publish the JSON snapshot."""
    run_temp = (temp_root / f"shc-{uuid.uuid4().hex[:8]}").resolve()
    run_temp.mkdir(parents=True, exist_ok=False)
    log.write(f"per-run temp dir: {run_temp}")

    log.section("query")
    shc_result = _tooling_query(
        session, "SELECT Id, Score FROM SecurityHealthCheck", get_fn
    )
    shc_records = shc_result.get("records", [])
    if not shc_records:
        raise RuntimeError(
            "SecurityHealthCheck returned no records — feature unavailable in this org"
        )
    shc_row = {k: v for k, v in shc_records[0].items() if k != "attributes"}

    risks = _collect_risks(session, get_fn)
    log.write(f"SecurityHealthCheck score={shc_row.get('Score')} risks={len(risks)}")

    payload = {
        "SecurityHealthCheck": shc_row,
        "Risks": risks,
        "risk_count": len(risks),
    }

    out_name = sentinel_name(org_alias)
    out_path = run_temp / out_name
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    log.section("publish")
    publish(run_temp, publish_path, sentinel_name=out_name)
    log.write(f"published to {publish_path} (sentinel {out_name} last)")
    remove_empty_temp(run_temp)
    return publish_path
