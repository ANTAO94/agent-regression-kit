import sys
import unittest
from pathlib import Path

from agent_regression import (
    PARAMETER_REGRESSION,
    RESULT_MISREAD,
    RuleBasedOrderAgentAdapter,
    compare_traces,
    record_mcp_run,
    replay_trace,
)


ROOT = Path(__file__).resolve().parents[1]
SERVER_COMMAND = [
    sys.executable,
    str(ROOT / "src/agent_regression/fixtures/mcp_stdio_server.py"),
]


def record(behavior: str = "normal", order_id: str = "123"):
    return record_mcp_run(
        RuleBasedOrderAgentAdapter(behavior),
        f"查询订单 {order_id}",
        SERVER_COMMAND,
        run_id=f"rule-agent-{behavior}-{order_id}",
    )


class RuleBasedOrderAgentTests(unittest.TestCase):
    def test_normal_agent_answers_from_actual_mcp_result(self):
        replay = replay_trace(record())

        self.assertEqual("get_order", replay["calls"][0]["tool"])
        self.assertEqual({"order_id": "123"}, replay["calls"][0]["arguments"])
        self.assertEqual(
            "not_shipped", replay["calls"][0]["recorded_result"]["result"]["status"]
        )
        self.assertEqual("订单 123 尚未发货。", replay["final_answer"]["text"])
        self.assertEqual(
            {"order_id": "123", "order_status": "not_shipped"},
            replay["final_answer"]["claims"],
        )

    def test_answer_changes_when_live_tool_result_changes(self):
        replay = replay_trace(record(order_id="999"))

        self.assertEqual(
            "not_found", replay["calls"][0]["recorded_result"]["result"]["status"]
        )
        self.assertEqual("未找到订单 999。", replay["final_answer"]["text"])
        self.assertEqual("not_found", replay["final_answer"]["claims"]["order_status"])

    def test_parameter_regression_is_caught_end_to_end(self):
        report = compare_traces(record(), record(PARAMETER_REGRESSION))
        categories = {difference["category"] for difference in report["differences"]}

        self.assertFalse(report["passed"])
        self.assertIn("tool_arguments", categories)
        self.assertIn("tool_result", categories)
        self.assertIn("result_interpretation", categories)
        self.assertIn("final_answer", categories)

    def test_result_misread_is_caught_without_a_tool_regression(self):
        report = compare_traces(record(), record(RESULT_MISREAD))
        categories = {difference["category"] for difference in report["differences"]}

        self.assertFalse(report["passed"])
        self.assertEqual({"result_interpretation", "final_answer"}, categories)


if __name__ == "__main__":
    unittest.main()
