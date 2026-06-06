"""Per-run record of metadata types skipped or partially retrieved.

Shared by the enumerator (per-type errors), the retrieve stage (partial
retrieves), and the publisher. Two output faces:

* ``write_csv`` — the PUBLISHED ``_skipped-types.csv``: ``type,bucket,
  components_requested,components_retrieved``. **No verbatim detail column** —
  diagnostic detail stays in the audit log (v1 §9; design §3.6).
* ``audit_lines`` — full (truncated) detail for the audit log only.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from sf_clean_room.constants import MAX_SKIP_DETAIL_LEN, SKIP_BUCKETS

CSV_HEADER = ("type", "bucket", "components_requested", "components_retrieved")


@dataclass(frozen=True)
class SkipRecord:
    type: str
    bucket: str
    detail: str = ""                       # verbatim message — audit log only
    components_requested: int | None = None
    components_retrieved: int | None = None


class SkipLog:
    def __init__(self) -> None:
        self._records: list[SkipRecord] = []

    def add(
        self,
        *,
        type: str,
        bucket: str,
        detail: str = "",
        requested: int | None = None,
        retrieved: int | None = None,
    ) -> None:
        if bucket not in SKIP_BUCKETS:
            raise ValueError(f"unknown skip bucket {bucket!r}; expected one of {SKIP_BUCKETS}")
        d = detail or ""
        if len(d) > MAX_SKIP_DETAIL_LEN:
            d = d[:MAX_SKIP_DETAIL_LEN] + "..."
        self._records.append(
            SkipRecord(
                type=type,
                bucket=bucket,
                detail=d,
                components_requested=requested,
                components_retrieved=retrieved,
            )
        )

    def __iter__(self):
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def bucket_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self._records:
            out[r.bucket] = out.get(r.bucket, 0) + 1
        return out

    def write_csv(self, path: Path) -> None:
        """Write the published skip log. Always written, header even if empty.
        Detail is deliberately NOT included (design §3.6)."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(CSV_HEADER)
            for r in sorted(self._records, key=lambda x: (x.bucket, x.type)):
                w.writerow([
                    r.type,
                    r.bucket,
                    "" if r.components_requested is None else r.components_requested,
                    "" if r.components_retrieved is None else r.components_retrieved,
                ])

    def audit_lines(self) -> list[str]:
        """Full per-skip detail, for the audit log only (not published)."""
        lines: list[str] = []
        for r in sorted(self._records, key=lambda x: (x.bucket, x.type)):
            extra = ""
            if r.bucket == "partial_retrieve":
                extra = f" (requested={r.components_requested}, retrieved={r.components_retrieved})"
            detail = f": {r.detail}" if r.detail else ""
            lines.append(f"skip {r.type} [{r.bucket}]{extra}{detail}")
        return lines
