"""Build SOQL, run the query, transform values in flight, write the artefacts.

The raw query result lives only in this module's process memory; only the
post-classification TSV is written to disk. DROP fields are never selected.
HASH/DERIVE are applied before any value reaches a file.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Callable

from sf_clean_room.constants import (
    DERIVE,
    DROP,
    HASH_EMAIL,
    HASH_ID,
    PASS,
    RAW,
)
from sf_clean_room.hashing import hash_email, hash_id
from sf_clean_room.plan import Effective, Plan, resolve
from sf_clean_room.schema_scan import ScannedField

# A query function takes (alias, soql) and returns the list of record dicts.
QueryFn = Callable[[str, str], list[dict]]

_FORBIDDEN_WHERE = (
    "insert", "update", "delete", "merge", "upsert",
    "create", "drop", "alter", "truncate",
    "limit", "offset",
)
_SELECT_LEN_CEILING = 95_000  # SOQL hard limit is ~100k chars; leave headroom.


class WhereError(ValueError):
    pass


class ExtractError(RuntimeError):
    pass


def validate_where(predicate: str) -> str:
    """Validate a ``--where`` predicate. Returns the stripped predicate or raises."""
    p = (predicate or "").strip()
    if not p:
        raise WhereError("--where predicate is empty")
    if ";" in p:
        raise WhereError("--where must not contain ';' (no statement chaining)")
    if "--" in p or "/*" in p or "*/" in p:
        raise WhereError("--where must not contain SQL comment markers")
    low = p.lower()
    for verb in _FORBIDDEN_WHERE:
        if re.search(rf"\b{verb}\b", low):
            raise WhereError(f"--where must not contain '{verb}'")
    return p


def build_soql(object_name: str, select_fields: list[str], where: str | None) -> str:
    if not select_fields:
        # Always have at least Id so the query is valid even if everything else dropped.
        select_fields = ["Id"]
    select = ", ".join(select_fields)
    soql = f"SELECT {select} FROM {object_name}"
    if where:
        soql += f" WHERE {where}"
    if len(soql) > _SELECT_LEN_CEILING:
        raise ExtractError(
            f"{object_name}: SOQL exceeds the safe length ({len(soql)} chars). "
            f"Narrow scope with --only / fewer kept fields."
        )
    return soql


# ----- DERIVE recipes (auto-inferred from field name) -----

def _infer_derive_recipe(field_name: str) -> str | None:
    n = field_name.lower()
    if any(t in n for t in ("postcode", "postal", "zip")):
        return "uk_postcode_outcode"
    if "birth" in n or "dob" in n:
        return "year_of_birth"
    return None


def _derive(value: str | None, recipe: str) -> str:
    if not value:
        return ""
    v = value.strip()
    if recipe == "uk_postcode_outcode":
        return v.upper().split(" ")[0] if " " in v else v.upper()
    if recipe == "year_of_birth":
        m = re.match(r"\s*(\d{4})", v)
        return m.group(1) if m else ""
    return ""


def transform_value(action: str, value, field_name: str) -> str:
    # sf data query --json returns typed scalars (bool/int/float) and nulls.
    # Normalise to str|None so the hash/derive recipes never see a non-string.
    sval = None if value is None else str(value)
    if action == HASH_EMAIL:
        return hash_email(sval)
    if action == HASH_ID:
        return hash_id(sval)
    if action == DERIVE:
        recipe = _infer_derive_recipe(field_name)
        return _derive(sval, recipe) if recipe else ""
    # RAW / PASS
    return sval if sval is not None else ""


@dataclass
class ObjectResult:
    object_name: str
    columns: list[str]
    rows_out: int
    action_counts: dict[str, int]
    downgraded: list[str]
    drift: list[str]
    audit_rows: list[list[str]] = dc_field(default_factory=list)


def _column_fields(obj: str, fields: list[ScannedField], plan: Plan | None) -> list[tuple[ScannedField, Effective]]:
    """Resolve effective actions; return the fields that become TSV columns
    (everything except DROP, and DERIVE only when a recipe is inferable)."""
    out: list[tuple[ScannedField, Effective]] = []
    for sf in fields:
        eff = resolve(obj, sf, plan)
        if eff.action == DROP:
            continue
        if eff.action == DERIVE and _infer_derive_recipe(sf.meta.name) is None:
            continue  # no recipe → treat as drop (safe); recorded in audit below
        out.append((sf, eff))
    return out


def extract_object(
    alias: str,
    obj: str,
    fields: list[ScannedField],
    plan: Plan | None,
    where: str | None,
    out_dir: Path,
    query_fn: QueryFn,
) -> ObjectResult:
    column_pairs = _column_fields(obj, fields, plan)
    select_fields = [sf.meta.name for sf, _ in column_pairs]
    columns = list(select_fields)

    soql = build_soql(obj, select_fields, where)
    records = query_fn(alias, soql)

    tsv_path = out_dir / f"{obj}.tsv"
    rows_out = 0
    with open(tsv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        w.writerow(columns)
        for rec in records:
            row = [transform_value(eff.action, rec.get(sf.meta.name), sf.meta.name)
                   for sf, eff in column_pairs]
            w.writerow(row)
            rows_out += 1

    # Audit + stats over ALL fields (including dropped ones).
    action_counts: dict[str, int] = {}
    downgraded: list[str] = []
    drift: list[str] = []
    audit_rows: list[list[str]] = []
    for sf in fields:
        eff = resolve(obj, sf, plan)
        recipe = _infer_derive_recipe(sf.meta.name) if eff.action == DERIVE else ""
        # A DERIVE with no recipe is effectively dropped.
        effective_action = eff.action
        if eff.action == DERIVE and not recipe:
            effective_action = DROP
        action_counts[effective_action] = action_counts.get(effective_action, 0) + 1
        if eff.downgraded:
            downgraded.append(sf.meta.name)
        if plan is not None and not plan.is_known(obj, sf.meta.name):
            drift.append(sf.meta.name)
        audit_rows.append([
            obj, sf.meta.name, sf.meta.type, effective_action, recipe or "",
            eff.source, str(eff.special_category), str(eff.downgraded), eff.reason,
        ])

    return ObjectResult(
        object_name=obj,
        columns=columns,
        rows_out=rows_out,
        action_counts=action_counts,
        downgraded=downgraded,
        drift=drift,
        audit_rows=audit_rows,
    )


AUDIT_SENTINEL = "_field-handling-applied.csv"
SUMMARY_NAME = "_extract-summary.json"


def write_audit_csv(results: list[ObjectResult], where: str | None, path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "object", "field", "type", "action", "recipe",
            "source", "special_category", "downgraded", "reason",
        ])
        for r in results:
            for row in r.audit_rows:
                w.writerow(row)
        if where:
            # Self-describing record of the narrowing predicate.
            w.writerow(["*", "__where__", "", "WHERE", "", "operator", "False", "False", where])


def write_summary_json(results: list[ObjectResult], where: str | None, path: Path) -> None:
    summary = {
        "where_clause": where,
        "objects": {
            r.object_name: {
                "rows_out": r.rows_out,
                "columns": r.columns,
                "action_counts": r.action_counts,
                "downgraded_special_category": r.downgraded,
                "drift_fields": r.drift,
            }
            for r in results
        },
    }
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def query_records_sf(alias: str, soql: str) -> list[dict]:
    from sf_clean_room.sfcli import run_cli_json, which_cli

    exe, flavor = which_cli()
    if flavor == "sf":
        cmd = [exe, "data", "query", "--query", soql, "--target-org", alias, "--json"]
    else:
        cmd = [exe, "force:data:soql:query", "-q", soql, "-u", alias, "--json"]
    data = run_cli_json(cmd)
    res = data.get("result", data)
    out: list[dict] = []
    for rec in res.get("records") or []:
        out.append({k: v for k, v in rec.items() if k != "attributes"})
    return out
