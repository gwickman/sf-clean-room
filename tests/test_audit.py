import io

from sf_clean_room.audit import AuditLog, audit_log


def test_write_goes_to_file_and_tee_stream(tmp_path):
    fpath = tmp_path / "x.log"
    tee = io.StringIO()
    with open(fpath, "w", encoding="utf-8") as fh:
        log = AuditLog(fh, fpath, tee_stream=tee)
        log.write("hello")
    file_content = fpath.read_text(encoding="utf-8")
    assert "hello" in file_content
    # File contains a timestamp prefix; tee output does not.
    assert "[" in file_content  # timestamp brackets present
    assert tee.getvalue() == "hello\n"


def test_section_echoes_to_tee(tmp_path):
    fpath = tmp_path / "x.log"
    tee = io.StringIO()
    with open(fpath, "w", encoding="utf-8") as fh:
        log = AuditLog(fh, fpath, tee_stream=tee)
        log.section("phase")
    assert "=== phase ===" in tee.getvalue()
    assert "=== phase ===" in fpath.read_text(encoding="utf-8")


def test_write_file_only_does_not_tee(tmp_path):
    fpath = tmp_path / "x.log"
    tee = io.StringIO()
    with open(fpath, "w", encoding="utf-8") as fh:
        log = AuditLog(fh, fpath, tee_stream=tee)
        log.write_file_only("forensic-detail")
    assert "forensic-detail" in fpath.read_text(encoding="utf-8")
    assert tee.getvalue() == ""


def test_without_tee_writes_only_to_file(tmp_path):
    fpath = tmp_path / "x.log"
    with open(fpath, "w", encoding="utf-8") as fh:
        log = AuditLog(fh, fpath)  # no tee
        log.write("solo")
    assert "solo" in fpath.read_text(encoding="utf-8")


def test_audit_log_context_writes_open_close_markers(tmp_path):
    with audit_log("myorg", log_dir=tmp_path) as log:
        log.write("middle")
    content = log.path.read_text(encoding="utf-8")
    assert "audit log opened" in content
    assert "middle" in content
    assert "audit log closed" in content
