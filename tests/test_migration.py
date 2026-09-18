import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import (
    build_compatibility_report,
    check_document_compatibility,
    check_public_api_version,
    migrate_trace,
)
from agent_regression.cli import main


ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def _trace(self):
        return json.loads(
            (ROOT / "baselines/order-123.trace.json").read_text(encoding="utf-8")
        )

    def test_v4_compatibility_accepts_trace_contract_and_report_boundaries(self):
        trace = self._trace()
        config = {
            "contract": {
                "required_claims": ["final_answer.claims.order_status"],
            }
        }
        report = {
            "schema_version": "0.1",
            "report_type": "agent_compare",
            "passed": True,
        }
        result = build_compatibility_report(
            trace=trace,
            config=config,
            report=report,
            public_api_version="4",
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["migration_required"])
        self.assertEqual("agent_compatibility", result["report_type"])

    def test_compatibility_rejects_unsupported_schema_and_accepts_session(self):
        trace = self._trace()
        session = {
            "schema_version": "0.1",
            "session_id": "session-123",
            "agent": {"name": "order-agent"},
            "turns": [trace],
        }
        self.assertTrue(check_document_compatibility(session, "session")["ok"])
        unsupported_trace = {**trace, "schema_version": "9.9"}
        trace_check = check_document_compatibility(unsupported_trace, "trace")
        self.assertFalse(trace_check["ok"])
        self.assertTrue(trace_check["migration_required"])
        unsupported_report = {
            "schema_version": "9.9",
            "report_type": "agent_compare",
        }
        self.assertFalse(check_document_compatibility(unsupported_report, "report")["ok"])
        self.assertFalse(
            check_document_compatibility(
                {"contract_schema_version": "9.9", "contract": {}}, "contract"
            )["ok"]
        )

    def test_legacy_public_api_is_explicitly_deprecated(self):
        result = check_public_api_version("3")
        self.assertTrue(result["ok"])
        self.assertEqual("deprecated", result["status"])
        self.assertTrue(result["migration_required"])
        self.assertFalse(check_public_api_version("2")["ok"])

    def test_trace_migration_is_validated_and_does_not_embed_payload_in_report(self):
        source = self._trace()
        source["unexpected_top_level"] = "discarded by canonicalization"
        migrated = migrate_trace(source)
        self.assertNotIn("unexpected_top_level", migrated)
        self.assertEqual(source["schema_version"], migrated["schema_version"])
        result = check_document_compatibility(migrated, "trace")
        self.assertTrue(result["ok"])

    def test_cli_compatibility_and_migrate_write_explicit_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.trace.json"
            migrated = root / "migrated.trace.json"
            source.write_text(json.dumps(self._trace()), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    0,
                    main(["compatibility", "--trace", str(source)]),
                )
                self.assertEqual(
                    0,
                    main(
                        [
                            "migrate",
                            "trace",
                            "--trace",
                            str(source),
                            "--out",
                            str(migrated),
                        ]
                    ),
                )
            self.assertTrue(migrated.is_file())
            self.assertIn('"report_type": "agent_migration"', output.getvalue())
            self.assertEqual(
                "0.1", json.loads(migrated.read_text(encoding="utf-8"))["schema_version"]
            )


if __name__ == "__main__":
    unittest.main()
