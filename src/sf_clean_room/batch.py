"""Weight-aware batching for retrieve.

Each batch respects two ceilings:

* component count — Salesforce hard limit is 10,000 per retrieve;
* total weight — proxy for compressed-zip size; targets the ~600 MB cap.

The deny list excludes the heaviest binary types, so most runs produce a
single batch. The batcher exists to make multi-batch runs correct, not to be
the common path.
"""
from __future__ import annotations

from dataclasses import dataclass

from sf_clean_room.constants import (
    MAX_COMPONENTS_PER_BATCH,
    MAX_WEIGHT_PER_BATCH,
    weight_for,
)


@dataclass(frozen=True)
class BatchChunk:
    type_name: str
    members: list[str]

    @property
    def count(self) -> int:
        return len(self.members)

    @property
    def weight(self) -> int:
        return self.count * weight_for(self.type_name)


@dataclass(frozen=True)
class Batch:
    chunks: list[BatchChunk]

    @property
    def total_count(self) -> int:
        return sum(c.count for c in self.chunks)

    @property
    def total_weight(self) -> int:
        return sum(c.weight for c in self.chunks)


def build_batches(
    members_by_type: dict[str, list[str]],
    max_components: int = MAX_COMPONENTS_PER_BATCH,
    max_weight: int = MAX_WEIGHT_PER_BATCH,
) -> list[Batch]:
    """Split members into batches respecting BOTH the count and weight ceilings.

    Iteration order over types is deterministic (sorted by name) so two runs
    against the same enumeration produce identical batch plans.
    """
    if max_components <= 0:
        raise ValueError("max_components must be positive")
    if max_weight <= 0:
        raise ValueError("max_weight must be positive")

    batches: list[Batch] = []
    current: list[BatchChunk] = []
    current_count = 0
    current_weight = 0

    def flush() -> None:
        nonlocal current, current_count, current_weight
        if current:
            batches.append(Batch(chunks=current))
            current = []
            current_count = 0
            current_weight = 0

    for tname in sorted(members_by_type.keys()):
        mems = members_by_type[tname]
        if not mems:
            continue
        weight_per_item = weight_for(tname)
        i = 0
        while i < len(mems):
            remaining_count = max_components - current_count
            remaining_weight = max_weight - current_weight
            if remaining_count <= 0 or remaining_weight <= 0:
                flush()
                remaining_count = max_components
                remaining_weight = max_weight
            # At least one item per chunk, even if the item alone exceeds the
            # weight ceiling — we cannot subdivide a component.
            max_by_weight = max(1, remaining_weight // max(weight_per_item, 1))
            take = min(max_by_weight, remaining_count, len(mems) - i)
            current.append(BatchChunk(type_name=tname, members=list(mems[i : i + take])))
            current_count += take
            current_weight += take * weight_per_item
            i += take
            if current_count >= max_components or current_weight >= max_weight:
                flush()

    flush()
    return batches


def describe_plan(batches: list[Batch]) -> str:
    """Human/agent-readable summary; used by --dry-run and by the audit log."""
    if not batches:
        return "no components after filtering"
    lines: list[str] = [f"{len(batches)} batch(es) planned:"]
    grand_count = 0
    grand_weight = 0
    for i, b in enumerate(batches, 1):
        grand_count += b.total_count
        grand_weight += b.total_weight
        lines.append(
            f"  batch {i}: {b.total_count} components, weight {b.total_weight:,}, "
            f"{len(b.chunks)} type-chunk(s)"
        )
        for c in b.chunks:
            lines.append(f"    {c.type_name}: {c.count} (weight {c.weight:,})")
    lines.append(f"  totals: {grand_count} components, weight {grand_weight:,}")
    return "\n".join(lines)
