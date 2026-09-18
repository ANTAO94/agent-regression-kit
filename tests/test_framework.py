import unittest

from agent_regression import (
    FrameworkTraceRecorder,
    RedactionPolicy,
    record_framework_run,
)


class FrameworkEventTests(unittest.TestCase):
    def test_callbacks_preserve_call_id_when_results_arrive_out_of_order(self):
        recorder = FrameworkTraceRecorder(
            {"name": "framework-agent", "version": "1.0.0"},
            run_id="framework-run",
            request={"question": "orders"},
        )
        first = recorder.on_tool_start("first", {}, call_id="framework-a")
        second = recorder.on_tool_start("second", {}, call_id="framework-b")
        self.assertEqual("framework-a", first)
        self.assertEqual("framework-b", second)
        recorder.on_tool_end(second, {"value": 2})
        recorder.on_tool_end(first, {"value": 1})
        recorder.on_final_answer("done", {"ok": True})
        trace = recorder.finish()
        self.assertEqual(["framework-a", "framework-b"], [trace.events[0]["call_id"], trace.events[1]["call_id"]])
        self.assertEqual("framework-b", trace.events[2]["call_id"])
        self.assertEqual("framework-a", trace.events[3]["call_id"])

    def test_lifecycle_errors_are_actionable(self):
        recorder = FrameworkTraceRecorder(
            {"name": "framework-agent", "version": "1.0.0"}, run_id="bad"
        )
        call_id = recorder.tool_start("lookup", {})
        with self.assertRaisesRegex(ValueError, "before tool results"):
            recorder.final_answer("not yet")
        recorder.tool_end(call_id, {})
        recorder.final_answer("done")
        with self.assertRaisesRegex(ValueError, "more than one"):
            recorder.final_answer("again")

    def test_record_framework_run_redacts_and_validates_the_complete_trace(self):
        def runner(request, events):
            call_id = events.tool_start("lookup", {"api_key": request["api_key"]})
            events.tool_end(call_id, {"status": "paid", "token": request["api_key"]})
            events.final_answer("paid", {"status": "paid"})

        trace = record_framework_run(
            {"name": "framework-agent", "version": "1.0.0"},
            runner,
            {"api_key": "framework-secret"},
            run_id="framework-redacted",
            redaction_policy=RedactionPolicy(secret_values=("framework-secret",)),
        )
        rendered = str(trace.to_dict())
        self.assertNotIn("framework-secret", rendered)
        self.assertIn("[REDACTED]", rendered)
        self.assertEqual("paid", trace.events[-1]["claims"]["status"])

    def test_finish_requires_a_final_answer_and_closed_calls(self):
        recorder = FrameworkTraceRecorder(
            {"name": "framework-agent", "version": "1.0.0"}, run_id="unfinished"
        )
        recorder.tool_start("lookup", {})
        with self.assertRaisesRegex(ValueError, "pending tool calls"):
            recorder.finish()


if __name__ == "__main__":
    unittest.main()
