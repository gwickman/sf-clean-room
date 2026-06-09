import datetime as dt

from sf_clean_room.eventlog_download import (
    build_query,
    compute_end_date,
    determine_start_date,
    find_completed_folder,
    safe_date,
    EVENTLOG_LOOKBACK_DAYS,
)


def test_compute_end_date_is_yesterday():
    assert compute_end_date(dt.date(2026, 6, 10)) == dt.date(2026, 6, 9)


def test_determine_start_date_cold_start(tmp_path):
    today = dt.date(2026, 6, 10)
    assert determine_start_date(tmp_path, today) == today - dt.timedelta(days=EVENTLOG_LOOKBACK_DAYS)


def test_determine_start_date_resumes(tmp_path):
    (tmp_path / "2026-05-01_to_2026-05-31").mkdir()
    (tmp_path / "2026-04-01_to_2026-04-30").mkdir()
    assert determine_start_date(tmp_path, dt.date(2026, 6, 10)) == dt.date(2026, 6, 1)


def test_find_completed_folder(tmp_path):
    (tmp_path / "2026-05-12_to_2026-06-09").mkdir()
    assert find_completed_folder(tmp_path, dt.date(2026, 6, 9)) is not None
    assert find_completed_folder(tmp_path, dt.date(2026, 6, 8)) is None


def test_safe_date():
    assert safe_date("2026-06-09T00:00:00.000+0000") == "2026-06-09"
    assert safe_date("2026-06-09") == "2026-06-09"


def test_build_query_window_and_filters():
    q = build_query(dt.date(2026, 6, 1), dt.date(2026, 6, 9), ["Login", "ReportExport"], with_interval=True)
    assert "FROM EventLogFile" in q
    assert "Interval = 'Daily'" in q
    assert "LogDate >= 2026-06-01T00:00:00Z" in q
    assert "LogDate < 2026-06-10T00:00:00Z" in q          # end + 1 day, exclusive
    assert "EventType IN ('Login', 'ReportExport')" in q
    assert "LogFileFieldNames" in q                        # needed for --dry-run plan


def test_build_query_without_interval_or_filter():
    q = build_query(dt.date(2026, 6, 1), dt.date(2026, 6, 9), None, with_interval=False)
    assert "Interval" not in q
    assert "EventType IN" not in q
