"""Tests for technical_classify.py — table-driven against the schema reference."""
import pytest

from sf_clean_room.technical_classify import (
    DERIVE,
    DROP,
    HASH,
    PASS,
    RAW,
    FieldMeta,
    classify_field,
    transform_value,
)


# ---------------------------------------------------------------------------
# Curated overrides (§3.2 of the requirements)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("obj,field,expected_action", [
    ("FlowInterview",    "InterviewLabel",    DROP),
    ("FlowInterview",    "PauseLabel",        DROP),
    ("SetupAuditTrail",  "Display",           DROP),
    ("SetupAuditTrail",  "DelegateUser",      HASH),
    ("IdpEventLog",      "IdentityUsed",      HASH),
    ("Organization",     "PrimaryContact",    DROP),
    ("AsyncApexJob",     "ExtendedStatus",    DROP),
    ("ApexTestQueueItem","ExtendedStatus",    DROP),
    ("BackgroundOperation","Error",           DROP),
    ("BackgroundOperation","ParentKey",       HASH),
    ("ApexLog",          "Status",            DROP),
    ("VerificationHistory","Remarks",         DROP),
    ("LoginHistory",     "Status",            PASS),
    ("CronTrigger",      "CronExpression",    PASS),
    ("ApexTestResult",   "Message",           DROP),
    ("ApexTestResult",   "StackTrace",        DROP),
])
def test_curated_overrides(obj, field, expected_action):
    action, _ = classify_field(obj, FieldMeta(field, "string"))
    assert action == expected_action, f"{obj}.{field} expected {expected_action}, got {action}"


# ---------------------------------------------------------------------------
# Generic Layer-1 rules
# ---------------------------------------------------------------------------

def test_id_type_is_raw():
    action, _ = classify_field("LoginHistory", FieldMeta("Id", "id"))
    assert action == RAW


def test_reference_type_is_raw():
    action, _ = classify_field("LoginHistory", FieldMeta("UserId", "reference"))
    assert action == RAW


def test_field_ending_in_id_is_raw():
    action, _ = classify_field("AuthSession", FieldMeta("UsersId", "string"))
    assert action == RAW


def test_email_type_is_hashed():
    action, recipe = classify_field("Group", FieldMeta("Email", "email"))
    assert action == HASH
    assert recipe == "email"


def test_email_named_string_is_hashed():
    action, recipe = classify_field("SomeObject", FieldMeta("NotificationEmail", "string"))
    assert action == HASH
    assert recipe == "email"


def test_email_named_boolean_not_hashed():
    # type=boolean is not text-bearing → should not trigger email rule
    action, _ = classify_field("Contact", FieldMeta("HasOptedOutOfEmail", "boolean"))
    assert action == PASS


def test_ip_named_field_is_derived():
    action, recipe = classify_field("LoginHistory", FieldMeta("SourceIp", "string"))
    assert action == DERIVE
    assert recipe == "ip_prefix"


def test_field_ending_in_ip_is_derived():
    action, recipe = classify_field("AuthSession", FieldMeta("ClientIp", "string"))
    assert action == DERIVE
    assert recipe == "ip_prefix"


def test_phone_type_is_dropped():
    action, _ = classify_field("Organization", FieldMeta("Phone", "phone"))
    assert action == DROP


def test_phone_named_field_is_dropped():
    action, _ = classify_field("SomeObj", FieldMeta("MobilePhone", "string"))
    assert action == DROP


def test_url_type_is_derived():
    action, recipe = classify_field("AuthSession", FieldMeta("LoginUrl", "url"))
    assert action == DERIVE
    assert recipe == "url_sanitise"


def test_url_named_field_is_derived():
    action, recipe = classify_field("AuthSession", FieldMeta("LogoutUrl", "string"))
    assert action == DERIVE
    assert recipe == "url_sanitise"


# LoginGeo latitude/longitude/city/postalcode → DROP; country/subdivision → PASS
@pytest.mark.parametrize("field,expected_action", [
    ("Latitude",       DROP),
    ("Longitude",      DROP),
    ("City",           DROP),
    ("PostalCode",     DROP),
    ("Country",        PASS),
    ("CountryIso",     PASS),
    ("CountryCode",    PASS),
    ("Subdivision",    PASS),
])
def test_login_geo_fields(field, expected_action):
    action, _ = classify_field("LoginGeo", FieldMeta(field, "string"))
    assert action == expected_action, f"LoginGeo.{field}: expected {expected_action}, got {action}"


def test_free_text_echo_description_is_dropped():
    action, _ = classify_field("PermissionSet", FieldMeta("Description", "string"))
    assert action == DROP


def test_free_text_echo_error_is_dropped():
    action, _ = classify_field("SomeObj", FieldMeta("SomeError", "string"))
    assert action == DROP


def test_permission_bit_is_passed():
    action, _ = classify_field("PermissionSet", FieldMeta("PermissionsModifyAllData", "boolean"))
    assert action == PASS


def test_unknown_safe_field_is_passed():
    action, _ = classify_field("ApexClass", FieldMeta("ApiVersion", "double"))
    assert action == PASS


def test_status_picklist_generic_is_passed():
    action, _ = classify_field("ApexClass", FieldMeta("Status", "picklist"))
    assert action == PASS


# ---------------------------------------------------------------------------
# transform_value
# ---------------------------------------------------------------------------

def test_transform_raw_returns_value():
    assert transform_value(RAW, "", "abc") == "abc"


def test_transform_pass_returns_value():
    assert transform_value(PASS, "", "hello") == "hello"


def test_transform_drop_returns_empty():
    assert transform_value(DROP, "", "sensitive") == ""


def test_transform_hash_email():
    import hashlib
    v = "user@example.com"
    expected = hashlib.sha256(v.encode()).hexdigest()
    assert transform_value(HASH, "email", v) == expected


def test_transform_hash_id():
    import hashlib
    v = "0050X000001abc"
    expected = hashlib.sha256(v.encode()).hexdigest()
    assert transform_value(HASH, "id", v) == expected


def test_transform_derive_ip_prefix_v4():
    assert transform_value(DERIVE, "ip_prefix", "192.168.1.42") == "192.168.1.0"


def test_transform_derive_url_sanitise():
    assert transform_value(DERIVE, "url_sanitise", "https://example.com/path?q=1") == "https://example.com/path"


def test_transform_none_value():
    assert transform_value(PASS, "", None) == ""
    assert transform_value(RAW, "", None) == ""
    assert transform_value(HASH, "id", None) == ""
    assert transform_value(DERIVE, "ip_prefix", None) == ""


def test_transform_handles_non_string_scalar():
    assert transform_value(PASS, "", 42) == "42"
    assert transform_value(PASS, "", True) == "True"
