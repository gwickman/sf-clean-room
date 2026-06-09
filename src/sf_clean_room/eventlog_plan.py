"""Classification plan for get_event_logs.

Event-log column names are consistent across EventTypes, so overrides are
column-global: ``[overrides].<COLUMN> = <action>`` applies wherever that column
appears. ``[scope].event_types`` narrows which EventTypes are pulled.

An override that *increases exposure* over the classifier default (e.g. keeping a
DROP content column, or passing a raw IP the classifier would DERIVE) requires a
justification in ``[reasons].<COLUMN>``; without one it is downgraded to the safe
default and reported — the special-category rule from get_records, generalised.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from sf_clean_room.eventlog_classify import DERIVE, DROP, HASH, PASS, RAW, classify_column

KEEP = "KEEP"  # override alias for "keep raw" -> PASS
OVERRIDE_ACTIONS = frozenset({RAW, HASH, PASS, DROP, KEEP})

# Exposure ranking: higher = more of the raw value revealed.
_EXPOSURE = {DROP: 0, DERIVE: 1, HASH: 2, RAW: 3, PASS: 3}


class EventLogPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class EventLogPlan:
    event_types: list[str]
    overrides: dict[str, str]   # COLUMN -> action
    reasons: dict[str, str]     # COLUMN -> justification


@dataclass(frozen=True)
class Effective:
    action: str
    recipe: str
    source: str       # "default" | "override"
    downgraded: bool


def load_plan(path: Path) -> EventLogPlan:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise EventLogPlanError(f"plan file is not valid TOML: {path}: {e}") from e
    event_types = [str(t) for t in data.get("scope", {}).get("event_types", [])]
    overrides = {str(k).upper(): str(v).upper() for k, v in (data.get("overrides", {}) or {}).items()}
    for col, act in overrides.items():
        if act not in OVERRIDE_ACTIONS:
            raise EventLogPlanError(
                f"override {col} = {act!r} is not a valid action (one of {sorted(OVERRIDE_ACTIONS)})"
            )
    reasons = {str(k).upper(): str(v) for k, v in (data.get("reasons", {}) or {}).items()}
    return EventLogPlan(event_types=event_types, overrides=overrides, reasons=reasons)


def resolve(col: str, plan: EventLogPlan | None) -> Effective:
    default_action, recipe = classify_column(col)
    if plan is None:
        return Effective(default_action, recipe, "default", False)
    ov = plan.overrides.get(col.strip().upper())
    if ov is None:
        return Effective(default_action, recipe, "default", False)
    action = PASS if ov == KEEP else ov
    # More-exposing override needs a recorded justification.
    if _EXPOSURE[action] > _EXPOSURE[default_action] and not plan.reasons.get(col.strip().upper()):
        return Effective(default_action, recipe, "override", True)
    return Effective(action, "" if action != DERIVE else recipe, "override", False)


def emit_plan(columns_by_type: dict[str, list[str]]) -> str:
    """Annotated, editable plan from the columns seen per EventType."""
    types = sorted(columns_by_type)
    lines = [
        "# sf-clean-room get_event_logs - classification plan",
        "# Edit [scope].event_types / [overrides].<COLUMN> / [reasons].<COLUMN>, then run without --dry-run.",
        "# Override actions: RAW, HASH, PASS, DROP, KEEP (=keep raw).",
        "# A more-exposing override (e.g. keeping a DROP column) needs a [reasons] entry, else it stays the safe default.",
        "",
        "[scope]",
        "event_types = [" + ", ".join(f'"{t}"' for t in types) + "]",
        "",
        "# Recommended classification per column (informational; re-derived each run):",
    ]
    seen: dict[str, str] = {}
    for t in types:
        for col in columns_by_type[t]:
            action, recipe = classify_column(col)
            tag = f"{action}" + (f"/{recipe}" if recipe else "")
            seen.setdefault(col, tag)
    for col in sorted(seen):
        lines.append(f"#   {col:<32} {seen[col]}")
    lines += ["", "[overrides]", "", "[reasons]", ""]
    return "\n".join(lines)
