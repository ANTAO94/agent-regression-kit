import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_regression import (
    AgentSession,
    ComparisonPolicy,
    FixtureTools,
    ScriptedSessionAdapter,
    StatefulFixtureTools,
    compare_sessions,
    record_session,
)
from agent_regression.cli import main
from agent_regression.reports import render_session_junit, render_session_markdown


def make_session(second_text="订单仍在处理中。"):
    adapter = ScriptedSessionAdapter(
        {"name": "session-agent", "version": "1.0.0"},
        [
            [
                {"type": "tool_call", "tool": "get_order", "arguments": {"order_id": "123"}},
                {
                    "type": "final_answer",
                    "text": "订单已查询。",
                    "claims": {"turn": 1, "status": "paid"},
                },
            ],
            [
                {"type": "tool_call", "tool": "get_shipping", "arguments": {"order_id": "123"}},
                {
                    "type": "final_answer",
                    "text": second_text,
                    "claims": {"turn": 2, "status": "processing"},
                },
            ],
        ],
    )
    return record_session(
        adapter,
        ["查询订单 123", "继续查询物流"],
        FixtureTools(
            {
                "get_order": {"order_id": "123", "status": "paid"},
                "get_shipping": {"order_id": "123", "status": "processing"},
            }
        ),
        session_id="order-session",
    )


class SessionTests(unittest.TestCase):
    def test_record_session_preserves_state_between_turns(self):
        def increment(world, arguments):
            del arguments
            world.data["count"] += 1
            return {"count": world.data["count"]}

        adapter = ScriptedSessionAdapter(
            {"name": "state-session"},
            [
                [
                    {"type": "tool_call", "tool": "increment", "arguments": {}},
                    {"type": "final_answer", "text": "one"},
                ],
                [
                    {"type": "tool_call", "tool": "increment", "arguments": {}},
                    {"type": "final_answer", "text": "two"},
                ],
            ],
        )
        session = record_session(
            adapter,
            ["one", "two"],
            StatefulFixtureTools({"count": 0}, {"increment": increment}),
            session_id="state-session",
        )
        self.assertEqual(0, session.turns[0].metadata["world_state"]["initial"]["count"])
        self.assertEqual(1, session.turns[0].metadata["world_state"]["final"]["count"])
        self.assertEqual(1, session.turns[1].metadata["world_state"]["initial"]["count"])
        self.assertEqual(2, session.turns[1].metadata["world_state"]["final"]["count"])

    def test_record_session_keeps_turns_and_shared_session_identity(self):
        session = make_session()
        self.assertEqual("order-session", session.session_id)
        self.assertEqual(2, len(session.turns))
        self.assertEqual([1, 2], [turn.metadata["turn"] for turn in session.turns])
        self.assertEqual("order-session-turn-2", session.turns[1].run_id)
        restored = AgentSession.from_dict(session.to_dict())
        self.assertEqual(session.session_id, restored.session_id)

    def test_compare_sessions_reports_a_regression_on_the_second_turn(self):
        baseline = make_session()
        candidate = make_session("订单已发货。")
        report = compare_sessions(baseline, candidate)
        self.assertFalse(report["passed"])
        self.assertEqual(2, report["turn_count"])
        self.assertEqual(1, report["blocking_difference_count"])
        self.assertEqual(2, report["differences"][0]["turn"])

    def test_compare_sessions_detects_turn_count_mismatch(self):
        baseline = make_session()
        candidate = AgentSession(
            session_id="short",
            agent=baseline.agent,
            turns=baseline.turns[:1],
        )
        report = compare_sessions(baseline, candidate)
        self.assertFalse(report["passed"])
        self.assertIn(
            "session_turn_count",
            {difference["category"] for difference in report["differences"]},
        )

    def test_session_renderers_and_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.session.json"
            candidate = root / "candidate.session.json"
            scenario = root / "scenario.json"
            scenario.write_text(
                json.dumps(
                    {
                        "session_id": "cli-session",
                        "agent": {"name": "cli-agent"},
                        "tools": {"lookup": {"status": "ok"}},
                        "turns": [
                            {
                                "input": "first",
                                "plan": [
                                    {"type": "tool_call", "tool": "lookup", "arguments": {}},
                                    {"type": "final_answer", "text": "first"},
                                ],
                            },
                            {"input": "second", "plan": [{"type": "final_answer", "text": "second"}]},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["session-record", "--scenario", str(scenario), "--out", str(baseline)]))
                self.assertEqual(0, main(["session-record", "--scenario", str(scenario), "--out", str(candidate)]))
                self.assertEqual(
                    0,
                    main(
                        [
                            "session-compare",
                            "--baseline",
                            str(baseline),
                            "--candidate",
                            str(candidate),
                            "--format",
                            "markdown",
                        ]
                    ),
                )
            report = compare_sessions(
                AgentSession.from_dict(json.loads(baseline.read_text(encoding="utf-8"))),
                AgentSession.from_dict(json.loads(candidate.read_text(encoding="utf-8"))),
            )

        self.assertIn("`PASS`", render_session_markdown(report))
        self.assertIn("testsuite", render_session_junit(report))


if __name__ == "__main__":
    unittest.main()
