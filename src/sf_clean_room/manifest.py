"""Build and parse ``package.xml`` manifests.

Used to (a) write the published manifest from the components actually retrieved
(merged across batches, so it never overstates) and (b) parse the
Salesforce-returned manifest inside a retrieve zip for component-accurate
partial-retrieve detection (design §3.5).
"""
from __future__ import annotations

import base64
import io
import xml.etree.ElementTree as ET
import zipfile

from sf_clean_room.constants import API_VERSION
from sf_clean_room.soap import URN


def build_package_xml(members_by_type: dict[str, list[str]], api_version: str = API_VERSION) -> str:
    """Render a package.xml from ``{type: [member, ...]}``. Deterministic
    (types and members sorted). Types with no members are omitted."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<Package xmlns="{URN}">',
    ]
    for tname in sorted(members_by_type):
        members = sorted(set(members_by_type[tname]))
        if not members:
            continue
        lines.append("  <types>")
        for m in members:
            lines.append(f"    <members>{m}</members>")
        lines.append(f"    <name>{tname}</name>")
        lines.append("  </types>")
    lines.append(f"  <version>{api_version}</version>")
    lines.append("</Package>")
    lines.append("")
    return "\n".join(lines)


def parse_package_members(xml_text: str) -> dict[str, set[str]]:
    """Parse a package.xml into ``{type: {member, ...}}``."""
    out: dict[str, set[str]] = {}
    if not xml_text or not xml_text.strip():
        return out
    root = ET.fromstring(xml_text)
    ns = {"m": URN}
    for t in root.findall(".//m:types", ns):
        name = t.findtext("m:name", default="", namespaces=ns)
        if not name:
            continue
        members = {
            (e.text or "").strip()
            for e in t.findall("m:members", ns)
            if e.text and e.text.strip()
        }
        out.setdefault(name, set()).update(members)
    return out


def retrieved_members_from_zip(zip_b64: str) -> dict[str, set[str]]:
    """Read the package.xml inside a retrieve zip and return its members per
    type — i.e. what Salesforce actually returned (post-FLS/permission filter)."""
    zbytes = base64.b64decode(zip_b64)
    with zipfile.ZipFile(io.BytesIO(zbytes), "r") as z:
        name = next(
            (n for n in z.namelist() if n.rsplit("/", 1)[-1] == "package.xml"),
            None,
        )
        if name is None:
            return {}
        xml_text = z.read(name).decode("utf-8", errors="replace")
    return parse_package_members(xml_text)
