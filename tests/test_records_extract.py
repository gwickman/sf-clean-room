import csv
import json

import pytest

from sf_clean_room.hashing import hash_email, hash_id
from sf_clean_room.records_extract import (
    AUDIT_SENTINEL,
    SUMMARY_NAME,
    ExtractError,
    WhereError,
    build_soql,
    extract_object,
    transform_value,
    validate_where,
    write_audit_csv,
    write_summary_json,
)
from sf_clean_room.schema_scan import scan_objects

ACCOUNT_FIELDS = [
    {"name": "Id", "type": "id", "label": "Account ID", "length": 18},
    {"name": "Name", "type": "string", "label": "Account Name", "length": 255},
    {"name": "OwnerId", "type": "reference", "label": "Owner ID", "length": 18},
    {"name": "Phone", "type": "phone", "label": "Phone", "length": 40},
    {"name": "Industry", "type": "picklist", "label": "Industry", "length": 40},
    {"name": "AnnualRevenue", "type": "currency", "label": "Annual Revenue", "length": 0},
    {"name": "Website_ID__c", "type": "string", "label": "Website ID", "length": 50, "custom": True},
    {"name": "Contact_Email__c", "type": "email", "label": "Contact Email", "length": 80, "custom": True},
    {"name": "Ethnicity__c", "type": "picklist", "label": "Ethnicity", "length": 40, "custom": True},
]


def fake_describe(_alias, _obj):
    return ACCOUNT_FIELDS


# ---- validate_where ----

@pytest.mark.parametrize("bad", [
    "", "   ",
    "Id = '1'; DROP TABLE x",
    "Id = '1' -- comment",
    "Id = '1' /* c */",
    "DELETE FROM Account",
    "Name != null UPDATE",
    "Id != null LIMIT 5",
    "Id != null OFFSET 5",
])
def test_validate_where_rejects(bad):
    with pytest.raises(WhereError):
        validate_where(bad)


def test_validate_where_accepts_and_strips():
    assert validate_where("  CreatedDate = THIS_YEAR ") == "CreatedDate = THIS_YEAR"


# ---- build_soql ----

def test_build_soql_projects_and_appends_where():
    s = build_soql("Account", ["Id", "Industry"], "Industry = 'Tech'")
    assert s == "SELECT Id, Industry FROM Account WHERE Industry = 'Tech'"


def test_build_soql_defaults_to_id_when_empty():
    assert build_soql("Account", [], None) == "SELECT Id FROM Account"


def test_build_soql_length_ceiling():
    fields = [f"Very_Long_Field_Name_{i}__c" for i in range(5000)]
    with pytest.raises(ExtractError):
        build_soql("Account", fields, None)


# ---- transform_value ----

def test_transform_hash_and_passthrough():
    assert transform_value("HASH_EMAIL", "A@B.com", "Email") == hash_email("A@B.com")
    assert transform_value("HASH_ID", "WID1", "Website_ID__c") == hash_id("WID1")
    assert transform_value("PASS", "Tech", "Industry") == "Tech"
    assert transform_value("RAW", "001x", "Id") == "001x"
    assert transform_value("PASS", None, "Industry") == ""


def test_transform_handles_non_string_scalars():
    # sf data query --json yields typed scalars; transform must not assume str.
    assert transform_value("PASS", True, "IsActive") == "True"
    assert transform_value("PASS", 1000, "AnnualRevenue") == "1000"
    assert transform_value("PASS", 12.5, "Score__c") == "12.5"
    assert transform_value("HASH_ID", 12345, "External_Id__c") == hash_id("12345")
    assert transform_value("HASH_EMAIL", None, "Email") == ""


def test_transform_derive_recipes():
    assert transform_value("DERIVE", "SW1A 1AA", "Postal_Code__c") == "SW1A"
    assert transform_value("DERIVE", "1990-05-01", "Date_Of_Birth__c") == "1990"


# ---- extract_object ----

def _scan_account(alias="a"):
    return scan_objects(alias, ["Account"], fake_describe)["Account"]


def test_extract_omits_drop_hashes_and_preserves(tmp_path):
    fields = _scan_account()
    records = [{
        "Id": "001x", "OwnerId": "005x", "Industry": "Tech",
        "AnnualRevenue": "1000", "Website_ID__c": "WID123",
        "Contact_Email__c": "Foo@Bar.com",
        "Name": "Acme", "Phone": "555", "Ethnicity__c": "X",
    }]
    res = extract_object("a", "Account", fields, None, None, tmp_path, lambda _a, _s: records)

    # DROP fields are not columns.
    for dropped in ("Name", "Phone", "Ethnicity__c"):
        assert dropped not in res.columns
    assert res.columns == ["Id", "OwnerId", "Industry", "AnnualRevenue", "Website_ID__c", "Contact_Email__c"]
    assert res.rows_out == 1

    rows = list(csv.reader(open(tmp_path / "Account.tsv", encoding="utf-8"), delimiter="\t"))
    header, data = rows[0], rows[1]
    row = dict(zip(header, data))
    assert row["Id"] == "001x"
    assert row["Industry"] == "Tech"
    assert row["Website_ID__c"] == hash_id("WID123")
    assert row["Contact_Email__c"] == hash_email("Foo@Bar.com")
    # Raw PII must not appear anywhere in the file.
    blob = (tmp_path / "Account.tsv").read_text(encoding="utf-8")
    assert "Acme" not in blob and "Foo@Bar.com" not in blob


def test_extract_audit_covers_all_fields(tmp_path):
    fields = _scan_account()
    res = extract_object("a", "Account", fields, None, None, tmp_path, lambda _a, _s: [])
    assert len(res.audit_rows) == len(ACCOUNT_FIELDS)
    assert res.rows_out == 0  # header-only TSV for empty result
    # action_counts sums to all fields.
    assert sum(res.action_counts.values()) == len(ACCOUNT_FIELDS)


def test_extract_tab_in_value_is_escaped(tmp_path):
    fields = _scan_account()
    records = [{"Industry": "Tech\tnology", "Id": "1", "OwnerId": "2",
                "AnnualRevenue": "1", "Website_ID__c": "w", "Contact_Email__c": "e@e.com"}]
    res = extract_object("a", "Account", fields, None, None, tmp_path, lambda _a, _s: records)
    rows = list(csv.reader(open(tmp_path / "Account.tsv", encoding="utf-8"), delimiter="\t"))
    # csv must keep the embedded tab inside one field, not split the row.
    assert len(rows) == 2
    assert dict(zip(rows[0], rows[1]))["Industry"] == "Tech\tnology"


def test_write_audit_csv_has_sentinel_and_where_row(tmp_path):
    fields = _scan_account()
    res = extract_object("a", "Account", fields, None, "Id != null", tmp_path, lambda _a, _s: [])
    write_audit_csv([res], "Id != null", tmp_path / AUDIT_SENTINEL)
    text = (tmp_path / AUDIT_SENTINEL).read_text(encoding="utf-8")
    assert "__where__" in text
    assert "Id != null" in text


def test_write_summary_json(tmp_path):
    fields = _scan_account()
    res = extract_object("a", "Account", fields, None, None, tmp_path, lambda _a, _s: [])
    write_summary_json([res], None, tmp_path / SUMMARY_NAME)
    data = json.loads((tmp_path / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert "Account" in data["objects"]
    assert data["where_clause"] is None
