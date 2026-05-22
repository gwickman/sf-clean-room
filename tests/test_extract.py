import base64
import io
import zipfile

import pytest

from sf_clean_room.extract import extract_zip_to


def _zip_b64(entries: dict[str, bytes]) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_basic_extraction(tmp_path):
    z = _zip_b64({
        "package.xml": b"<Package/>",
        "classes/Foo.cls": b"public class Foo {}",
    })
    renames = extract_zip_to(z, tmp_path)
    assert renames == []
    assert (tmp_path / "package.xml").read_bytes() == b"<Package/>"
    assert (tmp_path / "classes" / "Foo.cls").read_bytes() == b"public class Foo {}"
    assert not (tmp_path / "_path_renames.csv").exists()


def test_zip_slip_is_blocked(tmp_path):
    # Path attempting to escape the target directory.
    z = _zip_b64({
        "../evil.txt": b"pwned",
        "ok.txt": b"fine",
    })
    extract_zip_to(z, tmp_path)
    assert (tmp_path / "ok.txt").exists()
    # Anything that resolved outside tmp_path must NOT exist next to it.
    assert not (tmp_path.parent / "evil.txt").exists()


def test_illegal_windows_chars_are_sanitised(tmp_path):
    z = _zip_b64({
        'objects/Acc<ount>.field': b"x",
    })
    renames = extract_zip_to(z, tmp_path)
    # < and > should be replaced with _
    assert any("Acc_ount_.field" in written for _, written in renames)
    assert (tmp_path / "_path_renames.csv").exists()


def test_long_component_is_shortened_with_hash(tmp_path):
    long_name = "A" * 200 + ".cls"
    z = _zip_b64({f"classes/{long_name}": b"x"})
    renames = extract_zip_to(z, tmp_path)
    assert renames, "expected the long filename to be rewritten"
    _, written = renames[0]
    # Written component must be under the 120-char ceiling and retain extension.
    last = written.split("/")[-1]
    assert len(last) <= 120
    assert last.endswith(".cls")


def test_renames_csv_written_when_anything_rewritten(tmp_path):
    z = _zip_b64({'a<b.txt': b"x"})
    extract_zip_to(z, tmp_path)
    csv = (tmp_path / "_path_renames.csv").read_text(encoding="utf-8")
    assert csv.startswith("original,extracted\n")
    assert "a<b.txt" in csv


def test_directory_entries_are_skipped(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("nested/", b"")  # directory placeholder
        z.writestr("nested/file.txt", b"hello")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    extract_zip_to(b64, tmp_path)
    assert (tmp_path / "nested" / "file.txt").read_bytes() == b"hello"
