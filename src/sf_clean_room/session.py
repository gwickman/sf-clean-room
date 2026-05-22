"""Resolve a Salesforce session via the locally authenticated sf/sfdx CLI.

The tool does not handle credentials itself; it shells out to whichever CLI
flavour is on PATH and reads the OAuth access token already negotiated for the
given alias or username.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

_ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


class SessionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Session:
    session_id: str
    instance_url: str
    org_id: str
    username: str
    alias: str
    api_version: str


def _which_cli() -> tuple[str, str]:
    for exe, flavor in (("sf", "sf"), ("sfdx", "sfdx")):
        p = shutil.which(exe)
        if p:
            return p, flavor
    raise SessionError("Salesforce CLI not found on PATH. Install sf or sfdx and authenticate first.")


def _run_cli_json(cmd: list[str]) -> dict:
    env = os.environ.copy()
    env.update({
        "SF_DISABLE_TELEMETRY": "true",
        "SFDX_DISABLE_TELEMETRY": "true",
        "SF_LOG_LEVEL": "error",
        "SFDX_JSON_TO_STDOUT": "true",
        "FORCE_COLOR": "0",
    })
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if proc.returncode != 0:
        raise SessionError(
            f"Salesforce CLI failed ({proc.returncode}): {' '.join(cmd)}\nSTDERR:\n{proc.stderr.strip()}"
        )
    cleaned = proc.stdout.lstrip("﻿")
    cleaned = _ANSI_RE.sub("", cleaned)
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        cleaned = cleaned[first : last + 1]
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError as e:
        raise SessionError(f"Salesforce CLI returned non-JSON output: {cleaned[:400]}") from e


def get_session(
    username_or_alias: str,
    api_version: str,
    retries: int = 5,
    wait_seconds: float = 1.5,
) -> Session:
    exe, flavor = _which_cli()
    if flavor == "sf":
        cmd = [exe, "org", "display", "--target-org", username_or_alias, "--verbose", "--json"]
    else:
        cmd = [exe, "force:org:display", "-u", username_or_alias, "--verbose", "--json"]

    last_err: Optional[Exception] = None
    for _ in range(retries + 1):
        try:
            data = _run_cli_json(cmd)
            res = data.get("result", data)
            access_token = res.get("accessToken")
            instance_url = res.get("instanceUrl")
            if not access_token or not instance_url:
                raise SessionError("Salesforce CLI returned no accessToken/instanceUrl.")
            return Session(
                session_id=access_token,
                instance_url=instance_url,
                org_id=str(res.get("id") or res.get("orgId") or ""),
                username=str(res.get("username") or ""),
                alias=str(res.get("alias") or ""),
                api_version=api_version,
            )
        except Exception as e:
            last_err = e
            if wait_seconds > 0:
                time.sleep(wait_seconds)
    raise SessionError(f"Failed to read Salesforce session after retries: {last_err}")
