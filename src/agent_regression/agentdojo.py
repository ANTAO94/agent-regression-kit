"""Import and validate an exported AgentDojo run without copying its oracle.

AgentDojo stores model messages, tool calls and external ``utility``/
``security`` outcomes in one JSON document.  This bridge converts only the
observable messages into :class:`AgentTrace`; the external outcomes remain in
the validation report and are never embedded in Trace metadata or Contract
rules.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Dict, List, Mapping

from .contracts import ContractPolicy
from .model import AgentTrace


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _tool_arguments(value: Any, label: str) -> Dict[str, Any]:
    arguments = value if value is not None else {}
    if not isinstance(arguments, Mapping):
        raise ValueError(f"{label} must be an object")
    return deepcopy(dict(arguments))


def _source_metadata(run: Mapping[str, Any], source: Mapping[str, Any] | None) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "suite_name": run.get("suite_name"),
        "pipeline_name": run.get("pipeline_name"),
        "user_task_id": run.get("user_task_id"),
        "injection_task_id": run.get("injection_task_id"),
        "attack_type": run.get("attack_type"),
    }
    if source is not None:
        result["source"] = deepcopy(dict(source))
    return {key: value for key, value in result.items() if value is not None}


def trace_from_agentdojo_run(
    run: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None = None,
    run_id: str | None = None,
    agent: Mapping[str, Any] | None = None,
) -> AgentTrace:
    """Convert one exported AgentDojo run into a validated AgentTrace.

    ``utility`` and ``security`` are deliberately ignored while constructing
    the Trace.  They are external labels and can only be consumed after the
    observable Agent behavior has been checked.
    """

    run = _object(run, "AgentDojo run")
    messages = _array(run.get("messages"), "AgentDojo run.messages")
    events: List[Dict[str, Any]] = []
    sequence = 1
    seen_call_ids: set[str] = set()
    final_answer_seen = False

    for message_index, raw_message in enumerate(messages):
        message = _object(raw_message, f"AgentDojo message[{message_index}]")
        role = message.get("role")
        if role == "assistant":
            raw_calls = message.get("tool_calls") or []
            for call_index, raw_call in enumerate(_array(raw_calls, "assistant.tool_calls")):
                call = _object(
                    raw_call,
                    f"AgentDojo message[{message_index}].tool_calls[{call_index}]",
                )
                raw_function = call.get("function")
                if isinstance(raw_function, Mapping):
                    function = raw_function
                    tool = function.get("name", function.get("function"))
                    raw_arguments = function.get("args", function.get("arguments"))
                elif isinstance(raw_function, str):
                    function = {}
                    tool = raw_function
                    raw_arguments = call.get("args", call.get("arguments"))
                else:
                    raise ValueError("AgentDojo tool call.function must be a string or object")
                call_id = call.get("id")
                if not isinstance(tool, str) or not tool.strip():
                    raise ValueError("AgentDojo tool call function must contain a name")
                if not isinstance(call_id, str) or not call_id.strip():
                    raise ValueError("AgentDojo tool call id must be a non-empty string")
                if call_id in seen_call_ids:
                    raise ValueError(f"duplicate AgentDojo tool call id: {call_id}")
                seen_call_ids.add(call_id)
                events.append(
                    {
                        "sequence": sequence,
                        "type": "tool_call",
                        "call_id": call_id,
                        "tool": tool,
                        "arguments": _tool_arguments(raw_arguments, "AgentDojo tool call arguments"),
                        "metadata": {"source_role": "assistant"},
                    }
                )
                sequence += 1
            if not raw_calls and isinstance(message.get("content"), str):
                if final_answer_seen:
                    raise ValueError("AgentDojo run contains more than one final answer")
                final_answer_seen = True
                events.append(
                    {
                        "sequence": sequence,
                        "type": "final_answer",
                        "text": message["content"],
                        "metadata": {"source_role": "assistant"},
                    }
                )
                sequence += 1
        elif role == "tool":
            call_id = message.get("tool_call_id")
            if not isinstance(call_id, str) or not call_id.strip():
                raise ValueError("AgentDojo tool message needs tool_call_id")
            error = message.get("error")
            event: Dict[str, Any] = {
                "sequence": sequence,
                "type": "tool_result",
                "call_id": call_id,
                "result": deepcopy(message.get("content")),
                "is_error": error is not None,
                "metadata": {"source_role": "tool"},
            }
            if error is not None:
                event["error"] = str(error)
            events.append(event)
            sequence += 1

    if not final_answer_seen:
        raise ValueError("AgentDojo run must contain an assistant final answer")
    resolved_run_id = run_id or "agentdojo-{}-{}".format(
        run.get("suite_name", "run"),
        run.get("user_task_id", "unknown"),
    )
    identity = dict(agent or {})
    identity.setdefault("name", "agentdojo-agent")
    identity.setdefault("version", str(run.get("pipeline_name", "unknown")))
    return AgentTrace.from_dict(
        {
            "schema_version": "0.1",
            "run_id": resolved_run_id,
            "agent": identity,
            "events": events,
            "metadata": {"agentdojo": _source_metadata(run, source)},
        }
    )


def evaluate_agentdojo_run(
    run: Mapping[str, Any],
    contract: Mapping[str, Any] | ContractPolicy,
    *,
    source: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Check an exported run against a deterministic Contract and retain labels separately."""

    policy = contract if isinstance(contract, ContractPolicy) else ContractPolicy.from_dict(contract)
    trace = trace_from_agentdojo_run(run, source=source)
    differences = policy.check(trace, trace)
    tool_calls = [event for event in trace.events if event["type"] == "tool_call"]
    labels: Dict[str, Any] = {}
    for key in ("utility", "security"):
        if key in run:
            if not isinstance(run[key], bool):
                raise ValueError(f"AgentDojo run.{key} must be boolean when present")
            labels[key] = run[key]
    report: Dict[str, Any] = {
        "schema_version": "0.1",
        "report_type": "agentdojo_external_validation",
        "contract_passed": not differences,
        "difference_count": len(differences),
        "differences": differences,
        "contract": policy.to_dict(),
        "external_oracle": labels,
        "trace_summary": {
            "run_id": trace.run_id,
            "event_count": len(trace.events),
            "tool_call_count": len(tool_calls),
            "tool_names": [event["tool"] for event in tool_calls],
            "final_answer_present": True,
        },
        "provenance": {
            "source": deepcopy(dict(source)) if source is not None else None,
            "suite_name": run.get("suite_name"),
            "pipeline_name": run.get("pipeline_name"),
            "user_task_id": run.get("user_task_id"),
            "injection_task_id": run.get("injection_task_id"),
            "attack_type": run.get("attack_type"),
        },
        "label_boundary": (
            "AgentDojo utility/security labels are retained as external oracle values; "
            "they are not written into AgentTrace or used to build the Contract"
        ),
    }
    report["report_sha256"] = hashlib.sha256(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return report


__all__ = ["evaluate_agentdojo_run", "trace_from_agentdojo_run"]
