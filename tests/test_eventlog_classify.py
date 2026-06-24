import pytest

from sf_clean_room.eventlog_classify import (
    DERIVE, DROP, HASH, PASS, RAW,
    classify_column, derive_ip_prefix, sanitise_url, transform_value,
)
from sf_clean_room.hashing import hash_id


@pytest.mark.parametrize("name,action", [
    # IP -> DERIVE
    ("CLIENT_IP", DERIVE), ("SOURCE_IP", DERIVE), ("FORWARDED_FOR_IP", DERIVE),
    ("REMOTE_ADDRESS", DERIVE), ("IP_ADDRESS", DERIVE),
    # URL/URI -> DERIVE
    ("URI", DERIVE), ("PAGE_URL", DERIVE), ("REFERRER_URI", DERIVE),
    ("LOGIN_URL", DERIVE), ("API_RESOURCE", DERIVE), ("MALFORMED_URL", DERIVE),
    # HASH human/device ids (before the *_ID RAW rule)
    ("USER_NAME", HASH), ("DELEGATED_USER_NAME", HASH), ("DEVICE_ID", HASH),
    # DROP content
    ("QUERY", DROP), ("SEARCH_QUERY", DROP), ("HTTP_HEADERS", DROP),
    ("STACK_TRACE", DROP), ("EXCEPTION_MESSAGE", DROP), ("DESCRIPTION", DROP),
    ("FILTER", DROP), ("SELECT", DROP), ("CONTEXT_MAP", DROP),
    # RAW ids + pre-hashed correlation keys
    ("USER_ID", RAW), ("USER_ID_DERIVED", RAW), ("REPORT_ID", RAW),
    ("SESSION_KEY", RAW), ("LOGIN_KEY", RAW), ("DEVICE_SESSION_ID", RAW),
    ("URI_ID_DERIVED", RAW), ("DATASET_IDS", RAW), ("REQUEST_ID", RAW),
    # PASS — analytical / SF-provided geo / config names
    ("COUNTRY_CODE", PASS), ("CLIENT_GEO", PASS), ("QUERY_TYPE", PASS),
    ("KEY_PREFIX", PASS), ("RUN_TIME", PASS), ("EVENT_TYPE", PASS),
    ("TIMESTAMP_DERIVED", PASS), ("REPORT_DESCRIPTION", PASS), ("ENTITY_NAME", PASS),
])
def test_classify(name, action):
    assert classify_column(name)[0] == action


def test_session_keys_are_raw_not_hashed():
    # Salesforce already hashes these; re-hashing would break the join.
    assert classify_column("SESSION_KEY") == (RAW, "")
    assert classify_column("LOGIN_KEY") == (RAW, "")


def test_ip_derive_recipe():
    assert classify_column("CLIENT_IP") == (DERIVE, "ip_prefix")
    assert classify_column("URI") == (DERIVE, "url_sanitise")


def test_derive_ip_prefix():
    assert derive_ip_prefix("203.0.113.55") == "203.0.113.0"
    assert derive_ip_prefix("10.0.0.1") == "10.0.0.0"
    assert derive_ip_prefix("2001:db8:85a3:8d3:1319:8a2e:370:7348") == "2001:db8:85a3::"
    assert derive_ip_prefix("") == ""
    assert derive_ip_prefix("not-an-ip") == ""


def test_sanitise_url():
    assert sanitise_url("/home?ret=%2Fsetup") == "/home"
    assert sanitise_url("/p;jsessionid=ABC") == "/p"
    assert sanitise_url("https://h.my.salesforce.com/x/y?a=1&b=2") == "https://h.my.salesforce.com/x/y"
    assert sanitise_url("/x#frag") == "/x"
    assert sanitise_url("") == ""
    # IPv4 addresses in URL paths must be masked (last octet zeroed).
    assert sanitise_url("https://util.appinium.com/ipinfo/93.159.47.56") == "https://util.appinium.com/ipinfo/93.159.47.0"
    assert sanitise_url("http://10.0.0.1/api/v1?token=abc") == "http://10.0.0.0/api/v1"
    assert sanitise_url("https://example.com/path/192.168.1.42/info") == "https://example.com/path/192.168.1.0/info"


def test_transform_value():
    assert transform_value(HASH, "id", "jane@example.com") == hash_id("jane@example.com")
    assert transform_value(DERIVE, "ip_prefix", "203.0.113.55") == "203.0.113.0"
    assert transform_value(DERIVE, "url_sanitise", "/home?x=1") == "/home"
    assert transform_value(RAW, "", "005xx") == "005xx"
    assert transform_value(PASS, "", 1234) == "1234"   # non-string scalar coerced
    assert transform_value(DROP, "", "anything") == ""
