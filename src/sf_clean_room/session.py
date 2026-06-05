"""Resolve a Salesforce session via the locally authenticated sf/sfdx CLI.

The tool does not handle credentials itself; it shells out to whichever CLI
flavour is on PATH and reads the OAuth access token already negotiated for the
given alias or username.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from sf_clean_room.sfcli import SfCliError, run_cli_json, which_cli


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
    try:
        return which_cli()
    except SfCliError as e:
        raise SessionError(str(e)) from e


def _run_cli_json(cmd: list[str]) -> dict:
    try:
        return run_cli_json(cmd)
    except SfCliError as e:
        raise SessionError(str(e)) from e


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
