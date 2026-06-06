import csv

import pytest

from sf_clean_room.skip_log import CSV_HEADER, SkipLog


def test_bucket_must_be_valid():
    log = SkipLog()
    with pytest.raises(ValueError):
        log.add(type="X", bucket="not_a_bucket")


def test_published_csv_header_has_no_detail_column(tmp_path):
    log = SkipLog()
    log.add(type="DecisionTable", bucket="insufficient_access", detail="secret server message")
    p = tmp_path / "_skipped-types.csv"
    log.write_csv(p)
    rows = list(csv.reader(open(p, encoding="utf-8")))
    assert tuple(rows[0]) == CSV_HEADER
    assert "detail" not in rows[0]
    # The verbatim detail must NOT appear anywhere in the published file.
    assert "secret server message" not in p.read_text(encoding="utf-8")


def test_detail_is_in_audit_lines_only():
    log = SkipLog()
    log.add(type="DecisionTable", bucket="insufficient_access", detail="you don't have access")
    joined = "\n".join(log.audit_lines())
    assert "you don't have access" in joined


def test_empty_log_writes_header_only(tmp_path):
    p = tmp_path / "_skipped-types.csv"
    SkipLog().write_csv(p)
    rows = list(csv.reader(open(p, encoding="utf-8")))
    assert len(rows) == 1 and tuple(rows[0]) == CSV_HEADER


def test_partial_retrieve_counts_only_on_partial_rows(tmp_path):
    log = SkipLog()
    log.add(type="ApexClass", bucket="invalid_type", detail="x")
    log.add(type="Report", bucket="partial_retrieve", requested=10, retrieved=3)
    p = tmp_path / "s.csv"
    log.write_csv(p)
    rows = {r["type"]: r for r in csv.DictReader(open(p, encoding="utf-8"))}
    assert rows["ApexClass"]["components_requested"] == ""
    assert rows["Report"]["components_requested"] == "10"
    assert rows["Report"]["components_retrieved"] == "3"


def test_detail_truncated():
    log = SkipLog()
    log.add(type="X", bucket="unknown", detail="z" * 5000)
    rec = next(iter(log))
    assert len(rec.detail) <= 404 and rec.detail.endswith("...")


def test_bucket_counts():
    log = SkipLog()
    log.add(type="A", bucket="invalid_type")
    log.add(type="B", bucket="invalid_type")
    log.add(type="C", bucket="insufficient_access")
    assert log.bucket_counts() == {"invalid_type": 2, "insufficient_access": 1}
