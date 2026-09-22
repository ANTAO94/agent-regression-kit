import json
import runpy
from copy import deepcopy
from unittest.mock import patch
from types import SimpleNamespace
import unittest
from pathlib import Path

from agent_regression.config import load_compare_config
from agent_regression.model import AgentTrace
from agent_regression import compare_traces
from agent_regression.compare import ComparisonPolicy
from agent_regression.contracts import ContractPolicy


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
                "send_reply",
            ],
        )
        self.assertEqual(contract["max_steps"], 6)

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
                "send_reply",
            ],
        )
        final_answer = self.baseline["events"][-1]
        self.assertEqual(final_answer["type"], "final_answer")
        self.assertEqual(final_answer["claims"]["approval_decision"], "approved")
        self.assertTrue(final_answer["claims"]["refund_issued"])

    def _compare_run(self, *, reply=None, extra=None, corrupt=False):
        module = runpy.run_path(str(PILOT / "record_trace.py"))
        rows = [
            {"action": e["tool"], "payload": deepcopy(e["arguments"]),
             "result": deepcopy(self.baseline["events"][i + 1]["result"])}
            for i, e in enumerate(self.baseline["events"]) if e["type"] == "tool_call"
        ]
        if extra:
            rows.append(extra)
        if corrupt:
            rows[2]["result"]["results"][0]["text"] = "Refunds are prohibited."
        state = {"route": "use_tools", "approval_decision": "approved",
                 "review": {"grounded": True}, "citations": ["refund-policy"],
                 "final_reply": reply if reply is not None else self.baseline["events"][-1]["text"]}
        fn = module["_trace_from_run"]
        with patch.dict(fn.__globals__, {"_action_rows": lambda *_: rows}):
            trace = fn(db=None, first={"status": "interrupted"}, final={"state": state},
                       thread_id="test", source_commit=self.baseline["agent"]["source_commit"], mutation="none")
        return compare_traces(AgentTrace.from_dict(self.baseline), trace,
                              ComparisonPolicy(final_answer_mode="claims-only",
                                               contract=ContractPolicy.from_dict(self.config["contract"])))

    def test_wrong_actual_answer_fails_without_mutation_flag(self):
        report = self._compare_run(reply="Order ORD-5001 is delivered. Your refund was denied.")
        self.assertFalse(report["passed"])
        self.assertIn("contract_assertion", {d["category"] for d in report["differences"]})

    def test_unknown_answer_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "explicit order status"):
            self._compare_run(reply="Everything is fine.")

    def test_unexpected_crm_write_remains_visible_and_blocked(self):
        report = self._compare_run(extra={"action": "log_to_crm", "payload": {"customer_id": "OTHER"},
                                         "result": {"status": "logged"}})
        self.assertFalse(report["passed"])
        self.assertIn("unauthorized_tool_call", {d["category"] for d in report["differences"]})

    def test_changed_retrieval_body_with_same_id_is_blocked(self):
        self.assertFalse(self._compare_run(corrupt=True)["passed"])

    def test_normal_and_presentation_only_final_reply_pass(self):
        self.assertTrue(self._compare_run()["passed"])
        self.assertTrue(self._compare_run(reply=self.baseline["events"][-1]["text"] + " Thank you.")["passed"])

    def test_capture_preserves_consumed_body_and_rejects_missing_body(self):
        module = runpy.run_path(str(PILOT / "record_trace.py"))
        rows = [{"action": "check_refund_policy", "payload": {"query": "refund"},
                 "result": {"doc_ids": ["refund-policy"]}}]
        with self.assertRaisesRegex(ValueError, "missing consumed"):
            module["_merge_consumed_results"](rows, [])
        captures = [{**rows[0], "result": {"results": [{"doc_id": "refund-policy", "text": "Actual body"}]}}]
        merged = module["_merge_consumed_results"](rows, captures)
        self.assertEqual("Actual body", merged[0]["result"]["results"][0]["text"])
        self.assertNotIn("results", rows[0]["result"])
        captures = []
        returned = json.dumps(merged[0]["result"])
        tool = SimpleNamespace(name="check_refund_policy", invoke=lambda _: returned)
        wrapper = module["CapturedTool"](tool, captures)
        self.assertEqual(returned, wrapper.invoke({"query": "refund"}))
        self.assertEqual(merged[0]["result"], captures[0]["result"])


if __name__ == "__main__":
    unittest.main()
