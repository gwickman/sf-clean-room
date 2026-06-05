"""Shared test fixtures, including the opt-in live-org plumbing.

Live tests are marked ``@pytest.mark.live`` and auto-skip when the configured
org (``tests/live_org.toml``) is not authenticated. Nothing here ever logs in
or mutates ``sf`` state — it only checks whether a session can be resolved.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_CONFIG = Path(__file__).resolve().parent / "live_org.toml"


def _load_live_config() -> dict:
    if not LIVE_CONFIG.exists():
        return {}
    with open(LIVE_CONFIG, "rb") as f:
        return tomllib.load(f)


def _org_is_authenticated(alias: str) -> bool:
    try:
        from sf_clean_room.constants import API_VERSION
        from sf_clean_room.session import get_session

        get_session(alias, api_version=API_VERSION, retries=0, wait_seconds=0)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def live_org() -> str:
    """Return the configured live org alias, or skip if it is unavailable."""
    cfg = _load_live_config()
    alias = cfg.get("test_org")
    if not alias:
        pytest.skip("no test_org configured in tests/live_org.toml")
    if not _org_is_authenticated(alias):
        pytest.skip(
            f"live org {alias!r} is not authenticated "
            f"(run `sf org login web --alias {alias}` to enable live tests)"
        )
    return alias


@pytest.fixture
def log_to(tmp_path):
    """Factory yielding an AuditLog that writes under tmp (no fixed-location writes)."""
    from contextlib import contextmanager

    from sf_clean_room.audit import audit_log

    @contextmanager
    def _factory(alias: str = "testorg"):
        with audit_log(alias, log_dir=tmp_path / "logs") as log:
            yield log

    return _factory


@pytest.fixture(scope="session")
def live_output_dir() -> Path:
    cfg = _load_live_config()
    out = REPO_ROOT / cfg.get("output_dir", ".test-output")
    out.mkdir(parents=True, exist_ok=True)
    return out
