"""Import and evaluate published tau2-bench retail trajectories.

The integration intentionally keeps the upstream reward outside AgentTrace and
ContractPolicy.  The reward is consulted only after the contract decision so
the external benchmark remains an independent oracle instead of becoming an
answer hidden in the candidate evidence.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

from .contracts import ContractPolicy
from .model import AgentTrace


TAU2_RETAIL_WRITE_TOOLS = frozenset(
    {
        "cancel_pending_order",
        "exchange_delivered_order_items",
        "modify_pending_order_address",
        "modify_pending_order_items",
        "modify_pending_order_payment",
        "modify_user_address",
        "return_delivered_order_items",
    }
)

TAU2_RETAIL_OBSERVATION_TOOLS = frozenset(
    {
        "calculate",
        "find_user_id_by_email",
        "find_user_id_by_name_zip",
        "get_item_details",
        "get_order_details",
        "get_product_details",
        "get_user_details",
        "list_all_product_types",
        "transfer_to_human_agents",
    }
)

TAU2_AIRLINE_WRITE_TOOLS = frozenset(
    {
        "book_reservation",
        "cancel_reservation",
        "send_certificate",
        "update_reservation_baggages",
        "update_reservation_flights",
        "update_reservation_passengers",
    }
)

TAU2_AIRLINE_OBSERVATION_TOOLS = frozenset(
    {
        "calculate",
        "get_flight_status",
        "get_reservation_details",
        "get_user_details",
        "list_all_airports",
        "search_direct_flight",
        "search_onestop_flight",
        "transfer_to_human_agents",
    }
)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _canonical_arguments(tool: str, arguments: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply only order semantics declared by the upstream retail tools."""

    normalized = deepcopy(dict(arguments))
    item_ids = normalized.get("item_ids")
    if tool == "return_delivered_order_items" and isinstance(item_ids, list):
        normalized["item_ids"] = sorted(item_ids, key=repr)
    if tool in {"exchange_delivered_order_items", "modify_pending_order_items"}:
        new_item_ids = normalized.get("new_item_ids")
        if (
            isinstance(item_ids, list)
            and isinstance(new_item_ids, list)
            and len(item_ids) == len(new_item_ids)
        ):
            pairs = sorted(zip(item_ids, new_item_ids), key=repr)
            normalized["item_ids"] = [item for item, _ in pairs]
            normalized["new_item_ids"] = [new_item for _, new_item in pairs]
    return normalized


def _evaluation_criteria(task: Mapping[str, Any]) -> Mapping[str, Any]:
    return _object(task.get("evaluation_criteria", {}), "tau2 task evaluation_criteria")


def _expected_writes(
    task: Mapping[str, Any], write_tools: Iterable[str]
) -> List[Dict[str, Any]]:
    actions = _array(
        _evaluation_criteria(task).get("actions", []),
        "tau2 task evaluation_criteria.actions",
    )
    expected: List[Dict[str, Any]] = []
    for index, raw_action in enumerate(actions):
        action = _object(raw_action, f"tau2 task action[{index}]")
        tool = action.get("name")
        if tool not in write_tools:
            continue
        arguments = _object(action.get("arguments", {}), f"tau2 task action[{index}].arguments")
        expected.append(
            {
                "tool": tool,
                "arguments": _canonical_arguments(str(tool), arguments),
            }
        )
    return expected


