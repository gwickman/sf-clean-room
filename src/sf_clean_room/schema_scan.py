"""Schema scan: describe in-scope objects, classify each field, write the scan.

Read-only and value-free: only field *metadata* is fetched (`sf sobject
describe`), never row data. Admin-authored free text that flows into the scan
(labels, help text, formula expressions) is sanitised in flight — angle
brackets stripped, whitespace collapsed, length capped — so the scan cannot
carry markup or sprawling text.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sf_clean_room.classify import FieldMeta, Recommendation, classify_field

_WS_RE = re.compile(r"\s+")
_SANITISE_MAX = 500


def sanitise(text: str) -> str:
    """Strip angle brackets, collapse whitespace, cap length."""
    if not text:
        return ""
    cleaned = text.replace("<", "").replace(">", "")
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    if len(cleaned) > _SANITISE_MAX:
        cleaned = cleaned[:_SANITISE_MAX] + "..."
    return cleaned


@dataclass(frozen=True)
class ScannedField:
    object_name: str
    meta: FieldMeta
    recommendation: Recommendation


# A describe function takes (alias, object_name) and returns the raw list of
# field dicts (as `sf sobject describe` returns under result.fields). Injected
# so the scan is testable without a live org.
DescribeFn = Callable[[str, str], list[dict]]


def describe_object_sf(alias: str, object_name: str) -> list[dict]:
    from sf_clean_room.sfcli import run_cli_json, which_cli

    exe, flavor = which_cli()
    if flavor == "sf":
        cmd = [exe, "sobject", "describe", "--sobject", object_name,
               "--target-org", alias, "--json"]
    else:
        cmd = [exe, "force:schema:sobject:describe", "-s", object_name, "-u", alias, "--json"]
    data = run_cli_json(cmd)
    res = data.get("result", data)
    return list(res.get("fields") or [])


def scan_object(alias: str, object_name: str, describe_fn: DescribeFn) -> list[ScannedField]:
    out: list[ScannedField] = []
    for raw in describe_fn(alias, object_name):
        meta = FieldMeta.from_describe(raw)
        if not meta.name:
            continue
        meta = FieldMeta(
            name=meta.name,
            label=sanitise(meta.label),
            type=meta.type,
            length=meta.length,
            custom=meta.custom,
            calculated=meta.calculated,
            formula=sanitise(meta.formula),
            help_text=sanitise(meta.help_text),
        )
        out.append(ScannedField(object_name, meta, classify_field(meta)))
    return out


def scan_objects(
    alias: str, objects: list[str], describe_fn: DescribeFn = describe_object_sf
) -> dict[str, list[ScannedField]]:
    return {obj: scan_object(alias, obj, describe_fn) for obj in objects}


def write_schema_csv(scan: dict[str, list[ScannedField]], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "object", "field", "type", "length", "custom", "calculated",
            "recommended_action", "special_category", "reason",
        ])
        for obj, fields in scan.items():
            for sf in fields:
                m, r = sf.meta, sf.recommendation
                w.writerow([
                    obj, m.name, m.type, m.length, m.custom, m.calculated,
                    r.action, r.special_category, r.reason,
                ])
