"""Source-controlled constants. The deny list is non-negotiable at runtime."""
from __future__ import annotations

from typing import Final

API_VERSION: Final[str] = "61.0"

POLL_SECS: Final[int] = 5
RETRIEVE_TIMEOUT_SECS: Final[int] = 1800

# Salesforce hard limit per retrieve is 10,000; default below for safety headroom.
MAX_COMPONENTS_PER_BATCH: Final[int] = 8000
# Weight ceiling targets Salesforce's ~600 MB compressed-zip limit per retrieve.
MAX_WEIGHT_PER_BATCH: Final[int] = 50_000

FOLDERED: Final[dict[str, str]] = {
    "Dashboard": "DashboardFolder",
    "Document": "DocumentFolder",
    "EmailTemplate": "EmailFolder",
    "Report": "ReportFolder",
}

OPERATIONAL_DENY: Final[frozenset[str]] = frozenset({
    "Profile",
    "PermissionSet",
    "PermissionSetGroup",
    "DataCategoryGroup",
    "MLDataDefinition",
    "MLPredictionDefinition",
    "Role",
    "Territory2Model",
    "Territory2",
    "Territory2Type",
    "Territory2ModelState",
    "Network",
    "CleanDataService",
    "Certificate",
    "SamlSsoConfig",
    "OauthCustomScope",
    "ExternalServiceRegistration",
})

SENSITIVITY_DENY: Final[frozenset[str]] = frozenset({
    "ConnectedApp",
    "AuthProvider",
    "NamedCredential",
    "ExternalCredential",
    "CustomMetadata",
    "Document",
    "StaticResource",
    "ContentAsset",
})

DENY: Final[frozenset[str]] = OPERATIONAL_DENY | SENSITIVITY_DENY

TYPE_WEIGHTS: Final[dict[str, int]] = {
    "Document": 100,
    "StaticResource": 100,
    "ContentAsset": 100,
    "ExperienceBundle": 500,
    "SiteDotCom": 200,
    "LightningComponentBundle": 20,
    "AuraDefinitionBundle": 15,
    "WaveApplication": 50,
    "WaveDashboard": 30,
    "WaveDataflow": 20,
    "WaveLens": 20,
    "WaveRecipe": 20,
    "Flow": 3,
    "FlowDefinition": 1,
}
DEFAULT_TYPE_WEIGHT: Final[int] = 1


def weight_for(type_name: str) -> int:
    return TYPE_WEIGHTS.get(type_name, DEFAULT_TYPE_WEIGHT)


# ---------------------------------------------------------------------------
# get_metadata v2.1 — limited-permissions resilience.
#
# Source-only, like the deny list: no CLI flag, env var, or config entry. Adding
# a type to ALWAYS_PROBE_TYPES is a maintainer change with review. See
# docs/design/03-design-2.1.md.
# ---------------------------------------------------------------------------

# Types describeMetadata may hide from identities lacking view-source perms.
# Unioned with the describeMetadata output before filtering, then enumerated;
# a type the identity also cannot list falls into the skip-and-log path.
ALWAYS_PROBE_TYPES: Final[tuple[str, ...]] = (
    "ApexClass",
    "ApexTrigger",
    "StandardValueSet",
)

# Synthetic folder names always probed for foldered types, so personal /
# unfiled-public items are captured even when not returned as a folder.
SYNTHETIC_FOLDERS: Final[dict[str, tuple[str, ...]]] = {
    "Report": ("unfiled$public",),
    "Dashboard": ("unfiled$public",),
}

# Categories a per-type failure resolves into. `registry_miss` is reserved
# (a CLI-only failure; never populated on sf-clean-room's SOAP retrieve path).
SKIP_BUCKETS: Final[tuple[str, ...]] = (
    "insufficient_access",
    "invalid_type",
    "registry_miss",
    "partial_retrieve",
    "unknown",
)

# Verbatim SOAP error detail is truncated to this before going to the audit log
# (never to the published _skipped-types.csv).
MAX_SKIP_DETAIL_LEN: Final[int] = 400


