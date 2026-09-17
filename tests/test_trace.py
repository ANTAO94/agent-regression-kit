import unittest

from agent_regression import AgentTrace, TraceValidationError


class AgentTraceTests(unittest.TestCase):
    def test_rejects_non_contiguous_sequence(self):
        with self.assertRaisesRegex(TraceValidationError, "contiguous"):
            AgentTrace.from_dict(
                {
                    "schema_version": "0.1",
                    "run_id": "run-1",
                    "agent": {"name": "test"},
                    "events": [
                        {"sequence": 2, "type": "final_answer", "text": "done"}
                    ],
                }
            )

    def test_rejects_tool_result_without_call(self):
        with self.assertRaisesRegex(TraceValidationError, "unknown call_id"):
            AgentTrace.from_dict(
                {
                    "schema_version": "0.1",
                    "run_id": "run-1",
                    "agent": {"name": "test"},
                    "events": [
                        {
                            "sequence": 1,
                            "type": "tool_result",
                            "call_id": "missing",
                            "result": {},
                        },
                        {"sequence": 2, "type": "final_answer", "text": "done"},
                    ],
                }
            )

    def test_rejects_tool_result_without_boolean_error_state(self):
        with self.assertRaisesRegex(TraceValidationError, "is_error"):
            AgentTrace.from_dict(
                {
                    "schema_version": "0.1",
                    "run_id": "run-1",
                    "agent": {"name": "test"},
                    "events": [
                        {
                            "sequence": 1,
                            "type": "tool_call",
                            "call_id": "call-1",
                            "tool": "lookup",
                            "arguments": {},
                        },
                        {
                            "sequence": 2,
                            "type": "tool_result",
                            "call_id": "call-1",
                            "result": {},
                            "is_error": "false",
                        },
                        {"sequence": 3, "type": "final_answer", "text": "done"},
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
