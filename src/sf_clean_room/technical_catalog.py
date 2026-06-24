"""Source-controlled catalogue of the 40 technical objects (v4: get_technical_objects).

The catalogue, like the metadata deny list, is a source constant — no runtime
mechanism adds objects, re-routes them, or disables the skip list.

Transport values
----------------
soql              REST /query + queryMore (SObject SOQL path)
tooling           Tooling API describe + query (follows nextRecordsUrl)
entitydef         SObject SOQL with keyset pagination on QualifiedApiName
rest_limits       Fixed-schema REST GET /limits/
rest_recordcount  Fixed-schema REST GET /limits/recordCount
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


# Layer-0 structural skip (applied at field describe time, before classification).
# Verbatim from the proven reference extractor.
LAYER0_SKIP_TYPES: Final[frozenset[str]] = frozenset({
    "base64", "textarea", "address", "location", "complexvalue", "anyType",
})
LAYER0_SKIP_NAMES: Final[frozenset[str]] = frozenset({
    "Body", "Metadata", "SymbolTable", "FullName", "HtmlValue", "Content",
})


@dataclass(frozen=True)
class CatalogueEntry:
    api_name: str
    transport: str  # soql | tooling | entitydef | rest_limits | rest_recordcount


# The 40-object catalogue. Order determines --help listing order.
CATALOGUE: Final[tuple[CatalogueEntry, ...]] = (
    # Apex tooling (9 code/test objects + DebugLevel + TraceFlag)
    CatalogueEntry("ApexClass",                         "tooling"),
    CatalogueEntry("ApexCodeCoverage",                  "tooling"),
    CatalogueEntry("ApexCodeCoverageAggregate",         "tooling"),
    CatalogueEntry("ApexExecutionOverlayResult",        "tooling"),
    CatalogueEntry("ApexLog",                           "tooling"),
    CatalogueEntry("ApexTestQueueItem",                 "tooling"),
    CatalogueEntry("ApexTestResult",                    "tooling"),
    CatalogueEntry("ApexTestResultLimits",              "tooling"),
    CatalogueEntry("ApexTestRunResult",                 "tooling"),
    CatalogueEntry("DebugLevel",                        "tooling"),
    CatalogueEntry("TraceFlag",                         "tooling"),
    # Async / job machinery
    CatalogueEntry("AsyncApexJob",                      "soql"),
    CatalogueEntry("BackgroundOperation",               "soql"),
    CatalogueEntry("CronJobDetail",                     "soql"),
    CatalogueEntry("CronTrigger",                       "soql"),
    # Schema metadata
    CatalogueEntry("EntityDefinition",                  "entitydef"),
    CatalogueEntry("RecordType",                        "soql"),
    # Event monitoring headers (cheap inventory; actual log data is get_event_logs)
    CatalogueEntry("EventLogFile",                      "soql"),
    # Flow
    CatalogueEntry("FlowInterview",                     "soql"),
    # Groups / roles
    CatalogueEntry("Group",                             "soql"),
    CatalogueEntry("GroupMember",                       "soql"),
    CatalogueEntry("UserRole",                          "soql"),
    # Identity / session / login / MFA
    CatalogueEntry("AuthSession",                       "soql"),
    CatalogueEntry("IdpEventLog",                       "soql"),
    CatalogueEntry("LoginGeo",                          "soql"),
    CatalogueEntry("LoginHistory",                      "soql"),
    CatalogueEntry("SessionPermSetActivation",          "soql"),
    CatalogueEntry("UserLogin",                         "soql"),
    CatalogueEntry("VerificationHistory",               "soql"),
    # Authorization
    CatalogueEntry("PermissionSet",                     "soql"),
    CatalogueEntry("PermissionSetAssignment",           "soql"),
    CatalogueEntry("Profile",                           "soql"),
    # Audit
    CatalogueEntry("SetupAuditTrail",                   "soql"),
    # Lightning telemetry
    CatalogueEntry("LightningUsageByAppTypeMetrics",    "soql"),
    CatalogueEntry("LightningUsageByBrowserMetrics",    "soql"),
    CatalogueEntry("LightningUsageByFlexiPageMetrics",  "soql"),
    CatalogueEntry("LightningUsageByPageMetrics",       "soql"),
    # Organisation
    CatalogueEntry("Organization",                      "soql"),
    # REST pseudo-endpoints (fixed schemas, all PASS)
    CatalogueEntry("limits",                            "rest_limits"),
    CatalogueEntry("recordCount",                       "rest_recordcount"),
)

# Fast lookup by API name (case-preserving).
CATALOGUE_BY_NAME: Final[dict[str, CatalogueEntry]] = {e.api_name: e for e in CATALOGUE}

# All catalogue names in definition order.
CATALOGUE_NAMES: Final[tuple[str, ...]] = tuple(e.api_name for e in CATALOGUE)
