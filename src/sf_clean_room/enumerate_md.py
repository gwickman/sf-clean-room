"""describeMetadata + listMetadata, fault-tolerant under limited permissions.

A per-type ``listMetadata`` failure does not abort the run (design §3.1): it is
classified into a skip bucket, recorded in the run's ``SkipLog``, and the run
continues. Only a wholesale ``describeMetadata`` failure is fatal (a genuine
blocker — the tool cannot produce a plan). Always-probe types are unioned with
the describe output so types it hides from limited identities are still
attempted (§3.2). Foldered types use a two-step listing and are individually
fault-tolerant (§3.3).
"""
from __future__ import annotations

from sf_clean_room.constants import (
    ALWAYS_PROBE_TYPES,
    API_VERSION,
    DENY,
    FOLDERED,
    SYNTHETIC_FOLDERS,
    classify_skip_bucket,
)
from sf_clean_room.skip_log import SkipLog
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


def _try_list(
    client: SoapClient, type_name: str, folder: str | None = None
) -> tuple[list[str], Exception | None]:
    """list_metadata that never raises — returns (members, error)."""
    try:
        return list_metadata(client, type_name, folder=folder), None
    except Exception as e:  # noqa: BLE001 — per-type tolerance: classify, don't abort
        return [], e


def _enumerate_foldered(
    client: SoapClient, inner: str, folder_type: str, members: dict[str, list[str]], skip: SkipLog
) -> None:
    """Two-step folder enumeration for one inner type, fault-tolerant."""
    folders, err = _try_list(client, folder_type)
    if err is not None:
        skip.add(type=inner, bucket=classify_skip_bucket(str(err)), detail=str(err))
        return
    folder_names = set(folders) | set(SYNTHETIC_FOLDERS.get(inner, ()))
    if folders:
        # The folder objects are themselves retrievable metadata.
        members[folder_type] = sorted(set(folders))
    collected: list[str] = []
    first_err: Exception | None = None
    for f in sorted(folder_names):
        items, ferr = _try_list(client, inner, folder=f)
        if ferr is not None:
            first_err = first_err or ferr
            continue
        collected.extend(items)
    if collected:
        members[inner] = sorted(set(collected))
    elif first_err is not None:
        skip.add(type=inner, bucket=classify_skip_bucket(str(first_err)), detail=str(first_err))


def enumerate_all_members(client: SoapClient) -> tuple[dict[str, list[str]], SkipLog]:
    """Return ``({type: [fullName, ...]}, SkipLog)`` for every available,
    non-DENY type the identity can list. Per-type failures are recorded in the
    SkipLog rather than aborting."""
    meta = describe_metadata(client)
    described = {obj["xmlName"] for obj in meta}
    members: dict[str, list[str]] = {}
    skip = SkipLog()

    # Foldered types (two-step), skipping denied ones (e.g. Document).
    for inner, folder_type in FOLDERED.items():
        if inner in DENY:
            continue
        _enumerate_foldered(client, inner, folder_type, members, skip)

    # Non-foldered types: describe output unioned with always-probe types.
    candidates = (described | set(ALWAYS_PROBE_TYPES)) - set(FOLDERED) - DENY
    for tname in sorted(candidates):
        items, err = _try_list(client, tname)
        if err is not None:
            skip.add(type=tname, bucket=classify_skip_bucket(str(err)), detail=str(err))
        elif items:
            members[tname] = sorted(set(items))

    return members, skip
