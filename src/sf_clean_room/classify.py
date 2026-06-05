"""Field classifier — the recommendation engine for ``get_records``.

Reads one field's ``Describe`` metadata and recommends an action with a reason.
Rules are applied in order; first match wins. The recommendation is a default a
reviewed plan may override (see ``plan.py``); the classifier never aborts — an
ambiguous field gets the conservative recommendation and a reason that says so
(principle B2).
"""
from __future__ import annotations

from dataclasses import dataclass

from sf_clean_room.constants import (
    DROP,
    ESSAY_NAME_PATTERNS,
    ESSAY_NAMED_LEN,
    ESSAY_TEXTAREA_LEN,
    FORMULA_LEAK_SOURCES,
    HASH_EMAIL,
    HASH_ID,
    IDENTIFIER_PATTERNS,
    PASS,
    PII_DIRECT_PATTERNS,
    PII_SPECIAL_PATTERNS,
    RAW,
)

_JIGSAW = {"jigsaw", "jigsawcompanyid", "jigsawcontactid"}
# Text-bearing field types: the name-based email rule applies only to these, so a
# boolean/date/number field merely mentioning "email" is not hashed.
_TEXTY = {"string", "textarea", "url", ""}
# Any PII-shape pattern, used by the conservative fallback.
_ALL_PII_PATTERNS = PII_DIRECT_PATTERNS + PII_SPECIAL_PATTERNS


@dataclass(frozen=True)
class FieldMeta:
    name: str
    label: str = ""
    type: str = ""
    length: int = 0
    custom: bool = False
    calculated: bool = False
    formula: str = ""
    help_text: str = ""

    @classmethod
    def from_describe(cls, d: dict) -> "FieldMeta":
        return cls(
            name=str(d.get("name") or ""),
            label=str(d.get("label") or ""),
            type=str(d.get("type") or "").lower(),
            length=int(d.get("length") or 0),
            custom=bool(d.get("custom")),
            calculated=bool(d.get("calculated")),
            formula=str(d.get("calculatedFormula") or ""),
            help_text=str(d.get("inlineHelpText") or ""),
        )

    @property
    def haystack(self) -> str:
        return f"{self.name}\n{self.label}\n{self.help_text}".lower()


@dataclass(frozen=True)
class Recommendation:
    action: str
    reason: str
    special_category: bool = False


def _matches(haystack: str, patterns: tuple[str, ...]) -> str | None:
    for p in patterns:
        if p in haystack:
            return p
    return None


def _formula_leak_source(formula: str) -> str | None:
    low = formula.lower()
    for src in FORMULA_LEAK_SOURCES:
        if src.lower() in low:
            return src
    return None


def classify_field(meta: FieldMeta) -> Recommendation:
    name_l = meta.name.lower()
    hay = meta.haystack

    # 1. RAW — Salesforce intra-system IDs and references.
    if meta.type in ("id", "reference"):
        return Recommendation(RAW, f"Salesforce {meta.type} (intra-system, no external re-id power)")
    if name_l in _JIGSAW:
        return Recommendation(RAW, "Jigsaw/Data.com opaque foreign id")

    # 2. DROP — special-category data (GDPR Art. 9). Tagged so the plan can
    #    enforce the justification requirement on any keep-override.
    sp = _matches(hay, PII_SPECIAL_PATTERNS)
    if sp:
        return Recommendation(DROP, f"special-category data (matched '{sp}')", special_category=True)

    # 3. DROP — direct PII, plus the standard person/household/company Name.
    if meta.name == "Name":
        return Recommendation(DROP, "standard Name field (person/household/company name)")
    direct = _matches(hay, PII_DIRECT_PATTERNS)
    if direct:
        return Recommendation(DROP, f"direct PII (matched '{direct}')")

    # 4. DROP — free-text essays.
    if meta.type == "textarea" and meta.length >= ESSAY_TEXTAREA_LEN:
        return Recommendation(DROP, f"long free-text (textarea length {meta.length} >= {ESSAY_TEXTAREA_LEN})")
    essay = _matches(hay, ESSAY_NAME_PATTERNS)
    if essay and meta.length >= ESSAY_NAMED_LEN:
        return Recommendation(DROP, f"free-text essay shape (matched '{essay}', length {meta.length})")

    # 5. DROP — formula-leak (calculated field whose formula references PII).
    if meta.calculated and meta.formula:
        leak = _formula_leak_source(meta.formula)
        if leak:
            return Recommendation(DROP, f"formula references PII source '{leak}'")

    # 6. HASH_EMAIL — any email field. The name-based rule only applies to
    #    text-bearing fields, so boolean/date/number fields that merely mention
    #    "email" (e.g. HasOptedOutOfEmail, EmailBouncedDate) keep their analytical
    #    value rather than being hashed into noise.
    if meta.type == "email":
        note = "" if "email" in hay else " (type=email though name lacks 'email')"
        return Recommendation(HASH_EMAIL, f"email field{note}")
    if "email" in hay and meta.type in _TEXTY:
        return Recommendation(HASH_EMAIL, "text field whose name/label indicates email")

    # 7. HASH_ID — externally-meaningful identifiers.
    ident = _matches(hay, IDENTIFIER_PATTERNS)
    if ident:
        return Recommendation(HASH_ID, f"externally-meaningful identifier (matched '{ident}')")

    # 8. Conservative fallback / PASS.
    leftover = _matches(hay, _ALL_PII_PATTERNS)
    if leftover:
        return Recommendation(DROP, f"conservative default: PII-shaped name (matched '{leftover}')")
    return Recommendation(PASS, "non-identifying analytical signal")
