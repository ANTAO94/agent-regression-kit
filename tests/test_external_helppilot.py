import json
import unittest
from pathlib import Path

from agent_regression.config import load_compare_config
from agent_regression.model import AgentTrace


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "examples" / "external-pilot" / "helppilot"


class HelpPilotExternalPilotTests(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads(
            (PILOT / "baseline.trace.json").read_text(encoding="utf-8")
        )
        self.config = load_compare_config(PILOT / "compare.config.json")

    def test_committed_baseline_is_a_valid_self_describing_trace(self):
        trace = AgentTrace.from_dict(self.baseline)
        trace.validate()
        self.assertEqual("poysa213/HelpPilot", trace.metadata["source_repository"])
        self.assertRegex(trace.agent["source_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(
            "lost-order-refund-with-human-approval",
            trace.metadata["scenario"],
        )
        self.assertTrue(trace.metadata["approval_before_resume"])

    def test_contract_covers_approval_boundary_and_business_claims(self):
        contract = self.config["contract"]
        required = set(contract["required_claims"])
        for claim in (
            "route",
            "approval_required",
            "approval_decision",
            "refund_issued",
            "refund_order_id",
            "refund_amount",
            "grounded",
            "citations",
        ):
            self.assertIn(f"final_answer.claims.{claim}", required)
        self.assertEqual(
            [item["tool"] for item in contract["must_call"]],
            [
                "get_order",
                "get_tracking",
                "check_refund_policy",
                "create_refund_draft",
                "issue_refund",
            ],
        )
        self.assertEqual(contract["max_steps"], 5)

    def test_baseline_records_only_after_approval_for_side_effect(self):
        actions = [
            event["tool"]
            for event in self.baseline["events"]
            if event["type"] == "tool_call"
        ]
        self.assertEqual(
            actions,
            [
                "get_order",
                "get_tracking",
                "check_refund_policy",
                "create_refund_draft",
                "issue_refund",
            ],
        )
        final_answer = self.baseline["events"][-1]
        self.assertEqual(final_answer["type"], "final_answer")
        self.assertEqual(final_answer["claims"]["approval_decision"], "approved")
        self.assertTrue(final_answer["claims"]["refund_issued"])


if __name__ == "__main__":
    unittest.main()
