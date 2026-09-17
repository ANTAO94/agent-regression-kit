import unittest

from agent_regression import FixtureTools, ScriptedAgentAdapter, record_run, replay_trace


class RecordReplayTests(unittest.TestCase):
    def test_records_call_result_and_answer_in_order(self):
        adapter = ScriptedAgentAdapter(
            {"name": "toy", "version": "1"},
            [
                {"type": "tool_call", "tool": "lookup", "arguments": {"id": "123"}},
                {
                    "type": "final_answer",
                    "text": "pending",
                    "claims": {"status": "pending"},
                },
            ],
        )
        trace = record_run(
            adapter,
            "lookup 123",
            FixtureTools({"lookup": {"id": "123", "status": "pending"}}),
            run_id="test-run",
        )

        self.assertEqual([1, 2, 3], [event["sequence"] for event in trace.events])
        self.assertEqual("tool_result", trace.events[1]["type"])
        replay = replay_trace(trace)
        self.assertTrue(replay["ok"])
        self.assertEqual("pending", replay["final_answer"]["text"])


if __name__ == "__main__":
    unittest.main()
