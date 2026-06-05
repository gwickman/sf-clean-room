"""Shared helpers for shelling out to the locally authenticated ``sf``/``sfdx`` CLI.

The tool never handles credentials itself; it invokes whichever CLI flavour is
on PATH and reads the OAuth session already negotiated for an alias. Every
subprocess call forces UTF-8 decoding (Windows cp1252 mojibake guard) and
disables telemetry/colour so output is clean and parseable.

This module is read-only with respect to Salesforce: callers issue ``org
display``, ``sobject describe``, and ``data query`` only. There is no write
path here by construction.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

_ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


class SfCliError(RuntimeError):
    pass


def which_cli() -> tuple[str, str]:
    """Return ``(path, flavour)`` for the first of ``sf``/``sfdx`` on PATH."""
    for exe, flavor in (("sf", "sf"), ("sfdx", "sfdx")):
        p = shutil.which(exe)
        if p:
            return p, flavor
    raise SfCliError(
        "Salesforce CLI not found on PATH. Install sf or sfdx and authenticate first."
    )


def _hardened_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "SF_DISABLE_TELEMETRY": "true",
            "SFDX_DISABLE_TELEMETRY": "true",
            "SF_LOG_LEVEL": "error",
            "SFDX_JSON_TO_STDOUT": "true",
            "FORCE_COLOR": "0",
        }
    )
    return env


def run_cli_text(cmd: list[str], timeout: int | None = None) -> str:
    """Run an ``sf`` command and return its raw stdout (UTF-8, ANSI-stripped).

    Raises ``SfCliError`` on a non-zero exit, surfacing stderr so the operator
    can see why.
    """
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_hardened_env(),
        check=False,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise SfCliError(
            f"Salesforce CLI failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"STDERR:\n{(proc.stderr or '').strip()}"
        )
    return proc.stdout or ""


def run_cli_json(cmd: list[str], timeout: int | None = None) -> dict[str, Any]:
    """Run an ``sf`` command and parse its stdout as a single JSON object.

    Tolerates a BOM, ANSI escapes, and leading warning chatter by slicing to
    the outermost ``{ ... }``.
    """
    out = run_cli_text(cmd, timeout=timeout)
    cleaned = _ANSI_RE.sub("", out.lstrip("﻿"))
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        cleaned = cleaned[first : last + 1]
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError as e:
        raise SfCliError(f"Salesforce CLI returned non-JSON output: {cleaned[:400]}") from e
