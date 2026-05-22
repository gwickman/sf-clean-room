from sf_clean_room.constants import (
    DENY,
    OPERATIONAL_DENY,
    SENSITIVITY_DENY,
    TYPE_WEIGHTS,
    weight_for,
)


def test_sensitive_types_are_denied():
    expected = {
        "ConnectedApp",
        "AuthProvider",
        "NamedCredential",
        "ExternalCredential",
        "CustomMetadata",
        "Document",
        "StaticResource",
        "ContentAsset",
    }
    assert expected.issubset(SENSITIVITY_DENY)


def test_operational_exclusions_present():
    for t in ("Profile", "PermissionSet", "Role", "Certificate", "SamlSsoConfig"):
        assert t in OPERATIONAL_DENY


def test_deny_is_union():
    assert DENY == OPERATIONAL_DENY | SENSITIVITY_DENY


def test_heavy_types_have_explicit_weights():
    for t in ("Document", "StaticResource", "ContentAsset", "ExperienceBundle"):
        assert TYPE_WEIGHTS.get(t, 1) >= 100


def test_unknown_type_falls_back_to_default_weight():
    assert weight_for("ApexClass") == 1
    assert weight_for("SomeBrandNewType_That_Does_Not_Exist") == 1


def test_known_type_uses_table_weight():
    assert weight_for("LightningComponentBundle") == TYPE_WEIGHTS["LightningComponentBundle"]
