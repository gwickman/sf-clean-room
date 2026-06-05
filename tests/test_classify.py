import pytest

from sf_clean_room.classify import FieldMeta, classify_field
from sf_clean_room.constants import (
    DROP,
    HASH_EMAIL,
    HASH_ID,
    PASS,
    RAW,
)


def fm(name, type="string", length=0, label="", calculated=False, formula="", help_text=""):
    return FieldMeta(
        name=name, label=label, type=type, length=length,
        calculated=calculated, formula=formula, help_text=help_text,
    )


@pytest.mark.parametrize("meta,expected", [
    # RAW: ids and references.
    (fm("Id", type="id"), RAW),
    (fm("AccountId", type="reference"), RAW),
    (fm("OwnerId", type="reference"), RAW),
    (fm("Jigsaw"), RAW),
    # Direct PII.
    (fm("FirstName"), DROP),
    (fm("LastName"), DROP),
    (fm("Name"), DROP),
    (fm("MailingStreet"), DROP),
    (fm("Home_Phone__c", type="phone"), DROP),
    (fm("Birthdate", type="date"), DROP),
    (fm("PhotoUrl", type="url"), DROP),
    (fm("LinkedIn_Profile__c"), DROP),
    # Email.
    (fm("Email", type="email"), HASH_EMAIL),
    (fm("Personal_Email__c"), HASH_EMAIL),
    # Identifiers.
    (fm("Membership_Number__c"), HASH_ID),
    (fm("Website_ID__c"), HASH_ID),
    (fm("Passport_Number__c"), HASH_ID),
    # Analytical signal -> PASS.
    (fm("Industry", type="picklist"), PASS),
    (fm("AnnualRevenue", type="currency"), PASS),
    (fm("IsActive", type="boolean"), PASS),
    (fm("CreatedDate", type="datetime"), PASS),
])
def test_action(meta, expected):
    assert classify_field(meta).action == expected


def test_special_category_tagged_and_dropped():
    for name in ("Ethnicity__c", "Gender__c", "Disability__c", "Nationality__c", "Religion__c"):
        rec = classify_field(fm(name, type="picklist"))
        assert rec.action == DROP
        assert rec.special_category is True


def test_special_category_checked_before_other_rules():
    # A picklist named for ethnicity is special-category, not PASS.
    assert classify_field(fm("Ethnic_Group__c", type="picklist")).special_category is True


def test_long_textarea_is_dropped():
    assert classify_field(fm("Comments__c", type="textarea", length=40000)).action == DROP


def test_named_essay_dropped_only_when_long():
    assert classify_field(fm("Member_Notes__c", type="textarea", length=2000)).action == DROP
    # Short note-shaped field is not an essay; 'note' is not itself a PII pattern.
    assert classify_field(fm("Quick_Note__c", type="string", length=80)).action == PASS


def test_formula_leak_detected():
    rec = classify_field(fm(
        "Contact_Name_Text__c", type="string", calculated=True,
        formula="Contact.FirstName & ' ' & Contact.LastName",
    ))
    assert rec.action == DROP
    assert "formula" in rec.reason.lower()


def test_calculated_without_pii_source_passes():
    rec = classify_field(fm(
        "Total__c", type="currency", calculated=True, formula="Amount__c * 2",
    ))
    assert rec.action == PASS


def test_email_named_non_text_fields_are_not_hashed():
    # Boolean/date/number fields that merely mention 'email' keep their value;
    # only text-bearing (or true email-type) fields are hashed.
    assert classify_field(fm("HasOptedOutOfEmail", type="boolean")).action == PASS
    assert classify_field(fm("IsEmailBounced", type="boolean")).action == PASS
    assert classify_field(fm("EmailBouncedDate", type="datetime")).action == PASS
    # A genuine text email field is still hashed.
    assert classify_field(fm("Secondary_Email__c", type="string")).action == HASH_EMAIL


def test_email_type_without_email_name_still_hash_email_with_note():
    rec = classify_field(fm("Contact_Point__c", type="email"))
    assert rec.action == HASH_EMAIL
    assert "name lacks" in rec.reason


def test_conservative_fallback_drops_pii_shaped_unmatched_field():
    # Matches a PII pattern (address) but no earlier rule fired on type.
    rec = classify_field(fm("Delivery_Address_Ref__c", type="string"))
    assert rec.action == DROP


def test_reference_beats_pii_name():
    # A reference field is RAW even if its name contains a PII-ish token.
    assert classify_field(fm("Primary_Address_Lookup__c", type="reference")).action == RAW


def test_label_and_helptext_are_searched():
    rec = classify_field(fm("X1__c", type="string", label="Mobile Phone"))
    assert rec.action == DROP
    rec2 = classify_field(fm("X2__c", type="string", help_text="the member's email for login"))
    assert rec2.action == HASH_EMAIL
