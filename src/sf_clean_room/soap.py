"""Salesforce SOAP Metadata API helpers."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

from sf_clean_room.constants import API_VERSION

ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
URN = "http://soap.sforce.com/2006/04/metadata"
HEADERS = {
    "Content-Type": "text/xml; charset=UTF-8",
    "Accept": "text/xml",
    "SOAPAction": "''",
}


class MetadataApiError(RuntimeError):
    """SOAP fault, HTTP error, or unparseable response from the Metadata API."""


@dataclass(frozen=True)
class SoapClient:
    session_id: str
    endpoint: str  # e.g. https://<host>/services/Soap/m/61.0

    @classmethod
    def for_instance(cls, session_id: str, instance_url: str) -> "SoapClient":
        endpoint = f"{instance_url.rstrip('/')}/services/Soap/m/{API_VERSION}"
        return cls(session_id=session_id, endpoint=endpoint)

    def envelope(self, body_xml: str) -> str:
        return (
            f'<env:Envelope xmlns:env="{ENV_NS}">'
            f"<env:Header>"
            f'<SessionHeader xmlns="{URN}"><sessionId>{self.session_id}</sessionId></SessionHeader>'
            f"</env:Header>"
            f"<env:Body>{body_xml}</env:Body>"
            f"</env:Envelope>"
        )

    def post(self, body_xml: str, timeout: int = 180) -> ET.Element:
        xml = self.envelope(body_xml)
        resp = requests.post(self.endpoint, data=xml.encode("utf-8"), headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            _raise_with_fault(resp)
        try:
            return ET.fromstring(resp.text)
        except ET.ParseError as e:
            raise MetadataApiError("Invalid XML response from Metadata API") from e


def _raise_with_fault(resp: requests.Response) -> None:
    text = resp.text or ""
    try:
        root = ET.fromstring(text)
        fault = root.find(f".//{{{ENV_NS}}}Fault")
        if fault is not None:
            fs = fault.findtext("faultstring") or ""
            fc = fault.findtext("faultcode") or ""
            raise MetadataApiError(f"{resp.status_code} SOAP Fault: {fs or fc}")
    except ET.ParseError:
        pass
    try:
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001 — convert any HTTPError to MetadataApiError
        raise MetadataApiError(str(e)) from e
