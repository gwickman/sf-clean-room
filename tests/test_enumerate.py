import pytest

from sf_clean_room import enumerate_md
from sf_clean_room.soap import MetadataApiError

DESCRIBED = [
    {"xmlName": "CustomObject", "inFolder": False},
    {"xmlName": "Flow", "inFolder": False},
    {"xmlName": "DecisionTable", "inFolder": False},
    {"xmlName": "ConnectedApp", "inFolder": False},  # deny-listed
    {"xmlName": "Report", "inFolder": True},
]


def _fake_list(client, type_name, folder=None):
    if type_name == "DecisionTable":
        raise MetadataApiError("500 SOAP Fault: INSUFFICIENT_ACCESS: no access to DecisionTable")
    if type_name == "ApexClass":
        raise MetadataApiError("SOAP Fault: INVALID_TYPE: Cannot use: ApexClass in this organization")
    if type_name == "StandardValueSet":
        raise MetadataApiError("500 SOAP Fault: something unexpected")
    data = {
        ("CustomObject", None): ["Account__c", "Foo__c"],
        ("Flow", None): ["F1"],
        ("ApexTrigger", None): ["T1"],
        ("ReportFolder", None): ["FolderA"],
        ("Report", "FolderA"): ["FolderA/R1"],
        ("Report", "unfiled$public"): ["unfiled$public/R2"],
    }
    return data.get((type_name, folder), [])


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(enumerate_md, "describe_metadata", lambda client: DESCRIBED)
    monkeypatch.setattr(enumerate_md, "list_metadata", _fake_list)


def test_kept_types(patched):
    members, _ = enumerate_md.enumerate_all_members(client=None)
    assert members["CustomObject"] == ["Account__c", "Foo__c"]
    assert members["Flow"] == ["F1"]
    # Always-probe type that lists successfully even though it's not in describe.
    assert members["ApexTrigger"] == ["T1"]


def test_skip_buckets(patched):
    _, skip = enumerate_md.enumerate_all_members(client=None)
    buckets = {r.type: r.bucket for r in skip}
    assert buckets["DecisionTable"] == "insufficient_access"
    assert buckets["ApexClass"] == "invalid_type"   # always-probe, hidden, invalid
    assert buckets["StandardValueSet"] == "unknown"


def test_failed_types_not_in_members(patched):
    members, _ = enumerate_md.enumerate_all_members(client=None)
    for t in ("DecisionTable", "ApexClass", "StandardValueSet"):
        assert t not in members


def test_deny_listed_type_never_attempted(patched):
    members, skip = enumerate_md.enumerate_all_members(client=None)
    # ConnectedApp is deny-listed: never enumerated, never errors, never recorded.
    assert "ConnectedApp" not in members
    assert all(r.type != "ConnectedApp" for r in skip)


def test_folder_enumeration_with_synthetic_folder(patched):
    members, _ = enumerate_md.enumerate_all_members(client=None)
    # Per-folder members plus the synthetic unfiled$public folder.
    assert set(members["Report"]) == {"FolderA/R1", "unfiled$public/R2"}
    # The folder object itself is retrievable metadata.
    assert members["ReportFolder"] == ["FolderA"]


def test_describe_failure_still_aborts(monkeypatch):
    def boom(client):
        raise MetadataApiError("describeMetadata failed wholesale")
    monkeypatch.setattr(enumerate_md, "describe_metadata", boom)
    with pytest.raises(MetadataApiError):
        enumerate_md.enumerate_all_members(client=None)
