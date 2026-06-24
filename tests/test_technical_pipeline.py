"""Tests for technical_pipeline.py — offline, injected HTTP stubs.

Key checks:
- end-to-end with crafted describe/rows for representative objects
- no-raw-dump: no dotted-quad IPs, no email text, no DROP values in published CSVs
- sentinel present + last (mtime ordering)
- one failing object → skipped, run completes
- all failing → abort, publish path untouched
- 0-row object → header-only CSV
"""
import csv
import json
import re
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from sf_clean_room.technical_pipeline import (
    SENTINEL_NAME,
    SUMMARY_NAME,
    TechnicalRequest,
    dry_run,
    execute,
)


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _session(instance_url="https://test.salesforce.com"):
    s = MagicMock()
    s.session_id = "TOKEN"
    s.instance_url = instance_url
    return s


def _response(status: int, body):
    import io as _io
    r = requests.Response()
    r.status_code = status
    r._content = __import__("json").dumps(body).encode()
    return r


def _make_get_fn(describe_map: dict, query_responses: dict | None = None):
    """
    describe_map: {api_name: fields_list} for describe responses.
    query_responses: {api_name: [rows_list, ...]} — each page is one list of row dicts.

    URL matching:
    - Describe URLs contain '/describe' — matched on '/{api_name}/describe'.
    - Query/continuation URLs are URL-encoded SOQL or nextRecordsUrl paths — matched
      by api_name substring (api_names have no URL-special characters).
      Longer names checked first to avoid prefix collisions.
    """
    if query_responses is None:
        query_responses = {}
    page_counters: dict[str, int] = {}
    # Sort by length descending to avoid PermissionSet matching PermissionSetAssignment first.
    sorted_query_keys = sorted(query_responses, key=len, reverse=True)

    def _get(url, **kwargs):
        # Describe endpoint (priority: URL always contains api_name too, so check describe first).
        if "describe" in url:
            for api_name, fields in describe_map.items():
                if f"/{api_name}/describe" in url:
                    return _response(200, {"fields": fields})
            return _response(404, {"message": f"no describe stub for: {url}"})
        # Query / continuation endpoint.
        for api_name in sorted_query_keys:
            if api_name in url:
                pages = query_responses[api_name]
                idx = page_counters.get(api_name, 0)
                page_counters[api_name] = idx + 1
                page = pages[idx] if idx < len(pages) else []
                has_next = idx + 1 < len(pages)
                return _response(200, {
                    "records": page,
                    "done": not has_next,
                    **({"nextRecordsUrl": f"/nextRecordsUrl/{api_name}"} if has_next else {}),
                })
        return _response(404, {"message": f"unexpected URL: {url}"})
    return _get


def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


# ---------------------------------------------------------------------------
# Basic end-to-end: LoginHistory (SourceIp→DERIVE, Status→PASS, UserId→RAW)
# ---------------------------------------------------------------------------

