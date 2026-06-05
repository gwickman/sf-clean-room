import pytest

from sf_clean_room.classify import FieldMeta, classify_field
from sf_clean_room.constants import DROP, HASH_ID, PASS, RAW
from sf_clean_room.plan import PlanError, emit_plan, load_plan, resolve
from sf_clean_room.schema_scan import ScannedField


def scanned(obj, name, **kw):
    meta = FieldMeta(name=name, type=kw.get("type", "string"), length=kw.get("length", 0),
                     label=kw.get("label", ""), calculated=kw.get("calculated", False),
                     formula=kw.get("formula", ""))
    return ScannedField(obj, meta, classify_field(meta))


def make_scan():
    return {
        "Account": [
            scanned("Account", "Id", type="id"),
            scanned("Account", "Industry", type="picklist"),
            scanned("Account", "Ethnicity__c", type="picklist"),
            scanned("Account", "Notes__c", type="textarea", length=40000),
        ]
    }


def test_emit_then_load_roundtrip(tmp_path):
    scan = make_scan()
    text = emit_plan(scan)
    p = tmp_path / "plan.toml"
    p.write_text(text, encoding="utf-8")
    plan = load_plan(p)
    assert plan.objects == ["Account"]
    # known_fields captured for drift detection.
    assert plan.is_known("Account", "Id")
    assert plan.is_known("Account", "Ethnicity__c")
    # No overrides by default.
    assert plan.override_for("Account", "Industry") is None


def test_default_resolution_uses_recommendation():
    scan = make_scan()["Account"]
    eff = resolve("Account", scan[0], None)  # Id
    assert eff.action == RAW and eff.source == "default"


def test_override_keep_resolves_to_pass(tmp_path):
    p = tmp_path / "plan.toml"
    p.write_text(
        '[scope]\nobjects=["Account"]\n[overrides.Account]\nNotes__c="KEEP"\n',
        encoding="utf-8",
    )
    plan = load_plan(p)
    notes = scanned("Account", "Notes__c", type="textarea", length=40000)
    eff = resolve("Account", notes, plan)
    assert eff.action == PASS and eff.source == "override"


def test_override_to_explicit_action(tmp_path):
    p = tmp_path / "plan.toml"
    p.write_text(
        '[scope]\nobjects=["Account"]\n[overrides.Account]\nIndustry="HASH_ID"\n',
        encoding="utf-8",
    )
    plan = load_plan(p)
    industry = scanned("Account", "Industry", type="picklist")
    assert resolve("Account", industry, plan).action == HASH_ID


def test_special_category_keep_without_reason_downgrades(tmp_path):
    p = tmp_path / "plan.toml"
    p.write_text(
        '[scope]\nobjects=["Account"]\n[overrides.Account]\nEthnicity__c="KEEP"\n',
        encoding="utf-8",
    )
    plan = load_plan(p)
    eth = scanned("Account", "Ethnicity__c", type="picklist")
    eff = resolve("Account", eth, plan)
    assert eff.action == DROP
    assert eff.downgraded is True


def test_special_category_keep_with_reason_retained(tmp_path):
    p = tmp_path / "plan.toml"
    p.write_text(
        '[scope]\nobjects=["Account"]\n'
        '[overrides.Account]\nEthnicity__c="KEEP"\n'
        '[reasons.Account]\nEthnicity__c="lawful basis confirmed by user"\n',
        encoding="utf-8",
    )
    plan = load_plan(p)
    eth = scanned("Account", "Ethnicity__c", type="picklist")
    eff = resolve("Account", eth, plan)
    assert eff.action == PASS
    assert eff.downgraded is False
    assert "justified" in eff.reason


def test_invalid_action_rejected(tmp_path):
    p = tmp_path / "plan.toml"
    p.write_text('[overrides.Account]\nIndustry="OBLITERATE"\n', encoding="utf-8")
    with pytest.raises(PlanError):
        load_plan(p)


def test_drift_field_not_in_known(tmp_path):
    p = tmp_path / "plan.toml"
    p.write_text(
        '[scope]\nobjects=["Account"]\n[known_fields]\nAccount=["Id"]\n',
        encoding="utf-8",
    )
    plan = load_plan(p)
    assert plan.is_known("Account", "Id") is True
    assert plan.is_known("Account", "New_Field__c") is False
