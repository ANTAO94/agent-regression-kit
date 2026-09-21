import hashlib
import json
import runpy
import unittest
from pathlib import Path

from agent_regression.config import load_compare_config
from agent_regression.model import AgentTrace

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "examples" / "external-pilot" / "langgraph-agent-stack"
PILOT_MODULE = runpy.run_path(str(PILOT / "capture_trace.py"))


class ExternalPilotFixtureTests(unittest.TestCase):
    def test_fixture_and_committed_baseline_are_self_describing(self):
        fixture = PILOT_MODULE["_load_fixture"](PILOT / "research-fixture.json")
        trace = AgentTrace.from_dict(
            json.loads((PILOT / "baseline.trace.json").read_text(encoding="utf-8"))
        )
        trace.validate()
        self.assertEqual(fixture["fixture_id"], trace.agent["fixture_id"])
        self.assertEqual(
            fixture["source"]["url"], trace.agent["source_snapshot"]["url"]
        )
        self.assertEqual(
            hashlib.sha256(
                (PILOT / "research-fixture.json").read_bytes()
            ).hexdigest(),
            trace.agent["fixture_sha256"],
        )

    def test_claims_are_parsed_from_summary_facts(self):
        claims = PILOT_MODULE["_claims"](
            {
                "summary": 'answer\nFACTS_JSON={"checkpointer_scope":"single_thread"}',
                "findings": ["one"],
                "sources": ["https://docs.example.test"],
                "confidence": 0.92,
            }
        )
        self.assertEqual("single_thread", claims["facts"]["checkpointer_scope"])

    def test_claims_fail_closed_when_facts_are_missing(self):
        with self.assertRaisesRegex(ValueError, "FACTS_JSON"):
            PILOT_MODULE["_claims"](
                {
                    "summary": "summary without structured facts",
                    "findings": [],
                    "sources": [],
                }
            )

    def test_pilot_contract_requires_business_facts(self):
        config = load_compare_config(PILOT / "compare.config.json")
        required = set(config["contract"]["required_claims"])
        self.assertIn(
            "final_answer.claims.facts.checkpointer_scope",
            required,
        )
        self.assertEqual(
            "single_thread",
            next(
                item["equals"]
                for item in config["contract"]["assertions"]
                if item["path"].endswith("checkpointer_scope")
            ),
        )


if __name__ == "__main__":
    unittest.main()
