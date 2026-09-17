import sys
import unittest
from pathlib import Path

from agent_regression import StdioMcpClient, run_compatibility_smoke


ROOT = Path(__file__).resolve().parents[1]
SERVER_COMMAND = [
    sys.executable,
    str(ROOT / "src/agent_regression/fixtures/mcp_stdio_server.py"),
]


class CompatibilitySmokeTests(unittest.TestCase):
    def test_smoke_checks_advertised_discovery_surfaces_without_mutation(self):
        with StdioMcpClient(SERVER_COMMAND) as client:
            report = run_compatibility_smoke(client)

        self.assertTrue(report["ok"])
        self.assertEqual("2025-11-25", report["protocol_version"])
        self.assertEqual("passed", report["checks"]["tools"]["status"])
        self.assertEqual(1, report["checks"]["tools"]["count"])
        self.assertEqual("passed", report["checks"]["resources"]["status"])
        self.assertEqual("passed", report["checks"]["prompts"]["status"])
        self.assertEqual("passed", report["checks"]["tasks"]["status"])


if __name__ == "__main__":
    unittest.main()
