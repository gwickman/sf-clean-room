"""Offline tests for security_pipeline (get_security_health_check).

All Tooling API calls are mocked via the injectable get_fn so no network
or Salesforce session is needed.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from sf_clean_room.audit import audit_log
from sf_clean_room.security_pipeline import (
    dry_run,
    execute,
    sentinel_name,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALIAS = "test_org"


def _mock_session(instance_url="https://test.my.salesforce.com"):
    s = MagicMock()
    s.session_id = "TOKEN"
    s.instance_url = instance_url
    return s


def _make_get_fn(responses: dict):
    """Return a get_fn stub that maps URL substrings to (status, json_body) tuples."""
    def _get(url, **kwargs):
        for key, (status, body) in responses.items():
            if key in url:
                r = MagicMock()
                r.status_code = status
                r.json.return_value = body
                r.text = json.dumps(body)
                return r
        raise AssertionError(f"Unexpected URL: {url}")
    return _get


_SHC_ROW = {"Id": "000000000000000AAA", "Score": 75, "attributes": {"type": "SecurityHealthCheck"}}
_RISKS = [
    {
        "attributes": {"type": "SecurityHealthCheckRisks"},
        "RiskType": "HIGH_RISK",
        "Setting": "Session timeout",
        "SettingGroup": "SessionSettings",
        "OrgValue": "12 hours",
        "StandardValue": "2 hours",
    },
    {
        "attributes": {"type": "SecurityHealthCheckRisks"},
        "RiskType": "MEETS_STANDARD",
        "Setting": "Maximum invalid login attempts",
        "SettingGroup": "PasswordPolicies",
        "OrgValue": "5",
        "StandardValue": "5",
    },
]

# Risks key must come BEFORE the score key: "SecurityHealthCheck" is a
# substring of "SecurityHealthCheckRisks", so the more-specific key wins.
_GOOD_RESPONSES = {
    "SecurityHealthCheckRisks": (
        200,
        {"done": True, "records": _RISKS, "totalSize": 2},
    ),
    "SecurityHealthCheck": (
        200,
        {"done": True, "records": [_SHC_ROW], "totalSize": 1},
    ),
}


# ---------------------------------------------------------------------------
# sentinel_name
# ---------------------------------------------------------------------------

def test_sentinel_name():
    assert sentinel_name("myorg") == "securityhealthcheck_myorg.json"


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------

def test_dry_run_returns_score(tmp_path):
    get_fn = _make_get_fn(_GOOD_RESPONSES)
    session = _mock_session()
    with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
        result = dry_run(session, log, get_fn=get_fn)
    assert "75" in result
    assert "dry-run" in result


def test_dry_run_no_records(tmp_path):
    get_fn = _make_get_fn({
        "SecurityHealthCheckRisks": (200, {"done": True, "records": [], "totalSize": 0}),
        "SecurityHealthCheck": (200, {"done": True, "records": [], "totalSize": 0}),
    })
    session = _mock_session()
    with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
        result = dry_run(session, log, get_fn=get_fn)
    assert "0 records" in result or "unavailable" in result


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

def test_execute_writes_sentinel(tmp_path):
    get_fn = _make_get_fn(_GOOD_RESPONSES)
    session = _mock_session()
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
        execute(session, publish_path, _ALIAS, tmp_path / "temp", log, get_fn=get_fn)

    out = publish_path / sentinel_name(_ALIAS)
    assert out.exists(), "sentinel JSON file must be present"


def test_execute_sentinel_is_valid_json(tmp_path):
    get_fn = _make_get_fn(_GOOD_RESPONSES)
    session = _mock_session()
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
        execute(session, publish_path, _ALIAS, tmp_path / "temp", log, get_fn=get_fn)

    data = json.loads((publish_path / sentinel_name(_ALIAS)).read_text(encoding="utf-8"))
    assert "SecurityHealthCheck" in data
    assert "Risks" in data
    assert data["risk_count"] == len(_RISKS)
    assert data["SecurityHealthCheck"]["Score"] == 75
    # attributes key must be stripped from the SecurityHealthCheck object
    assert "attributes" not in data["SecurityHealthCheck"]


def test_execute_risks_list_preserved(tmp_path):
    get_fn = _make_get_fn(_GOOD_RESPONSES)
    session = _mock_session()
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
        execute(session, publish_path, _ALIAS, tmp_path / "temp", log, get_fn=get_fn)

    data = json.loads((publish_path / sentinel_name(_ALIAS)).read_text(encoding="utf-8"))
    assert len(data["Risks"]) == 2
    risk_types = {r["RiskType"] for r in data["Risks"]}
    assert "HIGH_RISK" in risk_types
    assert "MEETS_STANDARD" in risk_types


def test_execute_no_shc_records_raises(tmp_path):
    get_fn = _make_get_fn({
        "SecurityHealthCheckRisks": (200, {"done": True, "records": [], "totalSize": 0}),
        "SecurityHealthCheck": (200, {"done": True, "records": [], "totalSize": 0}),
    })
    session = _mock_session()
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    with pytest.raises(RuntimeError, match="no records"):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            execute(session, publish_path, _ALIAS, tmp_path / "temp", log, get_fn=get_fn)


def test_execute_api_error_raises(tmp_path):
    get_fn = _make_get_fn({
        "SecurityHealthCheckRisks": (200, {"done": True, "records": [], "totalSize": 0}),
        "SecurityHealthCheck": (401, {"message": "Session expired"}),
    })
    session = _mock_session()
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    with pytest.raises(RuntimeError, match="401"):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            execute(session, publish_path, _ALIAS, tmp_path / "temp", log, get_fn=get_fn)


def test_execute_publish_path_not_mutated_on_error(tmp_path):
    """Publish path must not be touched when execution fails."""
    sentinel_before = tmp_path / "out" / sentinel_name(_ALIAS)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    sentinel_before.write_text("prior", encoding="utf-8")

    get_fn = _make_get_fn({
        "SecurityHealthCheckRisks": (200, {"done": True, "records": [], "totalSize": 0}),
        "SecurityHealthCheck": (500, {"message": "Internal Server Error"}),
    })
    session = _mock_session()
    with pytest.raises(RuntimeError):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            execute(session, publish_path, _ALIAS, tmp_path / "temp", log, get_fn=get_fn)

    # Prior sentinel must be untouched
    assert sentinel_before.read_text(encoding="utf-8") == "prior"


def test_execute_pagination(tmp_path):
    """Risks spanning nextRecordsUrl are collected correctly."""
    page1_risks = [_RISKS[0]]
    page2_risks = [_RISKS[1]]

    def _get(url, **kwargs):
        r = MagicMock()
        r.status_code = 200
        if "MORE" in url:
            r.json.return_value = {"done": True, "records": page2_risks, "totalSize": 2}
        elif "SecurityHealthCheckRisks" in url:
            r.json.return_value = {
                "done": False,
                "records": page1_risks,
                "nextRecordsUrl": "/services/data/v99.0/tooling/query/MORE",
                "totalSize": 2,
            }
        elif "SecurityHealthCheck" in url:
            r.json.return_value = {"done": True, "records": [_SHC_ROW], "totalSize": 1}
        else:
            raise AssertionError(f"Unexpected URL: {url}")
        r.text = "{}"
        return r

    session = _mock_session()
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
        execute(session, publish_path, _ALIAS, tmp_path / "temp", log, get_fn=_get)

    data = json.loads((publish_path / sentinel_name(_ALIAS)).read_text(encoding="utf-8"))
    assert data["risk_count"] == 2
    assert len(data["Risks"]) == 2
