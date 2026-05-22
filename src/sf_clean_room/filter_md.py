"""Apply the source-controlled deny list to the enumeration result.

This is a defence-in-depth filter: ``enumerate_all_members`` already skips
DENY types during listing, but applying the filter again at the boundary keeps
the invariant explicit and makes the count of excluded components auditable.
"""
from __future__ import annotations

from dataclasses import dataclass

from sf_clean_room.constants import DENY


@dataclass(frozen=True)
class FilterResult:
    kept: dict[str, list[str]]
    excluded_counts: dict[str, int]  # type -> count, for audit log

    @property
    def excluded_total(self) -> int:
        return sum(self.excluded_counts.values())


def apply_deny_list(members_by_type: dict[str, list[str]]) -> FilterResult:
    kept: dict[str, list[str]] = {}
    excluded: dict[str, int] = {}
    for tname, mems in members_by_type.items():
        if tname in DENY:
            excluded[tname] = len(mems)
        else:
            kept[tname] = list(mems)
    return FilterResult(kept=kept, excluded_counts=excluded)
