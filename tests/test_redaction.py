import unittest

from agent_regression import RedactionPolicy, ScriptedAgentAdapter, record_run


class CapturingExecutor:
    def __init__(self):
        self.arguments = None

    def call(self, tool, arguments):
        self.arguments = arguments
        return {"api_key": arguments["api_key"], "nested": {"password": "pw"}}


class RedactionTests(unittest.TestCase):
    def test_default_policy_redacts_sensitive_keys_but_executor_receives_raw_value(self):
        executor = CapturingExecutor()
        adapter = ScriptedAgentAdapter(
            {"name": "secret-test"},
            [
                {"type": "tool_call", "tool": "echo", "arguments": {"api_key": "sk-live"}},
                {"type": "final_answer", "text": "done", "claims": {"token": "abc"}},
            ],
        )
        trace = record_run(adapter, "run", executor, run_id="redaction")

        self.assertEqual("sk-live", executor.arguments["api_key"])
        self.assertEqual("[REDACTED]", trace.events[0]["arguments"]["api_key"])
        self.assertEqual("[REDACTED]", trace.events[1]["result"]["api_key"])
        self.assertEqual("[REDACTED]", trace.events[2]["claims"]["token"])

    def test_configured_literal_is_redacted_from_text_and_input(self):
        policy = RedactionPolicy(secret_values=("secret-123",))
        adapter = ScriptedAgentAdapter(
            {"name": "secret-test"},
            [{"type": "final_answer", "text": "never print secret-123"}],
        )
        trace = record_run(
            adapter,
            "input secret-123",
            CapturingExecutor(),
            run_id="literal-redaction",
            redaction_policy=policy,
        )

        self.assertNotIn("secret-123", str(trace.to_dict()))
        self.assertIn("[REDACTED]", trace.events[0]["text"])


if __name__ == "__main__":
    unittest.main()