def _communication_claims(
    task: Mapping[str, Any], messages: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    required = _array(
        _evaluation_criteria(task).get("communicate_info", []) or [],
        "tau2 task evaluation_criteria.communicate_info",
    )
    assistant_text = "\n".join(
        str(message["content"])
        for message in messages
        if message.get("role") == "assistant" and isinstance(message.get("content"), str)
    ).lower().replace(",", "")
    normalized_required = [str(item) for item in required]
    return {
        "communication_met": all(item.lower() in assistant_text for item in normalized_required),
        "required_communication": normalized_required,
    }

def _decode_tool_content(content: Any) -> Any:
    if not isinstance(content, str):
        return deepcopy(content)
    try:
        return json.loads(content)
    except (TypeError, ValueError):
        return content


def trace_from_tau2_simulation(
    simulation: Mapping[str, Any],
    task: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None = None,
    agent: Mapping[str, Any] | None = None,
    domain: str = "retail",
) -> AgentTrace:
    """Convert one half-duplex tau2 simulation into a validated AgentTrace."""

    simulation = _object(simulation, "tau2 simulation")
    task = _object(task, "tau2 task")
    messages = [
        _object(message, f"tau2 message[{index}]")
        for index, message in enumerate(
            _array(simulation.get("messages", []), "tau2 simulation.messages")
        )
    ]
    events: List[Dict[str, Any]] = []
    pending: Dict[str, int] = {}
    seen_call_ids: set[str] = set()
    orphan_results = 0

    def append(event: Dict[str, Any]) -> None:
        event["sequence"] = len(events) + 1
        events.append(event)

    for message_index, message in enumerate(messages):
        role = message.get("role")
        if role == "assistant":
            calls = _array(message.get("tool_calls", []) or [], f"tau2 message[{message_index}].tool_calls")
            for call_index, raw_call in enumerate(calls):
                call = _object(raw_call, f"tau2 message[{message_index}].tool_calls[{call_index}]")
                if call.get("requestor", "assistant") != "assistant":
                    continue
                raw_call_id = call.get("id")
                call_id = raw_call_id if isinstance(raw_call_id, str) and raw_call_id else f"tau2-{message_index}-{call_index}"
                if call_id in seen_call_ids:
                    call_id = f"{call_id}-{message_index}-{call_index}"
                tool = call.get("name")
                if not isinstance(tool, str) or not tool:
                    raise ValueError("tau2 assistant tool call name must be a non-empty string")
                arguments = _object(call.get("arguments", {}), "tau2 assistant tool call arguments")
                seen_call_ids.add(call_id)
                pending[call_id] = message_index
                append(
                    {
                        "type": "tool_call",
                        "call_id": call_id,
                        "tool": tool,
                        "arguments": _canonical_arguments(tool, arguments),
                        "metadata": {"tau2_turn_idx": message.get("turn_idx")},
                    }
                )
        elif role == "tool":
            call_id = message.get("id")
            if not isinstance(call_id, str) or call_id not in pending:
                orphan_results += 1
                continue
            is_error = bool(message.get("error", False))
            event: Dict[str, Any] = {
                "type": "tool_result",
                "call_id": call_id,
                "result": _decode_tool_content(message.get("content")),
                "is_error": is_error,
                "metadata": {"tau2_turn_idx": message.get("turn_idx")},
            }
            if is_error:
                event["error"] = str(message.get("content", "tau2 tool error"))
            append(event)
            del pending[call_id]

    for call_id in list(pending):
        append(
            {
                "type": "tool_result",
                "call_id": call_id,
                "result": {"error": "missing tau2 tool result"},
                "is_error": True,
                "error": "missing tau2 tool result",
                "metadata": {"source": "tau2-import"},
            }
        )
        del pending[call_id]

    final_text = next(
        (
            str(message["content"])
            for message in reversed(messages)
            if message.get("role") == "assistant" and isinstance(message.get("content"), str)
        ),
        "",
    )
    append(
        {
            "type": "final_answer",
            "text": final_text,
            "claims": _communication_claims(task, messages),
        }
    )

    task_id = str(simulation.get("task_id", task.get("id", "unknown")))
    run_id = str(simulation.get("id") or f"tau2-task-{task_id}")
    identity = dict(agent or {"name": "tau2-published-agent", "framework": "tau2-bench"})
    metadata = {
        "integration": "tau2-bench",
        "domain": domain,
        "source_simulation_id": run_id,
        "task_id": task_id,
        "trial": simulation.get("trial"),
        "seed": simulation.get("seed"),
        "termination_reason": simulation.get("termination_reason"),
        "orphan_tool_results": orphan_results,
        "source": deepcopy(dict(source or {})),
    }
    trace = AgentTrace(
        schema_version="0.1",
        run_id=run_id,
        agent=identity,
        events=events,
        metadata=metadata,
    )
    trace.validate()
    return trace


def _build_tau2_contract(
    task: Mapping[str, Any],
    *,
    write_tools: Iterable[str],
    observation_tools: Iterable[str],
    ignore_argument_paths: Iterable[str] = (),
    state_ignore_argument_paths: Iterable[str] | None = None,
) -> ContractPolicy:
    """Build a deterministic contract from one tau2 domain task."""

    expected_writes = _expected_writes(_object(task, "tau2 task"), write_tools)
    if not expected_writes:
        raise ValueError("tau2 task has no write action to validate")
    extra_calls: List[Any] = sorted(observation_tools)
    extra_calls.extend(
        {"tool": tool, "is_error": True}
        for tool in sorted(write_tools)
    )
    ignored_arguments = sorted(set(ignore_argument_paths))
    state_ignored_arguments = sorted(
        set(
            ignore_argument_paths
            if state_ignore_argument_paths is None
            else state_ignore_argument_paths
        )
    )
    return ContractPolicy.from_dict(
        {
            "assertions": [
                {
                    "path": "final_answer.claims.communication_met",
                    "equals": True,
                }
            ],
            "path_rules": {
                "mode": "unordered_subset",
                "any_of": [expected_writes],
                "extra_calls": extra_calls,
                "ignore_argument_paths": ignored_arguments,
            },
            "state_equivalence": {
                "mode": "outcome",
                "ignore_argument_paths": state_ignored_arguments,
                "tool_aliases": [
                    [
                        "exchange_delivered_order_items",
                        "modify_pending_order_items",
                    ]
                ],
                "attempt_policy": {
                    # tau2's external reward can mark an expected write as
                    # successful even when its tool response is an error;
                    # preserve that benchmark oracle explicitly.
                    "require_success": False,
                    "allow_failed_before_success": True,
                    "max_failed_attempts": 1,
                },
                "idempotent_tools": [
                    "modify_pending_order_address",
                    "modify_user_address",
                ],
            },
        }
    )


def build_tau2_retail_contract(task: Mapping[str, Any]) -> ContractPolicy:
    """Build a deterministic contract from a tau2 retail task specification."""

    return _build_tau2_contract(
        task,
        write_tools=TAU2_RETAIL_WRITE_TOOLS,
        observation_tools=TAU2_RETAIL_OBSERVATION_TOOLS,
        state_ignore_argument_paths=("payment_method_id",),
    )


def build_tau2_airline_contract(task: Mapping[str, Any]) -> ContractPolicy:
    """Build a deterministic contract from a tau2 airline task specification."""

    return _build_tau2_contract(
        task,
        write_tools=TAU2_AIRLINE_WRITE_TOOLS,
        observation_tools=TAU2_AIRLINE_OBSERVATION_TOOLS,
        ignore_argument_paths=("payment_id",),
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _evaluate_tau2_results(
    payload: Mapping[str, Any],
    *,
    domain: str,
    write_tools: Iterable[str],
    contract_builder: Callable[[Mapping[str, Any]], ContractPolicy],
    source: Mapping[str, Any] | None = None,
    sample_limit: int = 5,
) -> Dict[str, Any]:
    """Compare one tau2 domain's deterministic contracts with reward labels."""

    if not isinstance(sample_limit, int) or isinstance(sample_limit, bool) or sample_limit < 0:
        raise ValueError("sample_limit must be a non-negative integer")
    payload = _object(payload, "tau2 results")
    tasks = {
        str(task.get("id")): task
        for index, raw_task in enumerate(_array(payload.get("tasks", []), "tau2 results.tasks"))
        for task in [_object(raw_task, f"tau2 task[{index}]")]
    }
    simulations = _array(payload.get("simulations", []), "tau2 results.simulations")
    info = _object(payload.get("info", {}), "tau2 results.info")
    agent_info = _object(info.get("agent_info", {}), "tau2 results.info.agent_info")
    agent_identity = {
        "name": str(agent_info.get("implementation") or "tau2-published-agent"),
        "model": str(agent_info.get("llm") or "unknown"),
        "framework": "tau2-bench",
    }
    source_info = deepcopy(dict(source or {}))
    outcomes: List[Dict[str, Any]] = []
    excluded = 0
    matrix: Counter[str] = Counter()
    samples: Dict[str, List[Dict[str, Any]]] = {
        "true_pass": [],
        "true_block": [],
        "false_alarm": [],
        "missed_failure": [],
    }

    for index, raw_simulation in enumerate(simulations):
        simulation = _object(raw_simulation, f"tau2 simulation[{index}]")
        task_id = str(simulation.get("task_id", ""))
        if task_id not in tasks:
            raise ValueError(f"tau2 simulation references unknown task_id {task_id!r}")
        task = tasks[task_id]
        if not _expected_writes(task, write_tools):
            excluded += 1
            continue
        trace = trace_from_tau2_simulation(
            simulation,
            task,
            source=source_info,
            agent=agent_identity,
            domain=domain,
        )
        contract = contract_builder(task)
        differences = contract.check(trace, trace)
        contract_passed = not differences
        reward_info = _object(simulation.get("reward_info", {}), "tau2 simulation.reward_info")
        reward = reward_info.get("reward")
        if not isinstance(reward, (int, float)) or isinstance(reward, bool):
            raise ValueError("tau2 simulation reward must be numeric")
        oracle_passed = float(reward) == 1.0
        if contract_passed and oracle_passed:
            classification = "true_pass"
        elif not contract_passed and not oracle_passed:
            classification = "true_block"
        elif not contract_passed and oracle_passed:
            classification = "false_alarm"
        else:
            classification = "missed_failure"
        matrix[classification] += 1
        outcome = {
            "simulation_id": trace.run_id,
            "task_id": task_id,
            "trial": simulation.get("trial"),
            "oracle_passed": oracle_passed,
            "contract_passed": contract_passed,
            "classification": classification,
            "difference_categories": sorted(
                {str(item.get("category")) for item in differences}
            ),
            "difference_paths": sorted({str(item.get("path")) for item in differences}),
        }
        outcomes.append(outcome)
        if len(samples[classification]) < sample_limit:
            samples[classification].append(deepcopy(outcome))

    eligible = len(outcomes)
    true_pass = matrix["true_pass"]
    true_block = matrix["true_block"]
    false_alarm = matrix["false_alarm"]
    missed_failure = matrix["missed_failure"]
    oracle_passes = true_pass + false_alarm
    oracle_failures = true_block + missed_failure
    return {
        "schema_version": "0.1",
        "report_type": "external_project_validation",
        "project": {
            "name": "tau2-bench",
            "domain": domain,
            **source_info,
        },
        "benchmark": {
            "dataset_git_commit": info.get("git_commit"),
            "agent": agent_identity,
            "oracle": "tau2 reward == 1.0",
            "decision_boundary": (
                "ContractPolicy sees task actions and trajectory evidence only; "
                "the tau2 reward is read after the contract decision"
            ),
        },
        "scope": {
            "total_simulations": len(simulations),
            "eligible_write_scenarios": eligible,
            "excluded_without_write_action": excluded,
            "contract_coverage": _rate(eligible, len(simulations)),
        },
        "confusion_matrix": {
            "true_pass": true_pass,
            "true_block": true_block,
            "false_alarm": false_alarm,
            "missed_failure": missed_failure,
        },
        "metrics": {
            "accuracy": _rate(true_pass + true_block, eligible),
            "failure_precision": _rate(true_block, true_block + false_alarm),
            "failure_recall": _rate(true_block, oracle_failures),
            "false_alarm_rate": _rate(false_alarm, oracle_passes),
            "missed_failure_rate": _rate(missed_failure, oracle_failures),
        },
        "samples": samples,
        "outcomes": outcomes,
    }


def evaluate_tau2_retail_results(
    payload: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None = None,
    sample_limit: int = 5,
) -> Dict[str, Any]:
    """Compare retail contracts with tau2's independent reward labels."""

    return _evaluate_tau2_results(
        payload,
        domain="retail",
        write_tools=TAU2_RETAIL_WRITE_TOOLS,
        contract_builder=build_tau2_retail_contract,
        source=source,
        sample_limit=sample_limit,
    )


def evaluate_tau2_airline_results(
    payload: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None = None,
    sample_limit: int = 5,
) -> Dict[str, Any]:
    """Compare airline contracts with tau2's independent reward labels."""

    return _evaluate_tau2_results(
        payload,
        domain="airline",
        write_tools=TAU2_AIRLINE_WRITE_TOOLS,
        contract_builder=build_tau2_airline_contract,
        source=source,
        sample_limit=sample_limit,
    )
