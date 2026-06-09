import csv
import datetime as dt

from sf_clean_room import eventlog_pipeline as elp
from sf_clean_room.eventlog_download import compute_end_date
from sf_clean_room.eventlog_pipeline import EventLogRequest, dry_run, execute
from sf_clean_room.hashing import hash_id
from sf_clean_room.session import Session

ALIAS = "demo"

LOGIN_CSV = (
    "EVENT_TYPE,USER_ID,USER_NAME,CLIENT_IP,URI,SESSION_KEY,COUNTRY_CODE\n"
    '"Login","005xx","jane@example.com","203.0.113.55","/home?ret=%2Fsetup","ABC123","US"\n'
)
REPORT_CSV = (
    "EVENT_TYPE,USER_ID,REPORT_ID,QUERY\n"
    "\"ReportExport\",\"005xx\",\"00Oxx\",\"SELECT Name FROM Contact WHERE Email='a@b.com'\"\n"
)

RECORDS = [
    {"Id": "0AT1", "EventType": "Login", "LogDate": "2026-06-09T00:00:00.000+0000",
     "ApiVersion": "61.0", "LogFileFieldNames": "EVENT_TYPE,USER_ID,USER_NAME,CLIENT_IP,URI,SESSION_KEY,COUNTRY_CODE"},
    {"Id": "0AT2", "EventType": "ReportExport", "LogDate": "2026-06-09T00:00:00.000+0000",
     "ApiVersion": "61.0", "LogFileFieldNames": "EVENT_TYPE,USER_ID,REPORT_ID,QUERY"},
]


def a_session():
    return Session("tok", "https://x.my.salesforce.com", "00D", "u@e.com", ALIAS, "61.0")


def fake_query(_s, _start, _end, _only):
    return list(RECORDS)


def fake_fetch(_s, rec):
    return LOGIN_CSV if rec["Id"] == "0AT1" else REPORT_CSV


def _run_dir(base):
    root = base / "event_logs" / ALIAS
    return next(d for d in root.iterdir() if "_to_" in d.name)


def test_execute_anonymises_and_no_raw_dump(tmp_path, log_to):
    req = EventLogRequest(only=None, plan_path=None, dry_run=False)
    with log_to() as log:
        dest = execute(a_session(), tmp_path, ALIAS, req, tmp_path / "temp", log,
                       query_fn=fake_query, fetch_fn=fake_fetch)

    assert (dest / elp.SENTINEL_NAME).exists()
    assert (dest / elp.SUMMARY_NAME).exists()
    files = sorted(p.name for p in dest.glob("*_Login_*.csv")) + sorted(p.name for p in dest.glob("*_ReportExport_*.csv"))
    assert len(files) == 2

    login = next(dest.glob("*_Login_*.csv"))
    rows = list(csv.reader(open(login, encoding="utf-8")))
    header, data = rows[0], dict(zip(rows[0], rows[1]))
    assert data["USER_ID"] == "005xx"                       # RAW
    assert data["SESSION_KEY"] == "ABC123"                  # RAW (already hashed by SF)
    assert data["USER_NAME"] == hash_id("jane@example.com") # HASH
    assert data["CLIENT_IP"] == "203.0.113.0"               # DERIVE prefix
    assert data["URI"] == "/home"                           # query stripped
    assert data["COUNTRY_CODE"] == "US"                     # PASS

    report = next(dest.glob("*_ReportExport_*.csv"))
    rheader = next(csv.reader(open(report, encoding="utf-8")))
    assert "QUERY" not in rheader                           # DROP column omitted

    # No-raw-dump: nothing sensitive survives anywhere in the published folder.
    blob = "".join(p.read_text(encoding="utf-8") for p in dest.glob("*.csv"))
    assert "jane@example.com" not in blob
    assert "203.0.113.55" not in blob                        # raw IP gone
    assert "a@b.com" not in blob and "SELECT" not in blob    # query text gone
    assert "%2Fsetup" not in blob                            # query string gone

    # temp cleaned up
    assert not any((tmp_path / "temp").glob("*")) if (tmp_path / "temp").exists() else True


def test_idempotent_no_op(tmp_path, log_to):
    end = compute_end_date(dt.datetime.now(dt.timezone.utc).date())
    root = tmp_path / "event_logs" / ALIAS
    existing = root / f"2026-01-01_to_{end.strftime('%Y-%m-%d')}"
    existing.mkdir(parents=True)
    called = {"q": False}

    def q(*a, **k):
        called["q"] = True
        return []

    req = EventLogRequest(only=None, plan_path=None, dry_run=False)
    with log_to() as log:
        dest = execute(a_session(), tmp_path, ALIAS, req, tmp_path / "temp", log,
                       query_fn=q, fetch_fn=fake_fetch)
    assert dest == existing
    assert called["q"] is False    # no query when already up to date


def test_per_record_fetch_failure_is_skipped(tmp_path, log_to):
    def flaky_fetch(_s, rec):
        if rec["Id"] == "0AT1":
            raise RuntimeError("boom")
        return REPORT_CSV

    req = EventLogRequest(only=None, plan_path=None, dry_run=False)
    with log_to() as log:
        dest = execute(a_session(), tmp_path, ALIAS, req, tmp_path / "temp", log,
                       query_fn=fake_query, fetch_fn=flaky_fetch)
    assert not list(dest.glob("*_Login_*.csv"))          # skipped
    assert list(dest.glob("*_ReportExport_*.csv"))       # other one made it
    assert (dest / elp.SENTINEL_NAME).exists()           # run still completes


def test_dry_run_reports_window_and_plan(tmp_path, log_to):
    req = EventLogRequest(only=None, plan_path=None, dry_run=True)
    with log_to() as log:
        report = dry_run(a_session(), tmp_path, ALIAS, req, log, query_fn=fake_query)
    assert "Login: 1" in report and "ReportExport: 1" in report
    assert "[scope]" in report and "[overrides]" in report
    assert "CLIENT_IP" in report      # column appears in the emitted plan
