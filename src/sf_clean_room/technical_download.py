"""Technical-objects download: describe fields + page records via SOQL/Tooling/REST.

All HTTP calls go through an injectable ``get_fn`` parameter (default:
``requests.get``) so tests can substitute a stub without live networking.

Read-only: only HTTP GET.  Raw query results stay in process memory — the caller
(technical_pipeline.py) classifies them before writing anything.
"""
from __future__ import annotations

from typing import Callable, Iterator
from urllib.parse import quote

import requests

from sf_clean_room.constants import API_VERSION
from sf_clean_room.session import Session
from sf_clean_room.technical_catalog import LAYER0_SKIP_NAMES, LAYER0_SKIP_TYPES
from sf_clean_room.technical_classify import FieldMeta

GetFn = Callable[..., requests.Response]


class TechnicalDownloadError(RuntimeError):
    pass


def _default_get(url: str, **kwargs) -> requests.Response:
    return requests.get(url, **kwargs)


def _headers(session: Session) -> dict:
    return {
        "Authorization": f"Bearer {session.session_id}",
        "Content-Type": "application/json",
    }


def _get(session: Session, url: str, get_fn: GetFn, timeout: int = 120) -> requests.Response:
    return get_fn(url, headers=_headers(session), timeout=timeout)


# ---------------------------------------------------------------------------
# Describe: field metas after Layer-0 skip
# ---------------------------------------------------------------------------

def describe_fields(
    session: Session,
    api_name: str,
    transport: str,
    get_fn: GetFn = _default_get,
) -> list[FieldMeta]:
    """Return the non-Layer-0-skipped queryable fields for ``api_name``.

    ``transport`` is ``"tooling"`` (Tooling describe endpoint) or anything
    else (SObject describe endpoint).
    Raises ``TechnicalDownloadError`` on HTTP error or empty safe-field list.
    """
    if transport == "tooling":
        url = (
            f"{session.instance_url}/services/data/v{API_VERSION}"
            f"/tooling/sobjects/{api_name}/describe"
        )
    else:
        url = (
            f"{session.instance_url}/services/data/v{API_VERSION}"
            f"/sobjects/{api_name}/describe"
        )
    r = _get(session, url, get_fn)
    if r.status_code != 200:
        raise TechnicalDownloadError(
            f"describe failed for {api_name} ({r.status_code}): {r.text[:300]}"
        )
    fields = []
    for f in r.json().get("fields", []):
        if not f.get("queryable", True):
            continue
        if f.get("type", "").lower() in LAYER0_SKIP_TYPES:
            continue
        if f.get("name", "") in LAYER0_SKIP_NAMES:
            continue
        fields.append(FieldMeta(
            name=f["name"],
            type=f.get("type", ""),
            label=f.get("label", ""),
        ))
    if not fields:
        raise TechnicalDownloadError(
            f"no safe queryable fields after Layer-0 skip for {api_name}"
        )
    return fields


# ---------------------------------------------------------------------------
# SOQL queryMore pagination
# ---------------------------------------------------------------------------

def page_soql(
    session: Session,
    soql: str,
    limit: int | None = None,
    get_fn: GetFn = _default_get,
) -> Iterator[dict]:
    """Yield records from a SOQL query, following queryMore to exhaustion.

    Strips ``attributes`` from each record.  Stops early when ``limit`` rows
    have been yielded.
    """
    url = f"{session.instance_url}/services/data/v{API_VERSION}/query?q={quote(soql)}"
    count = 0
    while url:
        r = _get(session, url, get_fn)
        if r.status_code != 200:
            raise TechnicalDownloadError(
                f"SOQL query failed ({r.status_code}): {r.text[:300]}"
            )
        payload = r.json()
        for rec in payload.get("records", []):
            rec.pop("attributes", None)
            yield rec
            count += 1
            if limit is not None and count >= limit:
                return
        next_url = payload.get("nextRecordsUrl")
        if next_url and not payload.get("done", True):
            url = f"{session.instance_url}{next_url}"
        else:
            url = None


# ---------------------------------------------------------------------------
# Tooling query (follows nextRecordsUrl)
# ---------------------------------------------------------------------------