def classify_skip_bucket(message: str) -> str:
    """Map a SOAP/CLI error message to a SKIP_BUCKETS category."""
    m = (message or "").upper()
    if "INSUFFICIENT_ACCESS" in m:
        return "insufficient_access"
    if "INVALID_TYPE" in m or "CANNOT USE" in m:
        return "invalid_type"
    return "unknown"


# ---------------------------------------------------------------------------
# get_records (v2) — field-classification constants.
#
# These drive the recommendation engine in ``classify.py``. They are source
# constants (like the metadata deny list) but, unlike the deny list, they
# produce *recommendations* a reviewed plan may override (see docs/design/02-design-v2.md).
# ---------------------------------------------------------------------------

# Classifier actions.
RAW: Final[str] = "RAW"
DROP: Final[str] = "DROP"
HASH_EMAIL: Final[str] = "HASH_EMAIL"
HASH_ID: Final[str] = "HASH_ID"
PASS: Final[str] = "PASS"
DERIVE: Final[str] = "DERIVE"
KEEP: Final[str] = "KEEP"  # plan-override alias meaning "keep raw" (resolves to PASS)

CLASSIFIER_ACTIONS: Final[frozenset[str]] = frozenset(
    {RAW, DROP, HASH_EMAIL, HASH_ID, PASS, DERIVE}
)
# Actions an operator may name in a plan override.
OVERRIDE_ACTIONS: Final[frozenset[str]] = CLASSIFIER_ACTIONS | {KEEP}

# Free-text essay thresholds (characters).
ESSAY_TEXTAREA_LEN: Final[int] = 30_000  # textarea at/above this → DROP (hard default)
ESSAY_NAMED_LEN: Final[int] = 1_000      # note/bio/statement-shaped at/above this → DROP

# Substring patterns (matched case-insensitively against name OR label OR helpText).

# Direct PII — names, addresses, phones, DOB/age, photo, social URLs.
PII_DIRECT_PATTERNS: Final[tuple[str, ...]] = (
    "firstname", "lastname", "middlename", "fullname", "salutation",
    "preferred_first_name", "preferred_name", "name_suffix", "assistantname",
    "nickname", "phoneticname", "maidenname",
    "address", "street", "city", "postal", "postcode", "zip",
    "phone", "mobile", "fax", "whatsapp", "telephone",
    "birthdate", "birth_date", "date_of_birth", "dob",
    "photourl", "photo", "headshot", "avatar",
    "twitter", "linkedin", "imdb", "facebook", "instagram",
    "personal_website", "profile_url", "link_to_video",
)

# Special-category data (GDPR Article 9). Overriding to keep these requires a
# recorded justification (see plan.py / docs §6).
PII_SPECIAL_PATTERNS: Final[tuple[str, ...]] = (
    "ethnic", "ethnicity", "race",
    "gender", "pronoun",
    "disability", "disabilities", "accessibility_need",
    "nationality", "citizenship",
    "religion", "sexual_orientation", "political_opinion",
    "health", "medical", "biometric", "genetic",
)

# Free-text essay name shapes (only DROP when also over ESSAY_NAMED_LEN).
ESSAY_NAME_PATTERNS: Final[tuple[str, ...]] = (
    "note", "notes", "comment", "description", "summary",
    "bio", "biography", "personal_statement", "supporting_statement",
    "essay", "feedback", "reason",
)

# Externally-meaningful identifiers → HASH_ID.
IDENTIFIER_PATTERNS: Final[tuple[str, ...]] = (
    "membership_number", "patron_number", "member_number",
    "website_id", "events_perfect_id", "external_id", "sap_id", "sap_number",
    "card_number", "cardid", "accountnumber", "bank_account", "iban", "bic", "swift",
    "nationalinsurance", "national_insurance", "passportnumber", "passport_number",
    "taxid", "tax_id", "vat", "duns", "iata",
    "twitterhandle", "twitter_handle",
)

# PII-source field names to scan formula expressions for (formula-leak detection).
FORMULA_LEAK_SOURCES: Final[tuple[str, ...]] = (
    "FirstName", "LastName", "MiddleName", "Salutation", "Name", "Email",
    "MobilePhone", "Phone", "Birthdate",
    "MailingStreet", "MailingCity", "MailingPostalCode",
)
