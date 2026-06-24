"""Tests for technical_catalog.py."""
import pytest

from sf_clean_room.technical_catalog import (
    CATALOGUE,
    CATALOGUE_BY_NAME,
    CATALOGUE_NAMES,
    LAYER0_SKIP_NAMES,
    LAYER0_SKIP_TYPES,
)

VALID_TRANSPORTS = {"soql", "tooling", "entitydef", "rest_limits", "rest_recordcount"}

EXPECTED_OBJECTS = {
    "ApexClass", "ApexCodeCoverage", "ApexCodeCoverageAggregate",
    "ApexExecutionOverlayResult", "ApexLog", "ApexTestQueueItem",
    "ApexTestResult", "ApexTestResultLimits", "ApexTestRunResult",
    "AsyncApexJob", "AuthSession", "BackgroundOperation",
    "CronJobDetail", "CronTrigger", "DebugLevel",
    "EntityDefinition", "EventLogFile", "FlowInterview",
    "Group", "GroupMember", "IdpEventLog",
    "LightningUsageByAppTypeMetrics", "LightningUsageByBrowserMetrics",
    "LightningUsageByFlexiPageMetrics", "LightningUsageByPageMetrics",
    "LoginGeo", "LoginHistory", "Organization",
    "PermissionSet", "PermissionSetAssignment", "Profile",
    "RecordType", "SessionPermSetActivation", "SetupAuditTrail",
    "TraceFlag", "UserLogin", "UserRole", "VerificationHistory",
    "limits", "recordCount",
}


def test_catalogue_has_exactly_40_objects():
    assert len(CATALOGUE) == 40


def test_catalogue_contains_all_expected_objects():
    assert {e.api_name for e in CATALOGUE} == EXPECTED_OBJECTS


def test_no_duplicate_api_names():
    names = [e.api_name for e in CATALOGUE]
    assert len(names) == len(set(names))


def test_all_transports_are_valid():
    for entry in CATALOGUE:
        assert entry.transport in VALID_TRANSPORTS, (
            f"{entry.api_name} has unknown transport: {entry.transport!r}"
        )


def test_catalogue_by_name_has_40_entries():
    assert len(CATALOGUE_BY_NAME) == 40


def test_catalogue_names_length():
    assert len(CATALOGUE_NAMES) == 40


def test_catalogue_by_name_lookup():
    assert CATALOGUE_BY_NAME["ApexClass"].transport == "tooling"
    assert CATALOGUE_BY_NAME["LoginHistory"].transport == "soql"
    assert CATALOGUE_BY_NAME["EntityDefinition"].transport == "entitydef"
    assert CATALOGUE_BY_NAME["limits"].transport == "rest_limits"
    assert CATALOGUE_BY_NAME["recordCount"].transport == "rest_recordcount"


def test_tooling_objects():
    tooling = {e.api_name for e in CATALOGUE if e.transport == "tooling"}
    assert "ApexClass" in tooling
    assert "DebugLevel" in tooling
    assert "TraceFlag" in tooling
    assert "ApexTestResult" in tooling


def test_layer0_skip_types_nonempty():
    assert "textarea" in LAYER0_SKIP_TYPES
    assert "base64" in LAYER0_SKIP_TYPES


def test_layer0_skip_names_nonempty():
    assert "Body" in LAYER0_SKIP_NAMES
    assert "Metadata" in LAYER0_SKIP_NAMES
    assert "SymbolTable" in LAYER0_SKIP_NAMES
