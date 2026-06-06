"""Live test for get_metadata v2.1 enumeration against the configured org.

Exercises the fault-tolerant enumerate + skip-log path (no retrieve, so fast).
Auto-skips when the org is not authenticated (conftest.live_org).
"""
import pytest

from sf_clean_room.audit import audit_log
from sf_clean_room.constants import API_VERSION, DENY
from sf_clean_room.pipeline import plan_only
from sf_clean_room.session import get_session

pytestmark = pytest.mark.live


def test_live_enumerate_does_not_abort_and_reports_skips(live_org, live_output_dir):
    session = get_session(live_org, api_version=API_VERSION)
    with audit_log(live_org, log_dir=live_output_dir / "logs") as log:
        plan = plan_only(session, log)
    # Enumeration completed without aborting and produced a batch plan.
    assert "batch(es) planned" in plan
    # The dry-run reports the would-be skip log (empty or with enum-bucket rows).
    assert "_skipped-types.csv" in plan
    # A deny-listed type must never surface in the would-be skip log.
    for line in plan.splitlines():
        if line.strip().startswith(tuple(f"{d}:" for d in DENY)):
            raise AssertionError(f"deny-listed type appeared in skip report: {line}")
