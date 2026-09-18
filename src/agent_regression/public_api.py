"""Explicit compatibility boundaries for integrations."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .model import SUPPORTED_SCHEMA_VERSION
from .session import SUPPORTED_SESSION_SCHEMA_VERSION
from .version import __version__

# Increment only when a public import or its documented behavior requires a
# migration. Trace schema versions are independent and can evolve separately.
PUBLIC_API_VERSION = "4"
LEGACY_PUBLIC_API_VERSIONS: Tuple[str, ...] = ("3",)
SUPPORTED_TRACE_SCHEMA_VERSIONS: Tuple[str, ...] = (SUPPORTED_SCHEMA_VERSION,)
SUPPORTED_SESSION_SCHEMA_VERSIONS: Tuple[str, ...] = (SUPPORTED_SESSION_SCHEMA_VERSION,)
SUPPORTED_CONTRACT_SCHEMA_VERSIONS: Tuple[str, ...] = ("0.1",)
SUPPORTED_REPORT_SCHEMA_VERSIONS: Tuple[str, ...] = ("0.1",)


def public_api_manifest() -> Dict[str, Any]:
    """Return the compatibility contract for tooling and integration checks."""
    return {
        "package_version": __version__,
        "public_api_version": PUBLIC_API_VERSION,
        "legacy_public_api_versions": list(LEGACY_PUBLIC_API_VERSIONS),
        "supported_trace_schema_versions": list(SUPPORTED_TRACE_SCHEMA_VERSIONS),
        "supported_session_schema_versions": list(SUPPORTED_SESSION_SCHEMA_VERSIONS),
        "supported_contract_schema_versions": list(SUPPORTED_CONTRACT_SCHEMA_VERSIONS),
        "supported_report_schema_versions": list(SUPPORTED_REPORT_SCHEMA_VERSIONS),
        "compatibility_policy": "semver-with-explicit-deprecation",
        "deprecation_policy": {
            "legacy_api_versions": list(LEGACY_PUBLIC_API_VERSIONS),
            "removal_requires": [
                "deprecation entry",
                "upgrade guide",
                "migration check",
                "major API decision",
            ],
        },
    }
