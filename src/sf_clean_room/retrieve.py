"""Async retrieve: submit, poll, return the base64 zip."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from sf_clean_room.batch import Batch
from sf_clean_room.constants import API_VERSION, POLL_SECS, RETRIEVE_TIMEOUT_SECS
from sf_clean_room.soap import URN, MetadataApiError, SoapClient


@dataclass(frozen=True)
class RetrieveResult:
    async_id: str
    status: str
    zip_b64: str
    error: str
    duration_secs: float


def render_unpackaged(batch: Batch) -> str:
    blocks: list[str] = []
    for c in batch.chunks:
        mem_xml = "\n      ".join(f"<members>{m}</members>" for m in c.members)
        blocks.append(
            f"  <types>\n      {mem_xml}\n      <name>{c.type_name}</name>\n  </types>"
        )
    return f"{os.linesep.join(blocks)}\n  <version>{API_VERSION}</version>"


def submit_retrieve(client: SoapClient, batch: Batch) -> str:
    unpackaged = render_unpackaged(batch)
    body = (
        f'<retrieve xmlns="{URN}">'
        f"<retrieveRequest>"
        f"<apiVersion>{API_VERSION}</apiVersion>"
        f"<singlePackage>true</singlePackage>"
        f"<unpackaged>\n{unpackaged}\n</unpackaged>"
        f"</retrieveRequest>"
        f"</retrieve>"
    )
    root = client.post(body)
    ns = {"m": URN}
    async_id = root.findtext(".//m:id", default="", namespaces=ns)
    if not async_id:
        raise MetadataApiError("Salesforce returned no async retrieve id")
    return async_id


def check_retrieve(client: SoapClient, async_id: str) -> dict[str, str]:
    body = (
        f'<checkRetrieveStatus xmlns="{URN}">'
        f"<asyncProcessId>{async_id}</asyncProcessId>"
        f"<includeZip>true</includeZip>"
        f"</checkRetrieveStatus>"
    )
    root = client.post(body)
    ns = {"m": URN}
    status = root.findtext(".//m:status", default="", namespaces=ns)
    return {
        "done": status in ("Succeeded", "Failed", "Canceled"),
        "status": status,
        "zip_b64": root.findtext(".//m:zipFile", default="", namespaces=ns),
        "error": root.findtext(".//m:errorMessage", default="", namespaces=ns),
    }


def run_batch(
    client: SoapClient,
    batch: Batch,
    poll_secs: int = POLL_SECS,
    timeout_secs: int = RETRIEVE_TIMEOUT_SECS,
    on_submit=None,
    on_poll=None,
    sleep=time.sleep,
    now=time.time,
) -> RetrieveResult:
    """Submit a retrieve and poll to completion.

    ``on_submit(async_id)`` is invoked once after the async id is known.
    ``on_poll(elapsed_secs, async_id)`` is invoked before each ``sleep``, so a
    caller can surface "still running" progress on long retrieves.
    """
    async_id = submit_retrieve(client, batch)
    if on_submit is not None:
        on_submit(async_id)
    start = now()
    while True:
        st = check_retrieve(client, async_id)
        if st["done"]:
            duration = now() - start
            if st["status"] != "Succeeded":
                raise MetadataApiError(
                    f"retrieve {async_id} ended with status {st['status']}: {st['error'] or '(no detail)'}"
                )
            if not st["zip_b64"]:
                raise MetadataApiError(f"retrieve {async_id} succeeded but returned no zip")
            return RetrieveResult(
                async_id=async_id,
                status=st["status"],
                zip_b64=st["zip_b64"],
                error=st["error"],
                duration_secs=duration,
            )
        elapsed = now() - start
        if elapsed > timeout_secs:
            raise MetadataApiError(f"retrieve {async_id} timed out after {timeout_secs}s")
        if on_poll is not None:
            on_poll(elapsed, async_id)
        sleep(poll_secs)
