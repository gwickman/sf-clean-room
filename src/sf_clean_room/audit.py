"""Per-run audit log.

Plain text, one file per run, written to a fixed system location. Append-only
at the filesystem level (each run is a new file); the tool does not rotate.

The log can also tee its milestone writes to a stream (typically ``sys.stderr``)
so an operator running the tool interactively sees real-time progress. The
tee'd output is the same content as the file, minus the timestamp prefix.
Verbose forensic content (e.g. the full batch plan) goes to the file only,
via ``write_file_only``.
"""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

from sf_clean_room.paths import default_log_dir


def _utc_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def log_path_for(org_alias: str, log_dir: Path | None = None) -> Path:
    base = (log_dir if log_dir is not None else default_log_dir()).resolve()
    base.mkdir(parents=True, exist_ok=True)
    safe_alias = "".join(c if c.isalnum() or c in "-_." else "_" for c in org_alias)
    return base / f"{_utc_stamp()}-{safe_alias}.log"


class AuditLog:
    def __init__(self, fh: TextIO, path: Path, tee_stream: TextIO | None = None) -> None:
        self._fh = fh
        self._tee = tee_stream
        self.path = path

    def _file(self, line: str) -> None:
        ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        self._fh.write(f"[{ts}] {line}\n")
        self._fh.flush()

    def write(self, line: str) -> None:
        """Write a milestone line to the log file and (if configured) the tee stream."""
        self._file(line)
        if self._tee is not None:
            self._tee.write(f"{line}\n")
            self._tee.flush()

    def section(self, title: str) -> None:
        header = f"\n=== {title} ===\n"
        self._fh.write(header)
        self._fh.flush()
        if self._tee is not None:
            self._tee.write(header)
            self._tee.flush()

    def write_file_only(self, line: str) -> None:
        """Write forensic content to the file only — not echoed to the tee stream."""
        self._file(line)


@contextmanager
def audit_log(
    org_alias: str,
    log_dir: Path | None = None,
    tee_stream: TextIO | None = None,
) -> Iterator[AuditLog]:
    path = log_path_for(org_alias, log_dir=log_dir)
    with open(path, "w", encoding="utf-8") as fh:
        log = AuditLog(fh, path, tee_stream=tee_stream)
        log.write(f"audit log opened for org_alias={org_alias}")
        try:
            yield log
        finally:
            log.write("audit log closed")
