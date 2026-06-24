"""Tests for technical_download.py — injected HTTP stubs, no live networking."""
import json
from unittest.mock import MagicMock

import pytest
import requests

from sf_clean_room.technical_classify import FieldMeta
from sf_clean_room.technical_download import (
    TechnicalDownloadError,
    describe_fields,
    fetch_limits,
    fetch_recordcount,
    page_entitydefinition,
    page_soql,
    query_tooling,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session(instance_url="https://test.salesforce.com"):
    s = MagicMock()
    s.session_id = "TOKEN"
    s.instance_url = instance_url
    return s


def _response(status: int, body) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(body).encode()
    return r


def _make_get_fn(url_map: dict):
    """Return a get_fn that matches URLs by substring."""
    def _get(url, **kwargs):
        for key, resp in url_map.items():
            if key in url:
                return resp
        raise AssertionError(f"Unexpected URL: {url}")
    return _get


# ---------------------------------------------------------------------------
# describe_fields
# ---------------------------------------------------------------------------

def test_describe_fields_soql_strips_layer0():
    fields_payload = [
        {"name": "Id",          "type": "id",       "queryable": True},
        {"name": "Name",        "type": "string",   "queryable": True},
        {"name": "Body",        "type": "string",   "queryable": True},   # Layer-0 name skip
        {"name": "Blob",        "type": "base64",   "queryable": True},   # Layer-0 type skip
        {"name": "Addr",        "type": "address",  "queryable": True},   # Layer-0 type skip
        {"name": "NotQ",        "type": "string",   "queryable": False},  # not queryable
    ]
    get_fn = _make_get_fn({"/describe": _response(200, {"fields": fields_payload})})
    result = describe_fields(_session(), "SomeObj", "soql", get_fn)
    names = [f.name for f in result]
    assert names == ["Id", "Name"]


def test_describe_fields_tooling_uses_tooling_endpoint():
    captured = {}
    def _get(url, **kwargs):
        captured["url"] = url
        return _response(200, {"fields": [{"name": "Id", "type": "id", "queryable": True}]})
    describe_fields(_session(), "ApexClass", "tooling", _get)
    assert "/tooling/sobjects/" in captured["url"]


def test_describe_fields_raises_on_http_error():
    get_fn = _make_get_fn({"/describe": _response(403, {"message": "forbidden"})})
    with pytest.raises(TechnicalDownloadError, match="403"):
        describe_fields(_session(), "ApexClass", "tooling", get_fn)


def test_describe_fields_raises_when_no_safe_fields():
    get_fn = _make_get_fn({"/describe": _response(200, {"fields": [
        {"name": "Body", "type": "string", "queryable": True},  # Layer-0 name skip
    ]})})
    with pytest.raises(TechnicalDownloadError, match="no safe queryable fields"):
        describe_fields(_session(), "ApexClass", "tooling", get_fn)


# ---------------------------------------------------------------------------
# page_soql — queryMore
# ---------------------------------------------------------------------------

def test_page_soql_follows_querymore():
    page1 = {
        "records": [{"Id": "001", "Name": "A"}],
        "done": False,
        "nextRecordsUrl": "/query/next",
    }
    page2 = {
        "records": [{"Id": "002", "Name": "B"}],
        "done": True,
    }
    def _get(url, **kwargs):
        if "nextRecordsUrl" in url or "/query/next" in url:
            return _response(200, page2)
        return _response(200, page1)
    records = list(page_soql(_session(), "SELECT Id, Name FROM Foo", get_fn=_get))
    assert len(records) == 2
    assert records[0]["Id"] == "001"
    assert records[1]["Id"] == "002"


def test_page_soql_strips_attributes():
    page = {
        "records": [{"attributes": {"type": "Foo"}, "Id": "001"}],
        "done": True,
    }
    get_fn = lambda url, **kw: _response(200, page)
    records = list(page_soql(_session(), "SELECT Id FROM Foo", get_fn=get_fn))
    assert "attributes" not in records[0]


def test_page_soql_respects_limit():
    page = {
        "records": [{"Id": str(i)} for i in range(10)],
        "done": True,
    }
    get_fn = lambda url, **kw: _response(200, page)
    records = list(page_soql(_session(), "SELECT Id FROM Foo", limit=3, get_fn=get_fn))
    assert len(records) == 3


def test_page_soql_raises_on_http_error():
    get_fn = lambda url, **kw: _response(401, [{"errorCode": "INVALID_SESSION_ID"}])
    with pytest.raises(TechnicalDownloadError, match="401"):
        list(page_soql(_session(), "SELECT Id FROM Foo", get_fn=get_fn))


# ---------------------------------------------------------------------------
# query_tooling
# ---------------------------------------------------------------------------

def test_query_tooling_follows_querymore():
    page1 = {"records": [{"Id": "T01"}], "done": False, "nextRecordsUrl": "/tooling/query/next"}
    page2 = {"records": [{"Id": "T02"}], "done": True}
    def _get(url, **kwargs):
        if "query/next" in url:
            return _response(200, page2)
        return _response(200, page1)
    records = query_tooling(_session(), "SELECT Id FROM ApexClass", get_fn=_get)
    assert [r["Id"] for r in records] == ["T01", "T02"]


def test_query_tooling_strips_attributes():
    page = {"records": [{"attributes": {"type": "ApexClass"}, "Id": "T01"}], "done": True}
    get_fn = lambda url, **kw: _response(200, page)
    records = query_tooling(_session(), "SELECT Id FROM ApexClass", get_fn=get_fn)
    assert "attributes" not in records[0]


def test_query_tooling_respects_limit():
    page = {"records": [{"Id": str(i)} for i in range(20)], "done": True}
    get_fn = lambda url, **kw: _response(200, page)
    records = query_tooling(_session(), "SELECT Id FROM ApexClass", limit=5, get_fn=get_fn)
    assert len(records) == 5


# ---------------------------------------------------------------------------
# page_entitydefinition — keyset pagination
# ---------------------------------------------------------------------------

def test_entitydef_keyset_terminates():
    calls = []
    def _get(url, **kwargs):
        calls.append(url)
        # First call: 3 records (less than batch=2000 -> no more pages).
        return _response(200, {
            "records": [
                {"QualifiedApiName": "Account"},
                {"QualifiedApiName": "Contact"},
                {"QualifiedApiName": "Lead"},
            ],
            "done": True,
        })
    fields = [FieldMeta("QualifiedApiName", "string")]
    records = list(page_entitydefinition(_session(), fields, get_fn=_get))
    assert [r["QualifiedApiName"] for r in records] == ["Account", "Contact", "Lead"]
    assert len(calls) == 1


def test_entitydef_keyset_uses_last_value():
    """Second page query must use WHERE QualifiedApiName > 'Lead'."""
    pages = [
        # First page: exactly 2000 records (triggers next page).
        {"records": [{"QualifiedApiName": f"Obj{i:04d}"} for i in range(2000)], "done": True},
        # Second page: 1 record (stops pagination).
        {"records": [{"QualifiedApiName": "ZZZFinal"}], "done": True},
    ]
    call_count = [0]
    captured_soqls = []
    def _get(url, **kwargs):
        captured_soqls.append(url)
        r = pages[call_count[0]]
        call_count[0] += 1
        return _response(200, r)
    fields = [FieldMeta("QualifiedApiName", "string")]
    records = list(page_entitydefinition(_session(), fields, get_fn=_get))
    assert len(records) == 2001
    # Second SOQL should have WHERE > last first-page value.
    assert "Obj1999" in captured_soqls[1]


def test_entitydef_raises_when_no_qualified_api_name():
    fields = [FieldMeta("Name", "string")]  # no QualifiedApiName
    get_fn = lambda url, **kw: _response(200, {"records": [], "done": True})
    with pytest.raises(TechnicalDownloadError, match="QualifiedApiName"):
        list(page_entitydefinition(_session(), fields, get_fn=get_fn))


def test_entitydef_strips_attributes():
    page = {"records": [{"attributes": {"type": "EntityDefinition"}, "QualifiedApiName": "Account"}], "done": True}
    get_fn = lambda url, **kw: _response(200, page)
    fields = [FieldMeta("QualifiedApiName", "string")]
    records = list(page_entitydefinition(_session(), fields, get_fn=get_fn))
    assert "attributes" not in records[0]


# ---------------------------------------------------------------------------
# fetch_limits / fetch_recordcount
# ---------------------------------------------------------------------------

def test_fetch_limits_parses_response():
    body = {
        "DailyApiRequests": {"Max": 15000, "Remaining": 14000},
        "DataStorageMB": {"Max": 5, "Remaining": 3},
    }
    get_fn = lambda url, **kw: _response(200, body)
    rows = fetch_limits(_session(), get_fn)
    names = {r["LimitName"] for r in rows}
    assert names == {"DailyApiRequests", "DataStorageMB"}
    by_name = {r["LimitName"]: r for r in rows}
    assert by_name["DailyApiRequests"]["Max"] == 15000
    assert by_name["DailyApiRequests"]["Remaining"] == 14000


def test_fetch_limits_ignores_non_dict_values():
    body = {"SomeFlag": True, "DailyApiRequests": {"Max": 100, "Remaining": 50}}
    get_fn = lambda url, **kw: _response(200, body)
    rows = fetch_limits(_session(), get_fn)
    assert len(rows) == 1  # SomeFlag is not a dict


def test_fetch_recordcount_parses_response():
    body = {"sObjects": [
        {"name": "Account", "count": 1234},
        {"name": "Contact", "count": 567},
    ]}
    get_fn = lambda url, **kw: _response(200, body)
    rows = fetch_recordcount(_session(), get_fn)
    assert len(rows) == 2
    by_name = {r["ObjectName"]: r for r in rows}
    assert by_name["Account"]["RecordCount"] == 1234


def test_fetch_limits_raises_on_http_error():
    get_fn = lambda url, **kw: _response(403, {"message": "forbidden"})
    with pytest.raises(TechnicalDownloadError, match="403"):
        fetch_limits(_session(), get_fn)


def test_fetch_recordcount_raises_on_http_error():
    get_fn = lambda url, **kw: _response(403, {"message": "forbidden"})
    with pytest.raises(TechnicalDownloadError, match="403"):
        fetch_recordcount(_session(), get_fn)
