"""Technical-objects classifier (the safety boundary for get_technical_objects).

Two layers (from docs/requirements/05-technical-objects.md §3):
  Layer 0: structural skip — field types / names that are NEVER selected.  Applied
           at SOQL-build time in technical_download.py, not here.
  Layer 1: first-match-wins classification of selected fields (this module).
           1. Curated per-object overrides (source-controlled table §3.2).
           2. id / reference type  -> RAW.
           3. IP-named             -> DERIVE ip_prefix.
           4. email type / named   -> HASH email.
           5. phone                -> DROP.
           6. url type / named     -> DERIVE url_sanitise.
           7. Fine geo (lat/lon/city/postcode)  -> DROP.
              Coarse geo (country/subdivision/state) -> PASS.
           8. Free-text echo names -> DROP.
           9. Default              -> PASS.

Reuses hashing.py recipes and eventlog_classify.derive_ip_prefix / sanitise_url.
"""
from __future__ import annotations

from dataclasses import dataclass

from sf_clean_room.eventlog_classify import (
    DERIVE,
    DROP,
    HASH,
    PASS,
    RAW,
    derive_ip_prefix,
    sanitise_url,
)
from sf_clean_room.hashing import hash_email, hash_id

__all__ = [
    "RAW", "HASH", "DERIVE", "PASS", "DROP",
    "FieldMeta", "CURATED", "classify_field", "transform_value",
]

# ---------------------------------------------------------------------------
# Curated per-object overrides (source-controlled; design §3.2).
# Key: "ApiName.FieldName" (exact case, as Salesforce emits it).
# Value: (action, recipe) — recipe is "" unless action == DERIVE.
# ---------------------------------------------------------------------------
CURATED: dict[str, tuple[str, str]] = {
    # FlowInterview: merge-field labels routinely embed customer data values.
    "FlowInterview.InterviewLabel":         (DROP,   ""),
    "FlowInterview.PauseLabel":             (DROP,   ""),
    # SetupAuditTrail.Display: free text embedding user/field/profile names.
    # Action + Section (PASS via generic rules) carry the analytical signal.
    "SetupAuditTrail.Display":              (DROP,   ""),
    "SetupAuditTrail.DelegateUser":         (HASH,   "id"),
    # IdpEventLog.IdentityUsed: federation id / username / email used as NameID.
    "IdpEventLog.IdentityUsed":             (HASH,   "id"),
    # Organization.PrimaryContact: person name (names are never hashed).
    "Organization.PrimaryContact":          (DROP,   ""),
    # AsyncApexJob / ApexTestQueueItem.ExtendedStatus: error text can echo data.
    "AsyncApexJob.ExtendedStatus":          (DROP,   ""),
    "ApexTestQueueItem.ExtendedStatus":     (DROP,   ""),
    # BackgroundOperation: error text echoes data; ParentKey is a dev correlation key.
    "BackgroundOperation.Error":            (DROP,   ""),
    "BackgroundOperation.ParentKey":        (HASH,   "id"),
    # ApexLog.Status: free-text fault messages (Operation/Application carry signal).
    "ApexLog.Status":                       (DROP,   ""),
    # VerificationHistory.Remarks: admin free text.
    "VerificationHistory.Remarks":          (DROP,   ""),
    # LoginHistory.Status: documented Salesforce vocabulary (not user-authored text).
    "LoginHistory.Status":                  (PASS,   ""),
    # CronTrigger.CronExpression: schedule string (config, not content).
    "CronTrigger.CronExpression":           (PASS,   ""),
    # ApexTestResult: test failure messages / stack traces.
    "ApexTestResult.Message":               (DROP,   ""),
    "ApexTestResult.StackTrace":            (DROP,   ""),
}

# --- Name-pattern substring sets (lower-case, tested with 'in' / 'endswith') ---

_FINE_GEO = frozenset({
    "latitude", "longitude", "city", "postalcode", "postcode", "postal",
})
_COARSE_GEO = frozenset({
    "country", "countryiso", "countrycode", "subdivision", "state",
})
_FREE_TEXT_ECHO = frozenset({
    "message", "stacktrace", "display", "remarks", "error", "description",
})
_LABEL_NAMES = frozenset({
    "interviewlabel", "pauselabel",
})
# Type-based email rule only fires for text-bearing field types (mirrors get_records fix).
_TEXTY = frozenset({"string", "email", "url", ""})


@dataclass(frozen=True)
class FieldMeta:
    name: str
    type: str
    label: str = ""


def classify_field(object_name: str, meta: FieldMeta) -> tuple[str, str]:
    """Return ``(action, recipe)`` for one field. First match wins.

    ``object_name`` must match the CatalogueEntry.api_name exactly (case-sensitive).
    ``recipe`` is ``"ip_prefix"`` / ``"url_sanitise"`` / ``"email"`` / ``"id"`` for
    DERIVE/HASH, else ``""``.
    """
    # 1. Curated per-object overrides.
    curated_key = f"{object_name}.{meta.name}"
    if curated_key in CURATED:
        return CURATED[curated_key]

    t = (meta.type or "").lower()
    n = (meta.name or "").lower()

    # 2. id / reference → RAW (join key; pseudonymous).
    if t in ("id", "reference") or n.endswith("id") or n.endswith("ids"):
        return (RAW, "")

    # 3. IP-named → DERIVE ip_prefix.
    if n.endswith("ip") or n in {"sourceip", "remoteaddress", "ipaddress"}:
        return (DERIVE, "ip_prefix")

    # 4. email type or email-named on text-bearing field → HASH email.
    if t == "email":
        return (HASH, "email")
    if t in _TEXTY and "email" in n:
        return (HASH, "email")

    # 5. phone → DROP.
    if t == "phone" or "phone" in n or "mobile" in n:
        return (DROP, "")

    # 6. url type or url-named → DERIVE url_sanitise.
    if t == "url" or n.endswith("url") or n.endswith("uri"):
        return (DERIVE, "url_sanitise")

    # 7. Fine-grained geo → DROP; coarse geo → PASS.
    if any(s in n for s in _FINE_GEO):
        return (DROP, "")
    if any(s in n for s in _COARSE_GEO):
        return (PASS, "")

    # 8. Free-text echo names → DROP.
    if any(s in n for s in _FREE_TEXT_ECHO):
        return (DROP, "")
    if n in _LABEL_NAMES:
        return (DROP, "")

    # 9. Default: PASS.
    return (PASS, "")


def transform_value(action: str, recipe: str, value) -> str:
    """Apply a resolved action to one raw cell value.

    DROP returns ''.  Non-string scalars are coerced (CSV cells are str anyway).
    """
    sval = None if value is None else str(value)
    if action == HASH:
        if recipe == "email":
            return hash_email(sval)
        return hash_id(sval)
    if action == DERIVE:
        if recipe == "ip_prefix":
            return derive_ip_prefix(sval)
        if recipe == "url_sanitise":
            return sanitise_url(sval)
        return ""
    if action == DROP:
        return ""
    return sval if sval is not None else ""  # RAW / PASS
