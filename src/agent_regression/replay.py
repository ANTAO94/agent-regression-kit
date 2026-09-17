from __future__ import annotations

from typing import Any, Dict

from .model import AgentTrace


def replay_trace(trace: AgentTrace) -> Dict[str, Any]:
    """Validate and render recorded evidence without executing tools again."""
    trace.validate()
    calls = []
    results: Dict[str, Any] = {}
    answer: Dict[str, Any] = {}
    for event in trace.events:
        if event["type"] == "tool_call":
            calls.append(
                {
                    "call_id": event["call_id"],
                    "tool": event["tool"],
                    "arguments": event["arguments"],
                }
            )
        elif event["type"] == "tool_result":
            results[event["call_id"]] = {
                "result": event.get("result"),
                "is_error": event.get("is_error", False),
            }
        else:
            answer = {"text": event["text"], "claims": event.get("claims", {})}
    for call in calls:
        call["recorded_result"] = results[call["call_id"]]
    return {"ok": True, "run_id": trace.run_id, "calls": calls, "final_answer": answer}
