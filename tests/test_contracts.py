import unittest

from agent_regression import AgentTrace, ComparisonPolicy, ContractPolicy, compare_traces


def make_trace(
    *,
    tool="get_order",
    arguments=None,
    result=None,
    text="订单尚未发货。",
    claims=None,
):
    return AgentTrace.from_dict(
        {
            "schema_version": "0.1",
            "run_id": "contract-test",
            "agent": {"name": "contract-test"},
            "events": [
                {
                    "sequence": 1,
                    "type": "tool_call",
                    "call_id": "call-1",
                    "tool": tool,
                    "arguments": arguments or {"order_id": "123"},
                },
                {
                    "sequence": 2,
                    "type": "tool_result",
                    "call_id": "call-1",
                    "result": result or {"status": "not_shipped"},
                    "is_error": False,
                },
                {
                    "sequence": 3,
                    "type": "final_answer",
                    "text": text,
                    "claims": claims or {"order_status": "not_shipped"},
                },
            ],
        }
    )


class ContractTests(unittest.TestCase):
    def test_ignore_paths_and_timestamp_normalizer_remove_known_noise(self):
        baseline = make_trace(
            result={"status": "not_shipped", "request_id": "req-1", "created_at": "2026-09-18T08:00:00Z"}
        )
        candidate = make_trace(
            result={"status": "not_shipped", "request_id": "req-2", "created_at": "2026-09-18T08:01:00Z"}
        )
        policy = ComparisonPolicy(
            contract=ContractPolicy(
                ignore_paths=["tool_results[*].result.request_id"],
                normalizers=[
                    {"path": "tool_results[*].result.created_at", "type": "timestamp"}
                ],
            )
        )
        report = compare_traces(baseline, candidate, policy)
        self.assertTrue(report["passed"])
        self.assertEqual([], report["differences"])

    def test_assertions_required_and_forbidden_tools_and_step_limit(self):
        policy = ComparisonPolicy(
            contract=ContractPolicy(
                assertions=[
                    {"path": "final_answer.claims.order_status", "equals": "not_shipped"},
                    {"path": "tool_calls[0].arguments.order_id", "exists": True},
                ],
                must_call=[{"tool": "get_order", "arguments": {"order_id": "123"}}],
                must_not_call=[{"tool": "delete_order"}],
                max_steps=1,
            )
        )
        report = compare_traces(make_trace(), make_trace(), policy)
        self.assertTrue(report["passed"])

        bad = make_trace(tool="delete_order", claims={"order_status": "shipped"})
        report = compare_traces(bad, bad, policy)
        categories = {item["category"] for item in report["differences"]}
        self.assertFalse(report["passed"])
        self.assertEqual(
            {"contract_assertion", "required_tool", "forbidden_tool"}, categories
        )

    def test_contract_policy_rejects_unsupported_normalizers(self):
        with self.assertRaises(ValueError):
            ContractPolicy(normalizers=[{"path": "events", "type": "regex"}])

    def test_required_claims_fail_when_the_agent_omits_a_business_result(self):
        policy = ComparisonPolicy(
            contract=ContractPolicy(
                required_claims=["final_answer.claims.order_status"]
            )
        )
        missing = make_trace(claims={"order_id": "123"})
        report = compare_traces(missing, missing, policy)
        self.assertFalse(report["passed"])
        self.assertEqual("required_claim", report["differences"][0]["category"])

    def test_required_claims_are_serialized_and_validated(self):
        policy = ContractPolicy.from_dict(
            {"required_claims": ["final_answer.claims.order_status"]}
        )
        self.assertEqual(
            ["final_answer.claims.order_status"], policy.to_dict()["required_claims"]
        )
        with self.assertRaises(ValueError):
            ContractPolicy.from_dict({"required_claims": "final_answer.claims"})


if __name__ == "__main__":
    unittest.main()