def test_login_history_extraction(tmp_path):
    fields = [
        {"name": "Id",       "type": "id",     "queryable": True},
        {"name": "UserId",   "type": "reference","queryable": True},
        {"name": "SourceIp", "type": "string",  "queryable": True},
        {"name": "Status",   "type": "string",  "queryable": True},
    ]
    rows = [
        {"Id": "0Yx001", "UserId": "005001", "SourceIp": "10.0.1.42", "Status": "Success"},
    ]
    get_fn = _make_get_fn({"LoginHistory": fields}, {"LoginHistory": [rows]})
    req = TechnicalRequest(only=["LoginHistory"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "audit.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=get_fn)

    csv_path = publish_path / "LoginHistory.csv"
    assert csv_path.exists()
    header_line = csv_path.read_text(encoding="utf-8").splitlines()[0]
    # SourceIp → DERIVE (ip_prefix), so column present but value anonymised.
    assert "SourceIp" in header_line
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        data = list(reader)
    assert len(data) == 1
    # IP should be zeroed last octet, not the original value.
    assert data[0]["SourceIp"] == "10.0.1.0"
    # UserId is RAW.
    assert data[0]["UserId"] == "005001"
    # Status is PASS.
    assert data[0]["Status"] == "Success"


# ---------------------------------------------------------------------------
# No-raw-dump: SourceIp dotted-quad must not appear verbatim
# ---------------------------------------------------------------------------

def test_no_raw_ip_in_published_csv(tmp_path):
    fields = [
        {"name": "Id",       "type": "id",     "queryable": True},
        {"name": "SourceIp", "type": "string",  "queryable": True},
    ]
    raw_ip = "203.0.113.55"
    rows = [{"Id": "0Yx001", "SourceIp": raw_ip}]
    get_fn = _make_get_fn({"LoginHistory": fields}, {"LoginHistory": [rows]})
    req = TechnicalRequest(only=["LoginHistory"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=get_fn)

    content = (publish_path / "LoginHistory.csv").read_text(encoding="utf-8")
    assert raw_ip not in content
    # Verify it was derived.
    assert "203.0.113.0" in content


# ---------------------------------------------------------------------------
# LoginGeo: fine-geo absent, coarse geo present
# ---------------------------------------------------------------------------

def test_login_geo_fine_geo_columns_absent(tmp_path):
    fields = [
        {"name": "Id",          "type": "id",     "queryable": True},
        {"name": "Latitude",    "type": "double",  "queryable": True},
        {"name": "Longitude",   "type": "double",  "queryable": True},
        {"name": "City",        "type": "string",  "queryable": True},
        {"name": "PostalCode",  "type": "string",  "queryable": True},
        {"name": "Country",     "type": "string",  "queryable": True},
        {"name": "Subdivision", "type": "string",  "queryable": True},
    ]
    rows = [{"Id": "001", "Latitude": 51.5, "Longitude": -0.1,
             "City": "London", "PostalCode": "SW1A", "Country": "GB", "Subdivision": "ENG"}]
    get_fn = _make_get_fn({"LoginGeo": fields}, {"LoginGeo": [rows]})
    req = TechnicalRequest(only=["LoginGeo"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=get_fn)

    header = (publish_path / "LoginGeo.csv").read_text(encoding="utf-8").splitlines()[0]
    for fine in ("Latitude", "Longitude", "City", "PostalCode"):
        assert fine not in header, f"{fine} should be absent (fine geo dropped)"
    assert "Country" in header
    assert "Subdivision" in header


# ---------------------------------------------------------------------------
# SetupAuditTrail: Display absent (curated DROP), Action present (PASS)
# ---------------------------------------------------------------------------

def test_setup_audit_trail_display_absent(tmp_path):
    fields = [
        {"name": "Id",      "type": "id",     "queryable": True},
        {"name": "Action",  "type": "string",  "queryable": True},
        {"name": "Section", "type": "string",  "queryable": True},
        {"name": "Display", "type": "string",  "queryable": True},
    ]
    rows = [{"Id": "SAT001", "Action": "changedProfilePermissions",
             "Section": "Manage Users", "Display": "admin changed user Bob's profile"}]
    get_fn = _make_get_fn({"SetupAuditTrail": fields}, {"SetupAuditTrail": [rows]})
    req = TechnicalRequest(only=["SetupAuditTrail"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=get_fn)

    content = (publish_path / "SetupAuditTrail.csv").read_text(encoding="utf-8")
    assert "Display" not in content.splitlines()[0]
    assert "Action" in content.splitlines()[0]
    # Verbatim Display text must not leak.
    assert "changed user Bob" not in content


# ---------------------------------------------------------------------------
# FlowInterview: InterviewLabel absent
# ---------------------------------------------------------------------------

def test_flow_interview_interview_label_absent(tmp_path):
    fields = [
        {"name": "Id",             "type": "id",    "queryable": True},
        {"name": "InterviewLabel", "type": "string", "queryable": True},
        {"name": "CurrentElement", "type": "string", "queryable": True},
    ]
    rows = [{"Id": "0Fv001", "InterviewLabel": "Order {!Contact.Name}", "CurrentElement": "Decision_1"}]
    get_fn = _make_get_fn({"FlowInterview": fields}, {"FlowInterview": [rows]})
    req = TechnicalRequest(only=["FlowInterview"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=get_fn)

    content = (publish_path / "FlowInterview.csv").read_text(encoding="utf-8")
    assert "InterviewLabel" not in content.splitlines()[0]
    assert "Contact.Name" not in content


# ---------------------------------------------------------------------------
# Sentinel is present and written last
# ---------------------------------------------------------------------------

def test_sentinel_present_and_last(tmp_path):
    fields = [{"name": "Id", "type": "id", "queryable": True}]
    rows = [{"Id": "001"}]
    get_fn = _make_get_fn({"ApexClass": fields}, {"ApexClass": [rows]})
    req = TechnicalRequest(only=["ApexClass"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=get_fn)

    sentinel = publish_path / SENTINEL_NAME
    assert sentinel.exists(), "sentinel must exist"
    # Sentinel must be the last file by mtime (or at least not older than CSVs).
    files = list(publish_path.iterdir())
    assert len(files) >= 2  # at least ApexClass.csv + sentinel
    csvs = [f for f in files if f.name != SENTINEL_NAME]
    sentinel_mtime = sentinel.stat().st_mtime
    for csv_f in csvs:
        assert sentinel_mtime >= csv_f.stat().st_mtime - 0.01, (
            f"sentinel mtime {sentinel_mtime} < {csv_f.name} mtime {csv_f.stat().st_mtime}"
        )


# ---------------------------------------------------------------------------
# Sentinel CSV structure
# ---------------------------------------------------------------------------

def test_sentinel_csv_has_correct_columns(tmp_path):
    fields = [
        {"name": "Id",       "type": "id",     "queryable": True},
        {"name": "SourceIp", "type": "string",  "queryable": True},
    ]
    rows = [{"Id": "001", "SourceIp": "10.0.0.1"}]
    get_fn = _make_get_fn({"LoginHistory": fields}, {"LoginHistory": [rows]})
    req = TechnicalRequest(only=["LoginHistory"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=get_fn)

    with open(publish_path / SENTINEL_NAME, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        rows_out = list(reader)
    assert headers == ["object", "column", "type", "action", "recipe", "source", "downgraded"]
    objects_in_sentinel = {r["object"] for r in rows_out}
    assert "LoginHistory" in objects_in_sentinel


# ---------------------------------------------------------------------------
# One failing object → skipped, run completes
# ---------------------------------------------------------------------------

def test_one_failing_object_skipped_run_completes(tmp_path):
    good_fields = [{"name": "Id", "type": "id", "queryable": True}]
    good_rows = [{"Id": "001"}]

    def _get(url, **kwargs):
        if "describe" in url:
            if "LoginHistory" in url:
                return _response(403, {"message": "INSUFFICIENT_ACCESS"})
            if "ApexClass" in url:
                return _response(200, {"fields": good_fields})
        elif "ApexClass" in url:
            return _response(200, {"records": good_rows, "done": True})
        return _response(404, {})

    req = TechnicalRequest(only=["ApexClass", "LoginHistory"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=_get)

    # ApexClass succeeded.
    assert (publish_path / "ApexClass.csv").exists()
    # LoginHistory was skipped — no CSV for it.
    assert not (publish_path / "LoginHistory.csv").exists()
    # Sentinel present.
    assert (publish_path / SENTINEL_NAME).exists()
    # Summary records the skip.
    summary = json.loads((publish_path / SUMMARY_NAME).read_text(encoding="utf-8"))
    skipped_names = [s["object"] for s in summary["skipped"]]
    assert "LoginHistory" in skipped_names


# ---------------------------------------------------------------------------
# All failing → abort, publish path untouched
# ---------------------------------------------------------------------------

def test_all_failing_aborts_without_touching_publish_path(tmp_path):
    def _get(url, **kwargs):
        return _response(403, {"message": "forbidden"})

    req = TechnicalRequest(only=["ApexClass"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    (publish_path / "old_file.csv").write_text("old", encoding="utf-8")
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    with pytest.raises(RuntimeError, match="every object failed"):
        execute(_session(), publish_path, req, tmp_path, log, get_fn=_get)

    # Old file must still be there (publish path untouched).
    assert (publish_path / "old_file.csv").read_text(encoding="utf-8") == "old"
    assert not (publish_path / SENTINEL_NAME).exists()


# ---------------------------------------------------------------------------
# 0-row object → header-only CSV (not fatal)
# ---------------------------------------------------------------------------

def test_zero_row_object_produces_header_only_csv(tmp_path):
    fields = [
        {"name": "Id",   "type": "id",     "queryable": True},
        {"name": "Name", "type": "string",  "queryable": True},
    ]
    get_fn = _make_get_fn({"ApexClass": fields}, {"ApexClass": [[]]})  # empty page
    req = TechnicalRequest(only=["ApexClass"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=get_fn)

    csv_path = publish_path / "ApexClass.csv"
    assert csv_path.exists()
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1  # header only
    assert "Id" in lines[0]
    assert (publish_path / SENTINEL_NAME).exists()


# ---------------------------------------------------------------------------
# REST pseudo-endpoints: limits and recordCount
# ---------------------------------------------------------------------------

def test_limits_endpoint_passes_through(tmp_path):
    limits_body = {
        "DailyApiRequests": {"Max": 15000, "Remaining": 14800},
        "DataStorageMB": {"Max": 5, "Remaining": 4},
    }

    def _get(url, **kwargs):
        if "/limits/" in url and "recordCount" not in url:
            return _response(200, limits_body)
        return _response(404, {})

    req = TechnicalRequest(only=["limits"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=_get)

    csv_path = publish_path / "limits.csv"
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "LimitName" in content
    assert "DailyApiRequests" in content


def test_recordcount_endpoint_passes_through(tmp_path):
    rc_body = {"sObjects": [{"name": "Account", "count": 5000}, {"name": "Contact", "count": 3000}]}

    def _get(url, **kwargs):
        if "recordCount" in url:
            return _response(200, rc_body)
        return _response(404, {})

    req = TechnicalRequest(only=["recordCount"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    execute(_session(), publish_path, req, tmp_path, log, get_fn=_get)

    csv_path = publish_path / "recordCount.csv"
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "ObjectName" in content
    assert "Account" in content


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------

def test_dry_run_returns_plan_text_no_publish(tmp_path):
    fields = [
        {"name": "Id",       "type": "id",     "queryable": True},
        {"name": "SourceIp", "type": "string",  "queryable": True},
    ]
    get_fn = _make_get_fn({"LoginHistory": fields}, {})
    req = TechnicalRequest(only=["LoginHistory"], limit=None, plan_path=None, dry_run=True)
    publish_path = tmp_path / "out"
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    report = dry_run(_session(), publish_path, req, log, get_fn=get_fn)

    assert "LoginHistory" in report
    assert "SourceIp" in report
    # Publish path should not have been created / written.
    assert not publish_path.exists() or not any(publish_path.iterdir())


def test_dry_run_writes_plan_file(tmp_path):
    fields = [{"name": "Id", "type": "id", "queryable": True}]
    get_fn = _make_get_fn({"ApexClass": fields}, {})
    plan_path = tmp_path / "plan.toml"
    req = TechnicalRequest(only=["ApexClass"], limit=None, plan_path=plan_path, dry_run=True)
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    dry_run(_session(), tmp_path / "out", req, log, get_fn=get_fn)

    assert plan_path.exists()
    content = plan_path.read_text(encoding="utf-8")
    assert "[scope]" in content
    assert "ApexClass" in content


# ---------------------------------------------------------------------------
# Unknown --only name aborts before any query
# ---------------------------------------------------------------------------

def test_unknown_only_raises_before_any_query(tmp_path):
    get_fn = MagicMock(side_effect=AssertionError("should not be called"))
    req = TechnicalRequest(only=["NotAnObject"], limit=None, plan_path=None, dry_run=False)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    log = MagicMock(); log.path = tmp_path / "a.log"
    log.section = MagicMock(); log.write = MagicMock()

    with pytest.raises(ValueError, match="unknown object"):
        execute(_session(), publish_path, req, tmp_path, log, get_fn=get_fn)

    get_fn.assert_not_called()
