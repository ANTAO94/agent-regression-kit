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


def make_refund_trace(*, amount=88, order_id="123"):
    return AgentTrace.from_dict(
        {
            "schema_version": "0.1",
            "run_id": "refund-contract-test",
            "agent": {"name": "refund-contract-test"},
            "events": [
                {
                    "sequence": 1,
                    "type": "tool_call",
                    "call_id": "call-1",
                    "tool": "get_order",
                    "arguments": {"order_id": order_id},
                },
                {
                    "sequence": 2,
                    "type": "tool_result",
                    "call_id": "call-1",
                    "result": {"order_id": order_id, "paid_amount": 88},
                    "is_error": False,
                },
                {
                    "sequence": 3,
                    "type": "tool_call",
                    "call_id": "call-2",
                    "tool": "refund_order",
                    "arguments": {"order_id": order_id, "amount": amount},
                },
                {
                    "sequence": 4,
                    "type": "tool_result",
                    "call_id": "call-2",
                    "result": {"order_id": order_id, "refunded_amount": amount},
                    "is_error": False,
                },
                {
                    "sequence": 5,
                    "type": "final_answer",
                    "text": "退款完成。",
                    "claims": {"order_id": order_id, "refund_amount": amount},
                },
            ],
            "metadata": {},
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

    def test_relations_check_cross_step_business_values(self):
        policy = ComparisonPolicy(
            contract=ContractPolicy(
                relations=[
                    {
                        "left": "tool_calls[1].arguments.order_id",
                        "operator": "equals_path",
                        "right_path": "tool_results[0].result.order_id",
                        "message": "refund must target the order returned by lookup",
                    },
                    {
                        "left": "tool_calls[1].arguments.amount",
                        "operator": "less_or_equal_path",
                        "right_path": "tool_results[0].result.paid_amount",
                        "message": "refund amount must not exceed the paid amount",
                    },
                ]
            )
        )
        passed = compare_traces(make_refund_trace(), make_refund_trace(), policy)
        self.assertTrue(passed["passed"], passed["differences"])

        bad_amount = make_refund_trace(amount=880)
        report = compare_traces(make_refund_trace(), bad_amount, policy)
        self.assertFalse(report["passed"])
        relation = next(
            item for item in report["differences"] if item["category"] == "contract_relation"
        )
        self.assertEqual("tool_calls[1].arguments.amount", relation["path"])
        self.assertIn("paid amount", relation["message"])

    def test_relations_support_literal_comparisons_and_missing_evidence_fails(self):
        policy = ContractPolicy.from_dict(
            {
                "relations": [
                    {"left": "tool_calls[0].arguments.order_id", "operator": "equals", "value": "123"},
                    {"left": "tool_calls[0].arguments.amount", "operator": "less_or_equal", "value": 88},
                ]
            }
        )
        self.assertEqual(2, len(policy.to_dict()["relations"]))
        report = compare_traces(make_refund_trace(), make_refund_trace(), ComparisonPolicy(contract=policy))
        self.assertFalse(report["passed"])
        self.assertTrue(
            any(item["category"] == "contract_relation" for item in report["differences"])
        )

    def test_relations_reject_unknown_fields_and_invalid_operator(self):
        with self.assertRaisesRegex(ValueError, "unsupported relation fields"):
            ContractPolicy.from_dict(
                {"relations": [{"left": "a", "operator": "equals", "value": 1, "mesage": "typo"}]}
            )
        with self.assertRaisesRegex(ValueError, "unsupported contract relation operator"):
            ContractPolicy.from_dict(
                {"relations": [{"left": "a", "operator": "regex", "value": "x"}]}
            )

    def test_contract_rejects_unknown_fields_instead_of_ignoring_typos(self):
        with self.assertRaisesRegex(ValueError, "unsupported contract fields"):
            ContractPolicy.from_dict({"must_not_cal": ["delete_order"]})

    def test_contract_rejects_unknown_nested_rule_fields(self):
        cases = [
            ({"must_call": [{"tool": "get_order", "argument": {}}]}, "tool rule"),
            ({"assertions": [{"path": "final_answer.text", "equals": "ok", "equal": "ok"}]}, "assertion"),
            ({"normalizers": [{"path": "final_answer.text", "type": "timestamp", "format": "iso"}]}, "normalizer"),
            ({"path_rules": {"any_of": [[{"tool": "get_order", "reslt": {}}]]}}, "path rule"),
            ({"side_effects": [{"path": "count", "from": 0, "too": 1}]}, "side effect"),
            ({"relations": [{"left": "a", "operator": "equals", "value": 1, "mesage": "typo"}]}, "relation"),
        ]
        for value, label in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, f"unsupported {label} fields"):
                    ContractPolicy.from_dict(value)


if __name__ == "__main__":
    unittest.main()
