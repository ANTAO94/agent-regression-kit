import unittest

from agent_regression import AgentTrace, ComparisonPolicy, RedactionPolicy, compare_traces


def make_trace(tool="get_order", order_id="123", status="not_shipped", text="not shipped"):
    return AgentTrace.from_dict(
        {
            "schema_version": "0.1",
            "run_id": f"run-{tool}-{order_id}-{status}",
            "agent": {"name": "toy"},
            "events": [
                {
                    "sequence": 1,
                    "type": "tool_call",
                    "call_id": "call-1",
                    "tool": tool,
                    "arguments": {"order_id": order_id},
                },
                {
                    "sequence": 2,
                    "type": "tool_result",
                    "call_id": "call-1",
                    "result": {"order_id": "123", "status": "not_shipped"},
                    "is_error": False,
                },
                {
                    "sequence": 3,
                    "type": "final_answer",
                    "text": text,
                    "claims": {"order_status": status},
                },
            ],
        }
    )


class CompareTests(unittest.TestCase):
    def test_identical_evidence_passes(self):
        report = compare_traces(make_trace(), make_trace())
        self.assertTrue(report["passed"])
        self.assertEqual([], report["differences"])

    def test_detects_tool_parameter_regression(self):
        report = compare_traces(make_trace(), make_trace(order_id=123))
        self.assertFalse(report["passed"])
        self.assertIn("tool_arguments", {item["category"] for item in report["differences"]})

    def test_detects_tool_name_interpretation_and_answer_changes(self):
        report = compare_traces(
            make_trace(),
            make_trace(tool="lookup_order", status="shipped", text="shipped"),
        )
        categories = {item["category"] for item in report["differences"]}
        self.assertEqual(
            {"tool_name", "result_interpretation", "final_answer"}, categories
        )

    def test_policy_can_allow_category_but_keep_other_differences_blocking(self):
        report = compare_traces(
            make_trace(),
            make_trace(status="shipped", text="shipped"),
            ComparisonPolicy(allowed_categories={"final_answer"}),
        )
        self.assertFalse(report["passed"])
        self.assertEqual(1, report["blocking_difference_count"])
        allowed = {item["category"]: item["allowed"] for item in report["differences"]}
        self.assertTrue(allowed["final_answer"])
        self.assertFalse(allowed["result_interpretation"])

    def test_policy_can_allow_exact_path(self):
        report = compare_traces(
            make_trace(),
            make_trace(text="same meaning, different wording"),
            ComparisonPolicy(allowed_paths={"final_answer.text"}),
        )
        self.assertTrue(report["passed"])
        self.assertEqual(0, report["blocking_difference_count"])

    def test_claims_only_mode_allows_wording_but_keeps_claims_strict(self):
        report = compare_traces(
            make_trace(text="The package has not shipped yet."),
            make_trace(text="订单目前仍未发货。"),
            ComparisonPolicy(final_answer_mode="claims-only"),
        )
        self.assertTrue(report["passed"])
        self.assertEqual([], report["differences"])
        self.assertEqual("claims-only", report["policy"]["final_answer_mode"])

    def test_claims_only_mode_still_blocks_changed_claims(self):
        report = compare_traces(
            make_trace(text="The package has not shipped yet."),
            make_trace(status="shipped", text="订单已发货。"),
            ComparisonPolicy(final_answer_mode="claims-only"),
        )
        self.assertFalse(report["passed"])
        self.assertEqual(
            {"result_interpretation"},
            {item["category"] for item in report["differences"]},
        )

    def test_report_redacts_sensitive_diff_values(self):
        baseline = make_trace()
        candidate = make_trace()
        baseline.events[0]["arguments"]["api_key"] = "baseline-secret"
        candidate.events[0]["arguments"]["api_key"] = "candidate-secret"
        report = compare_traces(
            baseline,
            candidate,
            redaction_policy=RedactionPolicy(secret_values=("not-used",)),
        )

        rendered = str(report)
        self.assertNotIn("baseline-secret", rendered)
        self.assertNotIn("candidate-secret", rendered)
        self.assertIn("[REDACTED]", rendered)


if __name__ == "__main__":
    unittest.main()