def query_tooling(
    session: Session,
    soql: str,
    limit: int | None = None,
    get_fn: GetFn = _default_get,
) -> list[dict]:
    """Run a Tooling API query, collecting all pages into a list.

    The proven reference tool did not follow nextRecordsUrl; this version does
    because Tooling supports it and large test-result tables can exceed one page.
    """
    base = f"{session.instance_url}/services/data/v{API_VERSION}/tooling"
    url = f"{base}/query/?q={quote(soql)}"
    records: list[dict] = []
    while url:
        r = _get(session, url, get_fn)
        if r.status_code != 200:
            raise TechnicalDownloadError(
                f"Tooling query failed ({r.status_code}): {r.text[:300]}"
            )
        payload = r.json()
        for rec in payload.get("records", []):
            rec.pop("attributes", None)
            records.append(rec)
            if limit is not None and len(records) >= limit:
                return records
        next_url = payload.get("nextRecordsUrl")
        if next_url and not payload.get("done", True):
            url = f"{session.instance_url}{next_url}"
        else:
            url = None
    return records


# ---------------------------------------------------------------------------
# EntityDefinition keyset pagination
# ---------------------------------------------------------------------------

def page_entitydefinition(
    session: Session,
    fields: list[FieldMeta],
    limit: int | None = None,
    get_fn: GetFn = _default_get,
) -> Iterator[dict]:
    """Yield EntityDefinition rows via keyset pagination on ``QualifiedApiName``.

    ``QualifiedApiName`` must be present in ``fields`` (it passes Layer-0 and
    is classified PASS by the generic rules).
    """
    field_names = [f.name for f in fields]
    if "QualifiedApiName" not in field_names:
        raise TechnicalDownloadError(
            "EntityDefinition keyset pagination requires QualifiedApiName in fields"
        )
    batch = 2000
    last_value = ""
    count = 0
    while True:
        soql = (
            f"SELECT {', '.join(field_names)} FROM EntityDefinition "
            f"WHERE QualifiedApiName > '{last_value}' "
            f"ORDER BY QualifiedApiName ASC "
            f"LIMIT {batch}"
        )
        url = f"{session.instance_url}/services/data/v{API_VERSION}/query?q={quote(soql)}"
        r = _get(session, url, get_fn)
        if r.status_code != 200:
            raise TechnicalDownloadError(
                f"EntityDefinition query failed ({r.status_code}): {r.text[:300]}"
            )
        payload = r.json()
        records = payload.get("records", [])
        if not records:
            return
        for rec in records:
            rec.pop("attributes", None)
            yield rec
            count += 1
            if limit is not None and count >= limit:
                return
        last_value = records[-1].get("QualifiedApiName", "")
        if not last_value or len(records) < batch:
            return


# ---------------------------------------------------------------------------
# REST pseudo-endpoints (fixed schemas, all PASS)
# ---------------------------------------------------------------------------

def fetch_limits(
    session: Session,
    get_fn: GetFn = _default_get,
) -> list[dict]:
    """Return limits data as ``[{'LimitName': str, 'Max': int, 'Remaining': int}]``."""
    url = f"{session.instance_url}/services/data/v{API_VERSION}/limits/"
    r = _get(session, url, get_fn)
    if r.status_code != 200:
        raise TechnicalDownloadError(f"limits fetch failed ({r.status_code}): {r.text[:300]}")
    rows = []
    for key, val in r.json().items():
        if isinstance(val, dict):
            rows.append({
                "LimitName": key,
                "Max": val.get("Max"),
                "Remaining": val.get("Remaining"),
            })
    return rows


def fetch_recordcount(
    session: Session,
    get_fn: GetFn = _default_get,
) -> list[dict]:
    """Return record-count data as ``[{'ObjectName': str, 'RecordCount': int}]``."""
    url = f"{session.instance_url}/services/data/v{API_VERSION}/limits/recordCount"
    r = _get(session, url, get_fn)
    if r.status_code != 200:
        raise TechnicalDownloadError(
            f"recordCount fetch failed ({r.status_code}): {r.text[:300]}"
        )
    data = r.json().get("sObjects", [])
    return [
        {"ObjectName": obj.get("name"), "RecordCount": obj.get("count")}
        for obj in data
    ]
