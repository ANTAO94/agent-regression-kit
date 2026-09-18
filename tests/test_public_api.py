import unittest

import agent_regression
from agent_regression import (
    PUBLIC_API_VERSION,
    SUPPORTED_TRACE_SCHEMA_VERSIONS,
    public_api_manifest,
)


class PublicApiCompatibilityTests(unittest.TestCase):
    def test_manifest_exposes_explicit_api_and_trace_boundaries(self):
        manifest = public_api_manifest()
        self.assertEqual("3", PUBLIC_API_VERSION)
        self.assertEqual(["0.1"], list(SUPPORTED_TRACE_SCHEMA_VERSIONS))
        self.assertEqual(PUBLIC_API_VERSION, manifest["public_api_version"])
        self.assertEqual(["0.1"], manifest["supported_trace_schema_versions"])
        self.assertEqual("semver-with-explicit-deprecation", manifest["compatibility_policy"])

    def test_every_declared_public_symbol_is_importable(self):
        missing = [name for name in agent_regression.__all__ if not hasattr(agent_regression, name)]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
