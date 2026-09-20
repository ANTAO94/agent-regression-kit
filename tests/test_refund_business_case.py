import unittest

from agent_regression import ComparisonPolicy, compare_traces, record_run
from examples.refund_business_case import (
    RefundAgent,
    build_contract,
    build_tools,
)


def record_refund(behavior):
    return record_run(
        RefundAgent(behavior),
        {
            "order_id": "123",
            "tenant_id": "tenant-a",
            "request": "请退掉订单 123",
        },
        build_tools(),
        run_id=f"test-refund-{behavior}",
    )


class RefundBusinessCaseTests(unittest.TestCase):
    def test_normal_refund_satisfies_contract(self):
        baseline = record_refund("normal")
        report = compare_traces(
            baseline,
            record_refund("normal"),
            ComparisonPolicy(final_answer_mode="claims-only", contract=build_contract()),
        )
        self.assertTrue(report["passed"], report["differences"])
        self.assertEqual(0, report["blocking_difference_count"])

    def test_each_injected_business_error_is_blocked(self):
        baseline = record_refund("normal")
        expected_categories = {
            "wrong-order": {"tool_argument_policy", "behavior_path"},
            "wrong-tenant": {"tool_argument_policy", "required_tool", "behavior_path"},
            "wrong-amount": {"tool_argument_policy", "tool_error_state"},
            "skip-eligibility": {"required_tool", "behavior_path"},
            "duplicate-refund": {"behavior_path", "step_limit", "tool_count"},
        }
        policy = ComparisonPolicy(final_answer_mode="claims-only", contract=build_contract())
        for behavior, categories in expected_categories.items():
            with self.subTest(behavior=behavior):
                report = compare_traces(baseline, record_refund(behavior), policy)
                self.assertFalse(report["passed"])
                observed = {item["category"] for item in report["differences"]}
                self.assertTrue(categories <= observed, observed)


if __name__ == "__main__":
    unittest.main()
