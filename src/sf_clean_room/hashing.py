"""Frozen, never-salted hash recipes.

The recipes are fixed so that a hashed column joins to the same logical value
extracted from another system or another org. **Do not salt** — salting would
defeat the cross-source join, which is the whole point of hashing rather than
dropping an identifier.

* Email : ``sha256(lower(strip(value)))``
* ID    : ``sha256(strip(value))``

An empty / whitespace-only value hashes to the empty string (preserving NULL
semantics and avoiding one giant collision bucket).
"""
from __future__ import annotations

import hashlib


def hash_email(value: str | None) -> str:
    if value is None:
        return ""
    v = value.strip().lower()
    if not v:
        return ""
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def hash_id(value: str | None) -> str:
    if value is None:
        return ""
    v = value.strip()
    if not v:
        return ""
    return hashlib.sha256(v.encode("utf-8")).hexdigest()
