import unittest

from agent_regression import (
    AgentTrace,
    ComparisonPolicy,
    ContractPolicy,
    ScriptedAgentAdapter,
    StatefulFixtureTools,
    compare_traces,
    record_run,
)


def _cancel(world, arguments):
    order = world.data["orders"][arguments["order_id"]]
    order["status"] = "cancelled"
    order["cancel_count"] += 1
    return dict(order)


def _get_order(world, arguments):
    return dict(world.data["orders"][arguments["order_id"]])


def _tools():
    return StatefulFixtureTools(
        {"orders": {"123": {"status": "paid", "cancel_count": 0}}},
        {"get_order": _get_order, "cancel_order": _cancel},
    )


def _agent(actions):
    return ScriptedAgentAdapter({"name": "stateful-order-agent"}, actions)


class ScenarioTests(unittest.TestCase):
    def test_recording_captures_isolated_initial_and_final_world_state(self):
        tools = _tools()
        adapter = _agent(
            [
                {"type": "tool_call", "tool": "cancel_order", "arguments": {"order_id": "123"}},
                {"type": "final_answer", "text": "cancelled", "claims": {"status": "cancelled"}},
            ]
        )
        trace = record_run(adapter, "cancel 123", tools, run_id="cancel-1")
        self.assertEqual("paid", trace.metadata["world_state"]["initial"]["orders"]["123"]["status"])
        self.assertEqual("cancelled", trace.metadata["world_state"]["final"]["orders"]["123"]["status"])
        self.assertEqual(1, trace.metadata["world_state"]["final"]["orders"]["123"]["cancel_count"])

        fresh = tools.fresh()
        self.assertEqual("paid", fresh.snapshot()["orders"]["123"]["status"])

    def test_side_effect_contract_and_state_diff_report(self):
        tools = _tools()
        adapter = _agent(
            [
                {"type": "tool_call", "tool": "cancel_order", "arguments": {"order_id": "123"}},
                {"type": "final_answer", "text": "cancelled", "claims": {"status": "cancelled"}},
            ]
        )
        baseline = record_run(adapter, "cancel 123", tools.fresh(), run_id="baseline")
        candidate = record_run(adapter, "cancel 123", tools.fresh(), run_id="candidate")
        report = compare_traces(
            baseline,
            candidate,
            ComparisonPolicy(
                contract=ContractPolicy(
                    side_effects=[
                        {"path": "orders.123.status", "from": "paid", "to": "cancelled"},
                        {"path": "orders.123.cancel_count", "to": 1},
                    ]
                )
            ),
        )
        self.assertTrue(report["passed"])
        self.assertEqual([], report["differences"])

        wrong = record_run(
            _agent(
                [
                    {"type": "tool_call", "tool": "get_order", "arguments": {"order_id": "123"}},
                    {"type": "final_answer", "text": "paid", "claims": {"status": "paid"}},
                ]
            ),
            "cancel 123",
            tools.fresh(),
            run_id="wrong",
        )
        report = compare_traces(
            baseline,
            wrong,
            ComparisonPolicy(
                contract=ContractPolicy(
                    side_effects=[{"path": "orders.123.status", "to": "cancelled"}]
                )
            ),
        )
        self.assertFalse(report["passed"])
        categories = {item["category"] for item in report["differences"]}
        self.assertIn("side_effect", categories)
        self.assertIn("state_change", categories)

    def test_path_contract_allows_one_of_two_valid_tool_paths(self):
        baseline = AgentTrace.from_dict(
            {
                "schema_version": "0.1",
                "run_id": "baseline",
                "agent": {"name": "path-agent"},
                "events": [
                    {"sequence": 1, "type": "tool_call", "call_id": "1", "tool": "get_order", "arguments": {"order_id": "123"}},
                    {"sequence": 2, "type": "tool_result", "call_id": "1", "result": {"status": "paid"}, "is_error": False},
                    {"sequence": 3, "type": "final_answer", "text": "paid", "claims": {"status": "paid"}},
                ],
            }
        )
        candidate = AgentTrace.from_dict(
            {
                "schema_version": "0.1",
                "run_id": "candidate",
                "agent": {"name": "path-agent"},
                "events": [
                    {"sequence": 1, "type": "tool_call", "call_id": "1", "tool": "get_order", "arguments": {"order_id": "123"}},
                    {"sequence": 2, "type": "tool_result", "call_id": "1", "result": {"status": "paid"}, "is_error": False},
                    {"sequence": 3, "type": "tool_call", "call_id": "2", "tool": "get_shipping", "arguments": {"order_id": "123"}},
                    {"sequence": 4, "type": "tool_result", "call_id": "2", "result": {"eta": "tomorrow"}, "is_error": False},
                    {"sequence": 5, "type": "final_answer", "text": "paid", "claims": {"status": "paid"}},
                ],
            }
        )
        policy = ComparisonPolicy(
            contract=ContractPolicy(
                path_rules={
                    "any_of": [
                        [{"tool": "get_order", "arguments": {"order_id": "123"}}],
                        [
                            {"tool": "get_order", "arguments": {"order_id": "123"}},
                            "get_shipping",
                        ],
                    ]
                }
            )
        )
        report = compare_traces(baseline, candidate, policy)
        self.assertTrue(report["passed"])

        bad = AgentTrace.from_dict({**candidate.to_dict(), "run_id": "bad", "events": [
            *candidate.events[:1],
            {"sequence": 2, "type": "tool_result", "call_id": "1", "result": {"status": "paid"}, "is_error": False},
            {"sequence": 3, "type": "tool_call", "call_id": "2", "tool": "delete_order", "arguments": {"order_id": "123"}},
            {"sequence": 4, "type": "tool_result", "call_id": "2", "result": {"ok": True}, "is_error": False},
            {"sequence": 5, "type": "final_answer", "text": "paid", "claims": {"status": "paid"}},
        ]})
        report = compare_traces(baseline, bad, policy)
        self.assertFalse(report["passed"])
        self.assertIn("behavior_path", {item["category"] for item in report["differences"]})

    def test_path_contract_can_require_a_result_and_error_state(self):
        baseline = AgentTrace.from_dict(
            {
                "schema_version": "0.1",
                "run_id": "result-path-baseline",
                "agent": {"name": "path-agent"},
                "events": [
                    {"sequence": 1, "type": "tool_call", "call_id": "1", "tool": "get_order", "arguments": {}},
                    {"sequence": 2, "type": "tool_result", "call_id": "1", "result": {"status": "paid"}, "is_error": False},
                    {"sequence": 3, "type": "final_answer", "text": "paid", "claims": {"status": "paid"}},
                ],
            }
        )
        policy = ComparisonPolicy(
            contract=ContractPolicy(
                path_rules={
                    "any_of": [
                        [{"tool": "get_order", "result": {"status": "paid"}, "is_error": False}]
                    ]
                }
            )
        )
        self.assertTrue(compare_traces(baseline, baseline, policy)["passed"])
        bad = AgentTrace.from_dict(
            {
                **baseline.to_dict(),
                "run_id": "result-path-bad",
                "events": [
                    baseline.events[0],
                    {"sequence": 2, "type": "tool_result", "call_id": "1", "result": {"status": "cancelled"}, "is_error": False},
                    {"sequence": 3, "type": "final_answer", "text": "paid", "claims": {"status": "paid"}},
                ],
            }
        )
        report = compare_traces(baseline, bad, policy)
        self.assertFalse(report["passed"])
        self.assertIn("behavior_path", {item["category"] for item in report["differences"]})


if __name__ == "__main__":
    unittest.main()
