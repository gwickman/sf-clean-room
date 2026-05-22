"""Scrub stage contract.

v1 ships with a single no-op stage so the orchestration code and the stage
contract exist from day one. Future stages (secret scanner, filename-shape
detector, PII hasher) implement the same protocol.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Finding:
    path: str       # relative to the temp dir
    category: str   # "secret", "pii", etc.
    detail: str


@dataclass(frozen=True)
class StageResult:
    stage_name: str
    findings: list[Finding]

    @property
    def clean(self) -> bool:
        return not self.findings


class ScrubStage(Protocol):
    name: str

    def run(self, temp_dir: Path) -> StageResult: ...


class NoopStage:
    """Always clean. Placeholder until real scanners land."""
    name = "noop"

    def run(self, temp_dir: Path) -> StageResult:
        return StageResult(stage_name=self.name, findings=[])


def default_stages() -> list[ScrubStage]:
    return [NoopStage()]


def run_stages(temp_dir: Path, stages: list[ScrubStage]) -> list[StageResult]:
    return [s.run(temp_dir) for s in stages]
