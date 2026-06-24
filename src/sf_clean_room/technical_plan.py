"""Classification plan for get_technical_objects.

Unlike event-log overrides (which are column-global), technical-object overrides
are per ``"Object.Field"`` key because the same field name can have different
semantics across objects.

  [scope]
  objects = ["ApexClass", "LoginHistory", ...]

  [overrides]
  "LoginHistory.UserId" = "RAW"
  "FlowInterview.InterviewLabel" = "PASS"

  [reasons]
  "FlowInterview.InterviewLabel" = "confirmed no customer data in this org"

An override that increases exposure over the classifier default (e.g. PASS for a
field the classifier would DROP) requires a recorded justification in ``[reasons]``;
without one it is silently downgraded to the safe default and the downgrade is
reported.  The run does not abort (B2 — forcing a human decision is an anti-pattern).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from sf_clean_room.technical_classify import (
    DERIVE,
    DROP,
    HASH,
    PASS,
    RAW,
    FieldMeta,
    classify_field,
)

KEEP = "KEEP"
OVERRIDE_ACTIONS = frozenset({RAW, HASH, PASS, DROP, DERIVE, KEEP})

# Exposure ranking: higher = more of the raw value revealed to the operator.
_EXPOSURE = {DROP: 0, DERIVE: 1, HASH: 2, RAW: 3, PASS: 3}


class TechnicalPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class TechnicalPlan:
    objects: list[str]           # empty = all catalogue objects
    overrides: dict[str, str]    # "Object.Field" -> action
    reasons: dict[str, str]      # "Object.Field" -> justification


@dataclass(frozen=True)
class Effective:
    action: str
    recipe: str
    source: str       # "default" | "override"
    downgraded: bool


def load_plan(path: Path) -> TechnicalPlan:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise TechnicalPlanError(f"plan file is not valid TOML: {path}: {e}") from e
    objects = [str(o) for o in data.get("scope", {}).get("objects", [])]
    raw_overrides = data.get("overrides", {}) or {}
    overrides = {str(k): str(v).upper() for k, v in raw_overrides.items()}
    for key, act in overrides.items():
        if act not in OVERRIDE_ACTIONS:
            raise TechnicalPlanError(
                f"override {key!r} = {act!r} is not a valid action "
                f"(one of {sorted(OVERRIDE_ACTIONS)})"
            )
    reasons = {str(k): str(v) for k, v in (data.get("reasons", {}) or {}).items()}
    return TechnicalPlan(objects=objects, overrides=overrides, reasons=reasons)


def resolve(object_name: str, meta: FieldMeta, plan: TechnicalPlan | None) -> Effective:
    """Return the effective classification for one field, accounting for any plan override."""
    default_action, recipe = classify_field(object_name, meta)
    if plan is None:
        return Effective(default_action, recipe, "default", False)
    key = f"{object_name}.{meta.name}"
    ov = plan.overrides.get(key)
    if ov is None:
        return Effective(default_action, recipe, "default", False)
    action = PASS if ov == KEEP else ov
    # More-exposing override without a justification is silently downgraded.
    if _EXPOSURE[action] > _EXPOSURE[default_action] and not plan.reasons.get(key):
        return Effective(default_action, recipe, "override", True)
    # For DERIVE overrides, preserve the original recipe from the classifier.
    effective_recipe = recipe if action == DERIVE else ""
    return Effective(action, effective_recipe, "override", False)


def emit_plan(fields_by_object: dict[str, list[FieldMeta]]) -> str:
    """Return an annotated, editable plan TOML string from per-object field lists."""
    objects = sorted(fields_by_object)
    lines = [
        "# sf-clean-room get_technical_objects - classification plan",
        "# Edit [scope].objects / [overrides] / [reasons], then run without --dry-run.",
        "# Override actions: RAW, HASH, PASS, DROP, DERIVE, KEEP (=keep raw).",
        "# A more-exposing override needs a [reasons] entry, else it stays the safe default.",
        "",
        "[scope]",
        "objects = [" + ", ".join(f'"{o}"' for o in objects) + "]",
        "",
        "# Recommended classification per field (informational; re-derived each run):",
    ]
    for obj in objects:
        lines.append(f"#")
        lines.append(f"# {obj}:")
        for meta in fields_by_object[obj]:
            action, recipe = classify_field(obj, meta)
            tag = f"{action}" + (f"/{recipe}" if recipe else "")
            lines.append(f"#   {meta.name:<42} {tag}")
    lines += [
        "",
        "[overrides]",
        '# "Object.Field" = "ACTION"',
        "",
        "[reasons]",
        '# "Object.Field" = "justification text"',
        "",
    ]
    return "\n".join(lines)
