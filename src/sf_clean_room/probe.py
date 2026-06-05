"""Capability probe: confirm the Data API is reachable before extracting.

Read-only and value-free beyond a single ``SELECT Id ... LIMIT 1`` used purely
to prove the Data API answers for the authenticated session. A Data-API failure
aborts the run before any temp directory or output is produced.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sf_clean_room.records_extract import QueryFn
from sf_clean_room.session import Session


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProbeResult:
    data_api_ok: bool
    probed_object: str
    username: str
    org_id: str
    instance_url: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "data_api_ok": self.data_api_ok,
            "probed_object": self.probed_object,
            "username": self.username,
            "org_id": self.org_id,
            "instance_url": self.instance_url,
            "detail": self.detail,
        }


def probe(session: Session, probe_object: str, query_fn: QueryFn) -> ProbeResult:
    soql = f"SELECT Id FROM {probe_object} LIMIT 1"
    try:
        query_fn(session.alias or session.username, soql)
    except Exception as e:  # noqa: BLE001 — any query failure is a probe failure
        raise ProbeError(
            f"Data API check failed on {probe_object}: {e}. "
            f"Confirm the alias is authenticated and has API + object access."
        ) from e
    return ProbeResult(
        data_api_ok=True,
        probed_object=probe_object,
        username=session.username,
        org_id=session.org_id,
        instance_url=session.instance_url,
        detail="data API reachable",
    )


def write_probe_json(result: ProbeResult, path: Path) -> None:
    path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
