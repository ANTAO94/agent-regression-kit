import copy
import unittest

from agent_regression import (
    ScriptedAgentAdapter,
    ScriptedSessionAdapter,
    StateIsolation,
    StatefulFixtureTools,
    isolated_record_run,
    isolated_record_session,
)


class ExternalStateBackend:
    """A tiny stand-in for a database or cache adapter."""

    def __init__(self, state):
        self.state = copy.deepcopy(state)

    def snapshot(self):
        return copy.deepcopy(self.state)

    def restore(self, snapshot):
        self.state = copy.deepcopy(snapshot)


class ExternalOrderTools:
    def __init__(self, backend):
        self.backend = backend

    def call(self, tool, arguments):
        if tool != "cancel_order":
            raise KeyError(tool)
        order = self.backend.state["orders"][arguments["order_id"]]
        order["status"] = "cancelled"
        return copy.deepcopy(order)


class IsolationTests(unittest.TestCase):
    def test_state_isolation_restores_an_external_backend_after_recording(self):
        backend = ExternalStateBackend(
            {"orders": {"123": {"status": "paid"}}}
        )
        tools = ExternalOrderTools(backend)
        adapter = ScriptedAgentAdapter(
            {"name": "external-state-agent"},
            [
                {
                    "type": "tool_call",
                    "tool": "cancel_order",
                    "arguments": {"order_id": "123"},
                },
                {
                    "type": "final_answer",
                    "text": "cancelled",
                    "claims": {"status": "cancelled"},
                },
            ],
        )

        trace = isolated_record_run(
            adapter,
            "cancel 123",
            tools,
            state_backend=backend,
            run_id="external-isolated-run",
        )

        self.assertEqual(
            "paid",
            trace.metadata["world_state"]["initial"]["orders"]["123"]["status"],
        )
        self.assertEqual(
            "cancelled",
            trace.metadata["world_state"]["final"]["orders"]["123"]["status"],
        )
        self.assertEqual("paid", backend.state["orders"]["123"]["status"])

    def test_stateful_fixture_exposes_a_restore_context(self):
        def increment(world, arguments):
            del arguments
            world.data["count"] += 1
            return {"count": world.data["count"]}

        tools = StatefulFixtureTools({"count": 0}, {"increment": increment})
        with tools.isolation():
            tools.call("increment", {})
            self.assertEqual(1, tools.snapshot()["count"])
        self.assertEqual(0, tools.snapshot()["count"])

    def test_isolated_session_preserves_state_between_turns_then_restores_once(self):
        def increment(world, arguments):
            del arguments
            world.data["count"] += 1
            return {"count": world.data["count"]}

        tools = StatefulFixtureTools({"count": 0}, {"increment": increment})
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

        session = isolated_record_session(
            adapter,
            ["one", "two"],
            tools,
            session_id="isolated-session",
        )

        self.assertEqual(0, session.turns[0].metadata["world_state"]["initial"]["count"])
        self.assertEqual(1, session.turns[0].metadata["world_state"]["final"]["count"])
        self.assertEqual(1, session.turns[1].metadata["world_state"]["initial"]["count"])
        self.assertEqual(2, session.turns[1].metadata["world_state"]["final"]["count"])
        self.assertEqual(0, tools.snapshot()["count"])

    def test_state_isolation_restores_when_the_scenario_fails(self):
        backend = ExternalStateBackend({"value": "before"})
        with self.assertRaises(RuntimeError):
            with StateIsolation(backend):
                backend.state["value"] = "during"
                raise RuntimeError("scenario failed")
        self.assertEqual({"value": "before"}, backend.state)

    def test_state_isolation_requires_snapshot_and_restore(self):
        with self.assertRaises(TypeError):
            with StateIsolation(object()):
                pass


if __name__ == "__main__":
    unittest.main()
