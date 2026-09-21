import hashlib
import json
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace

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
        tool_results = [
            event["result"] for event in trace.events if event["type"] == "tool_result"
        ]
        self.assertEqual(3, len(tool_results))
        self.assertTrue(all("Document-ID:" in result for result in tool_results))
        self.assertTrue(all("MOCK RESULT" not in result for result in tool_results))
        final_output = json.loads(trace.events[-1]["text"])
        self.assertEqual(set(tool_results), set(final_output["findings"]))

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

    def test_business_facts_are_derived_from_evidence_content(self):
        fixture = PILOT_MODULE["_load_fixture"](PILOT / "research-fixture.json")
        evidence = "\n".join(
            PILOT_MODULE["_fixture_result"](fixture, query, None)
            for query in fixture["queries"]
        )
        self.assertEqual(fixture["facts"], PILOT_MODULE["_facts_from_evidence"](evidence))
        ids_only = "\n".join(
            f"Document-ID: {document['id']}\nExcerpt: [CORRUPTED EVIDENCE]"
            for document in fixture["documents"]
        )
        self.assertEqual({}, PILOT_MODULE["_facts_from_evidence"](ids_only))

    def test_fixture_model_does_not_copy_expected_facts_when_content_is_missing(self):
        fixture = PILOT_MODULE["_load_fixture"](PILOT / "research-fixture.json")
        agent = SimpleNamespace(
            _invoke_llm_with_retry=lambda *_args, **_kwargs: SimpleNamespace(content="{}")
        )
        PILOT_MODULE["_install_fixture_model"](
            agent,
            fixture,
            misread_fact=None,
            vary_evidence_order=False,
            summary_confidence=None,
        )
        prompt = "Provide a JSON object with keys\n" + "\n".join(
            f"Document-ID: {document['id']}\nExcerpt: [CORRUPTED EVIDENCE]"
            for document in fixture["documents"]
        )
        response = json.loads(
            agent._invoke_llm_with_retry([SimpleNamespace(content=prompt)]).content
        )
        facts = json.loads(response["summary"].split("FACTS_JSON=", 1)[1])
        self.assertNotIn("checkpointer_scope", facts)
        self.assertNotIn("store_scope", facts)

    def test_recorded_tool_results_are_values_consumed_by_agent(self):
        events = [
            {
                "event": "on_tool_end",
                "run_id": "call-1",
                "data": {"output": "delegated mock result"},
            }
        ]
        reconciled = PILOT_MODULE["_events_with_consumed_results"](
            events, ["reviewed evidence returned to agent"]
        )
        self.assertEqual(
            "reviewed evidence returned to agent", reconciled[0]["data"]["output"]
        )
        self.assertEqual("delegated mock result", events[0]["data"]["output"])

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
