import csv

import pytest

from sf_clean_room.audit import audit_log
from sf_clean_room.pipeline import make_run_paths
from sf_clean_room.publish import PublishError, publish
from sf_clean_room.records_extract import AUDIT_SENTINEL
from sf_clean_room.records_pipeline import RecordsRequest, dry_run, execute, resolve_scope
from sf_clean_room.session import Session

ACCOUNT_FIELDS = [
    {"name": "Id", "type": "id", "length": 18},
    {"name": "Name", "type": "string", "length": 255},
    {"name": "Industry", "type": "picklist", "length": 40},
    {"name": "Email", "type": "email", "length": 80},
    {"name": "Ethnicity__c", "type": "picklist", "length": 40, "custom": True},
]


def fake_describe(_alias, _obj):
    return ACCOUNT_FIELDS


def fake_query(_alias, soql):
    if "LIMIT 1" in soql:  # probe
        return []
    return [{"Id": "001", "Industry": "Tech", "Email": "a@b.com", "Name": "Acme", "Ethnicity__c": "X"}]


def a_session(alias="testorg"):
    return Session(
        session_id="tok", instance_url="https://example.my.salesforce.com",
        org_id="00Dxx", username="u@e.com", alias=alias, api_version="61.0",
    )


# ---- resolve_scope ----

def test_resolve_scope_from_only():
    assert resolve_scope(["Account", "Contact", "Account"], None) == ["Account", "Contact"]


def test_resolve_scope_requires_objects():
    with pytest.raises(ValueError):
        resolve_scope(None, None)


# ---- dry_run ----

def test_dry_run_emits_plan(tmp_path, log_to):
    plan_file = tmp_path / "plan.toml"
    with log_to() as log:
        text = dry_run(a_session(), ["Account"], plan_file, log, describe_fn=fake_describe)
    assert "[scope]" in text
    assert "Account" in text
    assert plan_file.exists()
    assert "Ethnicity__c" in plan_file.read_text(encoding="utf-8")


# ---- execute (full publish) ----

def test_execute_publishes_with_sentinel_and_no_drop_leak(tmp_path, log_to):
    paths = make_run_paths(tmp_path / "temp", tmp_path / "out", "testorg")
    req = RecordsRequest(objects=["Account"], where=None, plan_path=None, dry_run=False)
    with log_to() as log:
        execute(a_session(), req, paths, log, describe_fn=fake_describe, query_fn=fake_query)

    pub = paths.publish_path
    # Sentinel + expected artefacts present.
    assert (pub / AUDIT_SENTINEL).exists()
    assert (pub / "_schema-scan.csv").exists()
    assert (pub / "_capability-probe.json").exists()
    assert (pub / "_extract-summary.json").exists()
    assert (pub / "Account.tsv").exists()

    rows = list(csv.reader(open(pub / "Account.tsv", encoding="utf-8"), delimiter="\t"))
    header = rows[0]
    assert "Name" not in header and "Ethnicity__c" not in header
    assert "Industry" in header and "Id" in header
    # No raw PII anywhere in the published TSV.
    blob = (pub / "Account.tsv").read_text(encoding="utf-8")
    assert "Acme" not in blob and "a@b.com" not in blob

    # Temp dir cleaned up after successful publish.
    assert not paths.run_temp_dir.exists()


def test_execute_where_requires_only_is_validated(tmp_path, log_to):
    paths = make_run_paths(tmp_path / "temp", tmp_path / "out", "testorg")
    # invalid where -> abort before any publish
    req = RecordsRequest(objects=["Account"], where="Id=1; DROP", plan_path=None, dry_run=False)
    with log_to() as log:
        with pytest.raises(Exception):
            execute(a_session(), req, paths, log, describe_fn=fake_describe, query_fn=fake_query)
    assert not (paths.publish_path / AUDIT_SENTINEL).exists()


# ---- publish sentinel generalisation ----

def test_publish_moves_custom_sentinel_and_requires_it(tmp_path):
    temp = tmp_path / "t"
    temp.mkdir()
    (temp / "Account.tsv").write_text("Id\n", encoding="utf-8")
    (temp / AUDIT_SENTINEL).write_text("object,field\n", encoding="utf-8")
    out = tmp_path / "out"
    publish(temp, out, sentinel_name=AUDIT_SENTINEL)
    assert (out / AUDIT_SENTINEL).exists()
    assert (out / "Account.tsv").exists()


def test_publish_refuses_without_sentinel(tmp_path):
    temp = tmp_path / "t"
    temp.mkdir()
    (temp / "Account.tsv").write_text("Id\n", encoding="utf-8")
    with pytest.raises(PublishError):
        publish(temp, tmp_path / "out", sentinel_name=AUDIT_SENTINEL)
