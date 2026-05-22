"""Source-controlled constants. The deny list is non-negotiable at runtime."""
from __future__ import annotations

from typing import Final

API_VERSION: Final[str] = "61.0"

POLL_SECS: Final[int] = 5
RETRIEVE_TIMEOUT_SECS: Final[int] = 1800

# Salesforce hard limit per retrieve is 10,000; default below for safety headroom.
MAX_COMPONENTS_PER_BATCH: Final[int] = 8000
# Weight ceiling targets Salesforce's ~600 MB compressed-zip limit per retrieve.
MAX_WEIGHT_PER_BATCH: Final[int] = 50_000

FOLDERED: Final[dict[str, str]] = {
    "Dashboard": "DashboardFolder",
    "Document": "DocumentFolder",
    "EmailTemplate": "EmailFolder",
    "Report": "ReportFolder",
}

OPERATIONAL_DENY: Final[frozenset[str]] = frozenset({
    "Profile",
    "PermissionSet",
    "PermissionSetGroup",
    "DataCategoryGroup",
    "MLDataDefinition",
    "MLPredictionDefinition",
    "Role",
    "Territory2Model",
    "Territory2",
    "Territory2Type",
    "Territory2ModelState",
    "Network",
    "CleanDataService",
    "Certificate",
    "SamlSsoConfig",
    "OauthCustomScope",
    "ExternalServiceRegistration",
})

SENSITIVITY_DENY: Final[frozenset[str]] = frozenset({
    "ConnectedApp",
    "AuthProvider",
    "NamedCredential",
    "ExternalCredential",
    "CustomMetadata",
    "Document",
    "StaticResource",
    "ContentAsset",
})

DENY: Final[frozenset[str]] = OPERATIONAL_DENY | SENSITIVITY_DENY

TYPE_WEIGHTS: Final[dict[str, int]] = {
    "Document": 100,
    "StaticResource": 100,
    "ContentAsset": 100,
    "ExperienceBundle": 500,
    "SiteDotCom": 200,
    "LightningComponentBundle": 20,
    "AuraDefinitionBundle": 15,
    "WaveApplication": 50,
    "WaveDashboard": 30,
    "WaveDataflow": 20,
    "WaveLens": 20,
    "WaveRecipe": 20,
    "Flow": 3,
    "FlowDefinition": 1,
}
DEFAULT_TYPE_WEIGHT: Final[int] = 1


def weight_for(type_name: str) -> int:
    return TYPE_WEIGHTS.get(type_name, DEFAULT_TYPE_WEIGHT)
