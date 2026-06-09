import pytest

from sf_clean_room.eventlog_classify import DERIVE, DROP, PASS, RAW
from sf_clean_room.eventlog_plan import EventLogPlanError, load_plan, resolve


def test_no_plan_uses_classifier_default():
    eff = resolve("CLIENT_IP", None)
    assert eff.action == DERIVE and eff.source == "default"
    assert resolve("USER_ID", None).action == RAW


def test_override_more_restrictive_is_allowed(tmp_path):
    p = tmp_path / "plan.toml"
    p.write_text('[overrides]\nCOUNTRY_CODE = "DROP"\n', encoding="utf-8")
    plan = load_plan(p)
    eff = resolve("COUNTRY_CODE", plan)
    assert eff.action == DROP and eff.source == "override" and not eff.downgraded


def test_exposing_override_without_reason_downgrades(tmp_path):
    # Keeping a DROP content column (QUERY) is more-exposing -> needs a reason.
    p = tmp_path / "plan.toml"
    p.write_text('[overrides]\nQUERY = "KEEP"\n', encoding="utf-8")
    plan = load_plan(p)
    eff = resolve("QUERY", plan)
    assert eff.action == DROP and eff.downgraded is True


def test_exposing_override_with_reason_retained(tmp_path):
    p = tmp_path / "plan.toml"
    p.write_text(
        '[overrides]\nQUERY = "KEEP"\n[reasons]\nQUERY = "security investigation, authorised"\n',
        encoding="utf-8",
    )
    plan = load_plan(p)
    eff = resolve("QUERY", plan)
    assert eff.action == PASS and eff.downgraded is False


def test_exposing_ip_override_needs_reason(tmp_path):
    # DERIVE -> PASS exposes the raw IP; needs justification.
    p = tmp_path / "plan.toml"
    p.write_text('[overrides]\nCLIENT_IP = "PASS"\n', encoding="utf-8")
    plan = load_plan(p)
    eff = resolve("CLIENT_IP", plan)
    assert eff.action == DERIVE and eff.downgraded is True


def test_invalid_action_rejected(tmp_path):
    p = tmp_path / "plan.toml"
    p.write_text('[overrides]\nQUERY = "OBLITERATE"\n', encoding="utf-8")
    with pytest.raises(EventLogPlanError):
        load_plan(p)


def test_scope_event_types(tmp_path):
    p = tmp_path / "plan.toml"
    p.write_text('[scope]\nevent_types = ["Login", "ReportExport"]\n', encoding="utf-8")
    assert load_plan(p).event_types == ["Login", "ReportExport"]
