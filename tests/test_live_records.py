"""Live tests — hit the real org from tests/live_org.toml. Auto-skip when it is
not authenticated (see conftest.live_org). These are the automated counterpart
to the chatbot-driven checks in docs/regression-testing.md.
"""
import csv

import pytest

from sf_clean_room.audit import audit_log
from sf_clean_room.constants import API_VERSION, DROP
from sf_clean_room.pipeline import make_run_paths
from sf_clean_room.records_extract import AUDIT_SENTINEL
from sf_clean_room.records_pipeline import RecordsRequest, dry_run, execute
from sf_clean_room.session import get_session

pytestmark = pytest.mark.live

LIVE_OBJECT = "Account"  # present in every org; describe always works.


def test_live_dry_run_emits_plan(live_org, live_output_dir):
    session = get_session(live_org, api_version=API_VERSION)
    plan_file = live_output_dir / f"{live_org}-plan.toml"
    with audit_log(live_org, log_dir=live_output_dir / "logs") as log:
        text = dry_run(session, [LIVE_OBJECT], plan_file, log)
    assert "[scope]" in text
    assert LIVE_OBJECT in text
    assert plan_file.exists()


def test_live_extract_publishes_safely(live_org, live_output_dir):
    session = get_session(live_org, api_version=API_VERSION)
    paths = make_run_paths(
        live_output_dir / "temp", live_output_dir / live_org / LIVE_OBJECT, live_org
    )
    req = RecordsRequest(objects=[LIVE_OBJECT], where=None, plan_path=None, dry_run=False)
    with audit_log(live_org, log_dir=live_output_dir / "logs") as log:
        execute(session, req, paths, log)

    pub = paths.publish_path
    assert (pub / AUDIT_SENTINEL).exists()
    assert (pub / f"{LIVE_OBJECT}.tsv").exists()

    # Invariant: no column in the published TSV maps to a DROP action.
    audit = {
        row["field"]: row["action"]
        for row in csv.DictReader(open(pub / AUDIT_SENTINEL, encoding="utf-8"))
        if row["field"] != "__where__"
    }
    header = next(csv.reader(open(pub / f"{LIVE_OBJECT}.tsv", encoding="utf-8"), delimiter="\t"))
    for col in header:
        assert audit.get(col) != DROP, f"DROP field {col} leaked into TSV header"
