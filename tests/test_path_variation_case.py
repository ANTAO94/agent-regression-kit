import unittest

from agent_regression import ComparisonPolicy, compare_traces, record_run
from examples.path_variation_case import (
    PathVariationAgent,
    build_contract,
    build_tools,
)


def record_path_variation(behavior):
    return record_run(
        PathVariationAgent(behavior),
        {"order_id": "123", "request": "查询订单 123"},
        build_tools(),
        run_id=f"test-path-variation-{behavior}",
    )


class PathVariationCaseTests(unittest.TestCase):
    def test_extra_observational_query_is_allowed(self):
        baseline = record_path_variation("normal")
        report = compare_traces(
            baseline,
            record_path_variation("extra-query"),
            ComparisonPolicy(final_answer_mode="claims-only", contract=build_contract()),
        )
        self.assertTrue(report["passed"], report["differences"])

    def test_reordered_and_forbidden_paths_are_blocked(self):
        baseline = record_path_variation("normal")
        policy = ComparisonPolicy(
            final_answer_mode="claims-only", contract=build_contract()
        )
        for behavior, category in (
            ("reordered", "behavior_path"),
            ("forbidden", "forbidden_tool"),
        ):
            with self.subTest(behavior=behavior):
                report = compare_traces(baseline, record_path_variation(behavior), policy)
                self.assertFalse(report["passed"])
                self.assertIn(category, {item["category"] for item in report["differences"]})


if __name__ == "__main__":
    unittest.main()
