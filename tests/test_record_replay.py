import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import (
    CassetteToolExecutor,
    CallableAgentAdapter,
    FixtureTools,
    ReplayMismatchError,
    ScriptedAgentAdapter,
    replay_agent_run,
    record_run,
    replay_trace,
)
from agent_regression.cli import main


ROOT = Path(__file__).resolve().parents[1]


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

    def _baseline(self):
        return record_run(
            ScriptedAgentAdapter(
                {"name": "cassette-agent", "version": "1"},
                [
                    {"type": "tool_call", "tool": "lookup", "arguments": {"id": "123"}},
                    {"type": "final_answer", "text": "pending", "claims": {"status": "pending"}},
                ],
            ),
            "lookup 123",
            FixtureTools({"lookup": {"id": "123", "status": "pending"}}),
            run_id="cassette-baseline",
        )

    def test_cassette_returns_recorded_result_without_calling_live_tools(self):
        cassette = CassetteToolExecutor.from_trace(self._baseline())
        self.assertEqual(
            {"id": "123", "status": "pending"},
            cassette.call("lookup", {"id": "123"}),
        )
        cassette.assert_consumed()

    def test_cassette_reports_argument_mismatch_and_extra_call(self):
        cassette = CassetteToolExecutor.from_trace(self._baseline())
        with self.assertRaises(ReplayMismatchError) as context:
            cassette.call("lookup", {"id": "999"})
        self.assertEqual("tool arguments changed", context.exception.reason)
        self.assertEqual(0, context.exception.to_dict()["index"])

        cassette = CassetteToolExecutor.from_trace(self._baseline())
        cassette.call("lookup", {"id": "123"})
        with self.assertRaises(ReplayMismatchError) as context:
            cassette.call("lookup", {"id": "123"})
        self.assertEqual("Agent made an extra tool call", context.exception.reason)

    def test_cassette_detects_an_agent_that_stops_before_the_next_call(self):
        baseline = record_run(
            ScriptedAgentAdapter(
                {"name": "two-step", "version": "1"},
                [
                    {"type": "tool_call", "tool": "first", "arguments": {}},
                    {"type": "tool_call", "tool": "second", "arguments": {}},
                    {"type": "final_answer", "text": "done", "claims": {}},
                ],
            ),
            "run",
            FixtureTools({"first": 1, "second": 2}),
            run_id="two-step-baseline",
        )
        adapter = CallableAgentAdapter(
            {"name": "one-step", "version": "1"},
            lambda request, context: (
                context.call_tool("first", {}),
                context.final_answer("done", {}),
            ),
        )
        with self.assertRaises(ReplayMismatchError) as context:
            replay_agent_run(adapter, "run", baseline, run_id="one-step-candidate")
        self.assertIn("stopped before", str(context.exception))

    def test_replay_agent_run_records_the_agent_against_the_cassette(self):
        baseline = self._baseline()

        def run(request, context):
            result = context.call_tool("lookup", {"id": request["id"]})
            context.final_answer("pending", {"status": result["status"]})

        candidate = replay_agent_run(
            CallableAgentAdapter({"name": "cassette-agent", "version": "2"}, run),
            {"id": "123"},
            baseline,
            run_id="cassette-candidate",
        )
        self.assertEqual("cassette-baseline", candidate.metadata["replay"]["source_run_id"])
        self.assertEqual(1, candidate.metadata["replay"]["consumed_call_count"])
        self.assertEqual({"status": "pending"}, candidate.events[-1]["claims"])

    def test_replay_run_cli_keeps_read_only_replay_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            scenario = root / "scenario.json"
            output = root / "candidate.json"
            baseline.write_text(json.dumps(self._baseline().to_dict()), encoding="utf-8")
            scenario.write_text(
                json.dumps(
                    {
                        "run_id": "cli-candidate",
                        "agent": {"name": "cassette-agent", "version": "2"},
                        "input": {"id": "123"},
                        "plan": [
                            {"type": "tool_call", "tool": "lookup", "arguments": {"id": "123"}},
                            {"type": "final_answer", "text": "pending", "claims": {"status": "pending"}},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(
                        [
                            "replay-run",
                            "--baseline",
                            str(baseline),
                            "--scenario",
                            str(scenario),
                            "--out",
                            str(output),
                        ]
                    ),
                )
            self.assertEqual("cassette-baseline", json.loads(output.read_text())["metadata"]["replay"]["source_run_id"])


if __name__ == "__main__":
    unittest.main()
