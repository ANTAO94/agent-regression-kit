"""Explicit compatibility boundaries for integrations."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .model import SUPPORTED_SCHEMA_VERSION

# Increment only when a public import or its documented behavior requires a
# migration. Trace schema versions are independent and can evolve separately.
PUBLIC_API_VERSION = "3"
SUPPORTED_TRACE_SCHEMA_VERSIONS: Tuple[str, ...] = (SUPPORTED_SCHEMA_VERSION,)


def public_api_manifest() -> Dict[str, Any]:
    """Return the compatibility contract for tooling and integration checks."""
    return {
        "public_api_version": PUBLIC_API_VERSION,
        "supported_trace_schema_versions": list(SUPPORTED_TRACE_SCHEMA_VERSIONS),
        "compatibility_policy": "semver-with-explicit-deprecation",
    }
