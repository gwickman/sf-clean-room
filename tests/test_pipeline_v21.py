import base64
import csv
import io
import zipfile

from sf_clean_room import pipeline
from sf_clean_room.manifest import build_package_xml
from sf_clean_room.pipeline import SKIPPED_TYPES_NAME, make_run_paths
from sf_clean_room.publish import SENTINEL_NAME
from sf_clean_room.retrieve import RetrieveResult
from sf_clean_room.session import Session
from sf_clean_room.skip_log import SkipLog


def _zip_b64(returned_members: dict[str, list[str]], files: dict[str, str]) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("package.xml", build_package_xml(returned_members))
        for path, content in files.items():
            z.writestr(path, content)
    return base64.b64encode(buf.getvalue()).decode()


def a_session():
    return Session("tok", "https://x.my.salesforce.com", "00D", "u@e.com", "demo", "61.0")


def test_execute_records_partial_retrieve_and_publishes_skip_log(tmp_path, log_to, monkeypatch):
    # Enumeration: 3 ApexClasses requested; one type already skipped at enum time.
    def fake_enum(client):
        skip = SkipLog()
        skip.add(type="DecisionTable", bucket="insufficient_access", detail="no access")
        return {"ApexClass": ["A", "B", "C"]}, skip
    monkeypatch.setattr(pipeline, "enumerate_all_members", fake_enum)

    # Retrieve returns only A and B (C filtered server-side) -> partial_retrieve.
    result = RetrieveResult(
        async_id="09S", status="Succeeded",
        zip_b64=_zip_b64({"ApexClass": ["A", "B"]},
                         {"classes/A.cls": "x", "classes/A.cls-meta.xml": "y",
                          "classes/B.cls": "x", "classes/B.cls-meta.xml": "y"}),
        error="", duration_secs=1.0,
    )
    monkeypatch.setattr(pipeline, "run_batch", lambda *a, **k: result)

    paths = make_run_paths(tmp_path / "temp", tmp_path / "out", "demo")
    with log_to() as log:
        pipeline.execute(a_session(), paths, log)

    pub = paths.publish_path
    assert (pub / SENTINEL_NAME).exists()
    assert (pub / SKIPPED_TYPES_NAME).exists()
    assert (pub / "classes" / "A.cls").exists()

    # Skip log: the enum skip AND the partial-retrieve row.
    rows = {r["type"]: r for r in csv.DictReader(open(pub / SKIPPED_TYPES_NAME, encoding="utf-8"))}
    assert rows["DecisionTable"]["bucket"] == "insufficient_access"
    assert rows["ApexClass"]["bucket"] == "partial_retrieve"
    assert rows["ApexClass"]["components_requested"] == "3"
    assert rows["ApexClass"]["components_retrieved"] == "2"

    # Published package.xml reflects RETRIEVED members (A, B) — never overstates (no C).
    pkg = (pub / SENTINEL_NAME).read_text(encoding="utf-8")
    assert "<members>A</members>" in pkg and "<members>B</members>" in pkg
    assert "<members>C</members>" not in pkg

    # Detail must not leak into the published skip log.
    assert "no access" not in (pub / SKIPPED_TYPES_NAME).read_text(encoding="utf-8")

    assert not paths.run_temp_dir.exists()  # cleaned after successful publish


def test_publish_moves_preceding_artefact_and_sentinel(tmp_path):
    from sf_clean_room.publish import publish
    temp = tmp_path / "t"
    (temp / "classes").mkdir(parents=True)
    (temp / "classes" / "A.cls").write_text("x", encoding="utf-8")
    (temp / SKIPPED_TYPES_NAME).write_text("type,bucket,components_requested,components_retrieved\n", encoding="utf-8")
    (temp / SENTINEL_NAME).write_text("<Package/>", encoding="utf-8")
    out = tmp_path / "out"
    publish(temp, out, sentinel_name=SENTINEL_NAME, preceding_artefacts=(SKIPPED_TYPES_NAME,))
    assert (out / SENTINEL_NAME).exists()
    assert (out / SKIPPED_TYPES_NAME).exists()
    assert (out / "classes" / "A.cls").exists()


def test_full_permission_run_has_header_only_skip_log(tmp_path, log_to, monkeypatch):
    def fake_enum(client):
        return {"ApexClass": ["A", "B"]}, SkipLog()
    monkeypatch.setattr(pipeline, "enumerate_all_members", fake_enum)
    result = RetrieveResult(
        async_id="09S", status="Succeeded",
        zip_b64=_zip_b64({"ApexClass": ["A", "B"]}, {"classes/A.cls": "x", "classes/B.cls": "x"}),
        error="", duration_secs=1.0,
    )
    monkeypatch.setattr(pipeline, "run_batch", lambda *a, **k: result)

    paths = make_run_paths(tmp_path / "temp", tmp_path / "out", "demo")
    with log_to() as log:
        pipeline.execute(a_session(), paths, log)

    rows = list(csv.reader(open(paths.publish_path / SKIPPED_TYPES_NAME, encoding="utf-8")))
    assert len(rows) == 1  # header only — nothing skipped
