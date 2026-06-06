import base64
import io
import zipfile

from sf_clean_room.manifest import (
    build_package_xml,
    parse_package_members,
    retrieved_members_from_zip,
)


def test_build_and_parse_roundtrip():
    members = {"ApexClass": ["B", "A"], "CustomObject": ["Account__c"]}
    xml = build_package_xml(members, api_version="62.0")
    assert "<version>62.0</version>" in xml
    parsed = parse_package_members(xml)
    assert parsed == {"ApexClass": {"A", "B"}, "CustomObject": {"Account__c"}}


def test_build_is_deterministic_and_sorted():
    a = build_package_xml({"B": ["2", "1"], "A": ["x"]})
    b = build_package_xml({"A": ["x"], "B": ["1", "2"]})
    assert a == b
    # A sorts before B; members sorted within a type.
    assert a.index("<name>A</name>") < a.index("<name>B</name>")
    assert a.index("<members>1</members>") < a.index("<members>2</members>")


def test_build_omits_empty_types():
    xml = build_package_xml({"ApexClass": [], "Flow": ["F1"]})
    assert "ApexClass" not in xml
    assert "Flow" in xml


def test_parse_empty_returns_empty():
    assert parse_package_members("") == {}


def test_retrieved_members_from_zip():
    pkg = build_package_xml({"ApexClass": ["A", "B"]})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("package.xml", pkg)
        z.writestr("classes/A.cls", "x")
        z.writestr("classes/A.cls-meta.xml", "x")
    b64 = base64.b64encode(buf.getvalue()).decode()
    assert retrieved_members_from_zip(b64) == {"ApexClass": {"A", "B"}}


def test_retrieved_members_zip_without_package_xml():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("classes/A.cls", "x")
    b64 = base64.b64encode(buf.getvalue()).decode()
    assert retrieved_members_from_zip(b64) == {}
