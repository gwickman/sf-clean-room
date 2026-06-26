"""Event-log column classifier (the safety boundary for get_event_logs).

Resolves each EventLogFile CSV column to an action, applying the rules in
docs/requirements/04-event-log-fields.md (first match wins). Source-controlled, like
the metadata deny list and the get_records classifier. Pure and heavily tested.

Key facts that shape the rules (from the schema reference):
- Salesforce already emits SESSION_KEY / LOGIN_KEY *hashed* -> keep RAW (do not
  re-hash; that would only break the cross-event join).
- The only routinely-present human identifiers are USER_NAME / DELEGATED_USER_NAME
  (login/email-shaped) and DEVICE_ID (persistent device) -> HASH.
- Salesforce already provides coarse geo (COUNTRY_CODE / CLIENT_GEO) -> PASS; only
  the raw IP columns are derived.
"""
from __future__ import annotations

import re

from sf_clean_room.hashing import hash_id

_IP_IN_URL = re.compile(r"(\b\d{1,3}\.\d{1,3}\.\d{1,3}\.)\d+\b")

# Actions.
RAW = "RAW"
HASH = "HASH"
DERIVE = "DERIVE"
PASS = "PASS"
DROP = "DROP"

# --- source-controlled column sets (upper-snake-case, matched exactly) ---

IP_COLS = frozenset({"CLIENT_IP", "SOURCE_IP", "FORWARDED_FOR_IP", "REMOTE_ADDRESS", "IP_ADDRESS"})

# URL/URI columns not caught by the URI/URL suffix rule.
URL_COLS = frozenset({"REFERRER", "HTTP_REFERER", "NEXT_LINK", "BLOCKED_URI_DOMAIN", "REQUEST_PATH", "API_RESOURCE"})

# Direct human / persistent-device identifiers Salesforce left in the clear.
HASH_COLS = frozenset({"USER_NAME", "DELEGATED_USER_NAME", "DEVICE_ID"})

# Free-text / content / secret columns (exact names — see schema reference §3).
DROP_COLS = frozenset({
    "QUERY", "SEARCH_QUERY", "EXCEPTION_MESSAGE", "ERROR_MESSAGE", "MESSAGE",
    "ERROR_DESCRIPTION", "STACK_TRACE", "ACCESS_ERROR", "DOWNLOAD_ERROR",
    "CANCELLED_REASON", "FAILURE_REASON", "HTTP_HEADERS", "CONTEXT_MAP",
    "RESOURCE_SAMPLE", "DATA", "DESCRIPTION",
    "FILTER", "SELECT", "SEARCH", "ORDERBY", "EXPAND",  # OData query fragments
})

# Opaque correlation keys (incl. Salesforce-pre-hashed session/login keys).
RAW_COLS = frozenset({
    "REQUEST_ID", "ORGANIZATION_ID", "USER_ID", "SESSION_KEY", "LOGIN_KEY",
    "QUERY_ID", "CORRELATION_ID", "SQL_ID", "QUERY_IDENTIFIER", "SERVER_REQUEST_ID",
    "BOT_ID", "BOT_SESSION_ID", "PLANNER_ID", "DEVICE_SESSION_ID", "WAVE_SESSION_ID",
    "SESSION_ID", "UI_EVENT_ID", "UI_ROOT_ACTIVITY_ID",
})


def classify_column(name: str) -> tuple[str, str]:
    """Return ``(action, recipe)`` for a column name. ``recipe`` is
    ``"ip_prefix"`` / ``"url_sanitise"`` for DERIVE, else ``""``."""
    u = (name or "").strip().upper()

    # 1. IP addresses -> DERIVE (network prefix).
    if u in IP_COLS or u.endswith("_IP"):
        return (DERIVE, "ip_prefix")
    # 2. URL / URI -> DERIVE (host+path, query stripped).
    if u in URL_COLS or u.endswith("URI") or u.endswith("URL"):
        return (DERIVE, "url_sanitise")
    # 3. Human / persistent-device identifiers -> HASH (before the *_ID RAW rule).
    if u in HASH_COLS:
        return (HASH, "id")
    # 4. Free-text / content / secrets -> DROP.
    if u in DROP_COLS:
        return (DROP, "")
    # 5. Salesforce IDs and opaque/pre-hashed correlation keys -> RAW.
    if u in RAW_COLS or u.endswith("_ID") or u.endswith("_ID_DERIVED") or u.endswith("_IDS"):
        return (RAW, "")
    # 6. Conservative content-shaped fallback (narrow, to avoid enum false-positives).
    if (
        u.endswith("_MESSAGE") or u.endswith("_TEXT") or u.endswith("_HEADERS")
        or any(s in u for s in ("PASSWORD", "SECRET", "TOKEN", "CREDENTIAL", "STACK_TRACE"))
    ):
        return (DROP, "")
    # 7. Default: non-identifying analytical signal.
    return (PASS, "")


def derive_ip_prefix(value: str | None) -> str:
    """IPv4 -> last octet zeroed; IPv6 -> last 80 bits zeroed (keep first 3 groups)."""
    if not value:
        return ""
    v = value.strip()
    if not v:
        return ""
    if ":" in v:  # IPv6
        groups = v.split(":")
        head = [g for g in groups[:3] if g != ""]
        return ":".join(head) + "::" if head else ""
    if "." in v:  # IPv4
        parts = v.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3]) + ".0"
        return ""
    return ""


def sanitise_url(value: str | None) -> str:
    """Keep scheme+host+path; drop query string, matrix params, and fragment.
    IPv4 addresses anywhere in the URL (host or path) are masked to /24."""
    if not value:
        return ""
    v = value.strip()
    for sep in ("?", ";", "#"):
        v = v.split(sep, 1)[0]
    return _IP_IN_URL.sub(r"\g<1>0", v)


def transform_value(action: str, recipe: str, value) -> str:
    """Apply a resolved action to one raw cell. DROP columns are omitted upstream,
    so DROP returns ''. Non-string scalars are coerced (CSV cells are str anyway)."""
    sval = None if value is None else str(value)
    if action == HASH:
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
