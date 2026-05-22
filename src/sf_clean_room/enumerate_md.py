"""describeMetadata + listMetadata, with foldered-type handling."""
from __future__ import annotations

from sf_clean_room.constants import API_VERSION, DENY, FOLDERED
from sf_clean_room.soap import URN, SoapClient


def describe_metadata(client: SoapClient) -> list[dict]:
    body = f'<describeMetadata xmlns="{URN}"><asOfVersion>{API_VERSION}</asOfVersion></describeMetadata>'
    root = client.post(body)
    ns = {"m": URN}
    out: list[dict] = []
    for mo in root.findall(".//m:metadataObjects", ns):
        name = mo.findtext("m:xmlName", default="", namespaces=ns)
        in_folder = mo.findtext("m:inFolder", default="false", namespaces=ns) == "true"
        if name:
            out.append({"xmlName": name, "inFolder": in_folder})
    return out


def list_metadata(client: SoapClient, type_name: str, folder: str | None = None) -> list[str]:
    q = f"<queries><type>{type_name}</type>"
    if folder:
        q += f"<folder>{folder}</folder>"
    q += "</queries>"
    body = f'<listMetadata xmlns="{URN}">{q}<asOfVersion>{API_VERSION}</asOfVersion></listMetadata>'
    root = client.post(body)
    ns = {"m": URN}
    return [
        r.findtext("m:fullName", default="", namespaces=ns)
        for r in root.findall(".//m:result", ns)
        if r is not None
    ]


def enumerate_all_members(client: SoapClient) -> dict[str, list[str]]:
    """Return ``{type_name: [fullName, ...]}`` for every available, non-DENY type."""
    meta = describe_metadata(client)
    members: dict[str, list[str]] = {}

    for t, folder_type in FOLDERED.items():
        if t in DENY:
            continue
        folders = list_metadata(client, folder_type)
        if not folders:
            continue
        items: list[str] = []
        for f in folders:
            items.extend(list_metadata(client, t, folder=f))
        if items:
            members[t] = sorted(set(items))

    for obj in meta:
        tname = obj["xmlName"]
        if tname in FOLDERED or tname in DENY:
            continue
        items = list_metadata(client, tname)
        if items:
            members[tname] = sorted(set(items))

    return members
