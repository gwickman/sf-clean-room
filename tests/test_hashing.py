import hashlib

from sf_clean_room.hashing import hash_email, hash_id


def test_hash_email_lowercases_and_strips():
    expected = hashlib.sha256("foo@bar.com".encode()).hexdigest()
    assert hash_email("  Foo@Bar.COM ") == expected


def test_hash_id_strips_but_preserves_case():
    expected = hashlib.sha256("WID-123".encode()).hexdigest()
    assert hash_id("  WID-123 ") == expected
    # Case matters for ids (unlike email).
    assert hash_id("wid-123") != hash_id("WID-123")


def test_empty_and_none_hash_to_empty():
    for v in ("", "   ", None):
        assert hash_email(v) == ""
        assert hash_id(v) == ""


def test_deterministic_no_salt():
    assert hash_email("a@b.com") == hash_email("a@b.com")
    assert hash_id("x") == hash_id("x")


def test_known_vector():
    # sha256("a@b.com") — guards against accidental recipe changes that would
    # break cross-source joins.
    assert hash_email("a@b.com") == hashlib.sha256(b"a@b.com").hexdigest()
