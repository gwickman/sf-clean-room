"""Live test for get_event_logs against the configured org. Auto-skips when the
org is not authenticated. Exercises the read-only query + publish path; when the
org has no Event Monitoring data (e.g. a dev edition), the run publishes an empty
run folder with a header-only sentinel and the per-record leak checks are noted
as not exercised (see docs/regression-testing.md).
"""
import csv

import pytest

from sf_clean_room.audit import audit_log
from sf_clean_room.constants import API_VERSION
from sf_clean_room.eventlog_classify import DROP
from sf_clean_room.eventlog_pipeline import EventLogRequest, SENTINEL_NAME, dry_run, execute
from sf_clean_room.session import get_session

pytestmark = pytest.mark.live


def test_live_dry_run_queries_without_aborting(live_org, live_output_dir):
    session = get_session(live_org, api_version=API_VERSION)
    req = EventLogRequest(only=None, plan_path=None, dry_run=True)
    with audit_log(live_org, log_dir=live_output_dir / "logs") as log:
        report = dry_run(session, live_output_dir, live_org, req, log)
    # Query path reached without aborting — either a window report or, if a prior
    # run already covers yesterday, the idempotent "already up to date" message.
    assert "window" in report or "already up to date" in report


def test_live_run_publishes_run_folder_with_sentinel(live_org, live_output_dir):
    session = get_session(live_org, api_version=API_VERSION)
    req = EventLogRequest(only=None, plan_path=None, dry_run=False)
    with audit_log(live_org, log_dir=live_output_dir / "logs") as log:
        dest = execute(session, live_output_dir, live_org, req, live_output_dir / "temp", log)

    assert (dest / SENTINEL_NAME).exists()  # sentinel published last

    # If any CSVs were produced (org has Event Monitoring), enforce no-raw-dump:
    actions = {
        row["column"]: row["action"]
        for row in csv.DictReader(open(dest / SENTINEL_NAME, encoding="utf-8"))
    }
    for csv_path in dest.glob("*_*.csv"):
        if csv_path.name.startswith("_"):
            continue
        header = next(csv.reader(open(csv_path, encoding="utf-8")), [])
        for col in header:
            assert actions.get(col) != DROP, f"DROP column {col} leaked into {csv_path.name}"
