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
import re
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

TAU2_TELECOM_WRITE_TOOLS = frozenset(
    {
        "disconnect_vpn",
        "enable_roaming",
        "grant_app_permission",
        "make_payment",
        "refuel_data",
        "reboot_device",
        "reset_apn_settings",
        "reseat_sim_card",
        "resume_line",
        "send_payment_request",
        "set_network_mode_preference",
        "toggle_airplane_mode",
        "toggle_data",
        "toggle_data_saver_mode",
        "toggle_roaming",
        "toggle_wifi_calling",
        "transfer_to_human_agents",
    }
)

TAU2_TELECOM_OBSERVATION_TOOLS = frozenset(
    {
        "can_send_mms",
        "check_apn_settings",
        "check_app_permissions",
        "check_app_status",
        "check_data_restriction_status",
        "check_network_mode_preference",
        "check_network_status",
        "check_payment_request",
        "check_service_status",
        "check_sim_status",
        "check_status_bar",
        "check_vpn_status",
        "check_wifi_calling_status",
        "check_wifi_status",
        "get_bills_for_customer",
        "get_customer_by_id",
        "get_customer_by_name",
        "get_customer_by_phone",
        "get_data_usage",
        "get_details_by_id",
        "run_speed_test",
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
    """Apply only semantics declared by the upstream domain tools."""

    normalized = deepcopy(dict(arguments))
    if tool == "transfer_to_human_agents":
        # Handoff summaries are generated prose, not a stable business key.
        # The telecom task oracle checks that escalation happened, while the
        # exact wording varies with the diagnosed issue.
        normalized.pop("summary", None)
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
    task: Mapping[str, Any],
    write_tools: Iterable[str],
    requestors: Iterable[str] | None = None,
) -> List[Dict[str, Any]]:
    actions = _array(
        _evaluation_criteria(task).get("actions", []),
        "tau2 task evaluation_criteria.actions",
    )
    allowed_requestors = set(requestors) if requestors is not None else None
    expected: List[Dict[str, Any]] = []
    for index, raw_action in enumerate(actions):
        action = _object(raw_action, f"tau2 task action[{index}]")
        tool = action.get("name")
        if tool not in write_tools:
            continue
        if allowed_requestors is not None and action.get("requestor", "assistant") not in allowed_requestors:
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
    include_user_tools: bool = False,
    preserve_raw_arguments: bool = False,
) -> AgentTrace:
    """Convert one half-duplex tau2 simulation into a validated AgentTrace.

    ``preserve_raw_arguments`` is intended for domain evidence parsers. The
    default canonical form keeps Contract comparisons deterministic; telecom
    validation can retain generated handoff prose for environment evidence
    while checking an assistant-only canonical trace separately.
    """

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
        if role == "assistant" or (include_user_tools and role == "user"):
            calls = _array(message.get("tool_calls", []) or [], f"tau2 message[{message_index}].tool_calls")
            for call_index, raw_call in enumerate(calls):
                call = _object(raw_call, f"tau2 message[{message_index}].tool_calls[{call_index}]")
                requestor = call.get("requestor", role)
                if requestor not in {"assistant", "user"}:
                    continue
                if requestor == "user" and not include_user_tools:
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
                        "arguments": (
                            deepcopy(dict(arguments))
                            if preserve_raw_arguments
                            else _canonical_arguments(tool, arguments)
                        ),
                        "metadata": {
                            "tau2_turn_idx": message.get("turn_idx"),
                            "requestor": requestor,
                        },
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
    expected_requestors: Iterable[str] | None = None,
    allow_successful_write_extras: bool = False,
    tool_aliases: Iterable[Sequence[str]] = (
        ("exchange_delivered_order_items", "modify_pending_order_items"),
    ),
    idempotent_tools: Iterable[str] = (
        "modify_pending_order_address",
        "modify_user_address",
    ),
) -> ContractPolicy:
    """Build a deterministic contract from one tau2 domain task."""

    expected_writes = _expected_writes(
        _object(task, "tau2 task"),
        write_tools,
        requestors=expected_requestors,
    )
    if not expected_writes:
        raise ValueError("tau2 task has no write action to validate")
    extra_calls: List[Any] = sorted(observation_tools)
    if allow_successful_write_extras:
        extra_calls.extend(sorted(write_tools))
    else:
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
    aliases = [list(group) for group in tool_aliases]
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
                "tool_aliases": aliases,
                "attempt_policy": {
                    # tau2's external reward can mark an expected write as
                    # successful even when its tool response is an error;
                    # preserve that benchmark oracle explicitly.
                    "require_success": False,
                    "allow_failed_before_success": True,
                    "max_failed_attempts": 1,
                },
                "idempotent_tools": sorted(set(idempotent_tools)),
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


def build_tau2_telecom_contract(task: Mapping[str, Any]) -> ContractPolicy:
    """Build a deterministic contract from a tau2 telecom task specification."""

    return _build_tau2_contract(
        task,
        write_tools=TAU2_TELECOM_WRITE_TOOLS,
        observation_tools=TAU2_TELECOM_OBSERVATION_TOOLS,
        expected_requestors=("assistant",),
        allow_successful_write_extras=True,
        tool_aliases=(),
        idempotent_tools=(),
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _telecom_result_records(trace: AgentTrace) -> List[Dict[str, Any]]:
    calls = {
        event.get("call_id"): event
        for event in trace.events
        if event.get("type") == "tool_call"
    }
    records: List[Dict[str, Any]] = []
    for event in trace.events:
        if event.get("type") != "tool_result":
            continue
        call = calls.get(event.get("call_id"), {})
        records.append(
            {
                "tool": call.get("tool"),
                "arguments": call.get("arguments", {}),
                "result": event.get("result"),
                "is_error": bool(event.get("is_error", False)),
            }
        )
    return records


def _telecom_result_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, sort_keys=True)


def _telecom_environment_assertion_met(
    assertion: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> bool:
    name = assertion.get("func_name")
    arguments = _object(assertion.get("arguments", {}), "telecom environment assertion.arguments")
    if name == "assert_service_status":
        expected = str(arguments.get("expected_status", "")).lower()
        direct_records = [
            record
            for record in reversed(records)
            if record.get("tool") in {
                "check_network_status",
                "check_status_bar",
                "toggle_airplane_mode",
                "toggle_data",
                "reboot_device",
                "reseat_sim_card",
            }
            and not record.get("is_error")
        ]
        for record in direct_records:
            text = _telecom_result_text(record.get("result")).lower()
            if record.get("tool") == "check_network_status":
                match = re.search(r"cellular connection:\s*([^\n]+)", text)
                if match:
                    return match.group(1).strip() == expected
            if expected == "no_service" and ("no signal" in text or "no service" in text):
                return True
            if expected == "connected" and "excellent" in text and "no signal" not in text:
                return True
        if expected == "no_service":
            for record in records:
                if record.get("tool") != "transfer_to_human_agents":
                    continue
                summary = str(record.get("arguments", {}).get("summary", "")).lower()
                if "no service" in summary or "no signal" in summary:
                    return True
            for record in reversed(records):
                if record.get("tool") != "get_details_by_id" or record.get("is_error"):
                    continue
                result = record.get("result")
                if isinstance(result, Mapping) and str(result.get("status", "")).lower() in {
                    "suspended",
                    "inactive",
                }:
                    return True
        if direct_records:
            return False
        for record in reversed(records):
            if record.get("is_error"):
                continue
            text = _telecom_result_text(record.get("result")).lower()
            if record.get("tool") == "get_details_by_id" and isinstance(record.get("result"), Mapping):
                status = str(record["result"].get("status", "")).lower()
                if status:
                    return (
                        (expected == "no_service" and status in {"suspended", "inactive"})
                        or (expected == "connected" and status == "active")
                    )
        return False
    if name == "assert_mobile_data_status":
        expected = bool(arguments.get("expected_status"))
        for record in reversed(records):
            if record.get("tool") not in {
                "check_network_status",
                "check_status_bar",
                "toggle_data",
                "toggle_airplane_mode",
            } or record.get("is_error"):
                continue
            text = _telecom_result_text(record.get("result")).lower()
            if "mobile data enabled:" in text:
                return ("mobile data enabled: yes" in text) == expected
            if "data enabled" in text or "data disabled" in text:
                return ("data enabled" in text and "data disabled" not in text) == expected
        return False
    if name == "assert_internet_speed":
        expected_speed = arguments.get("expected_speed")
        expected_description = str(arguments.get("expected_desc", "")).lower()
        try:
            expected_speed_value = float(expected_speed)
        except (TypeError, ValueError):
            return False
        for record in reversed(records):
            if record.get("tool") != "run_speed_test" or record.get("is_error"):
                continue
            text = _telecom_result_text(record.get("result"))
            speed = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*Mbps", text, re.IGNORECASE)
            description = re.search(r"\(([^)]+)\)", text)
            if "speed test failed" in text.lower() or speed is None:
                return False
            return (
                float(speed.group(1)) >= expected_speed_value
                and (
                    not expected_description
                    or (description is not None and description.group(1).lower() == expected_description)
                )
            )
        return False
    if name == "assert_data_refueling_amount":
        expected_amount = arguments.get("expected_amount")
        expected_line = arguments.get("line_id")
        expected_customer = arguments.get("customer_id")
        try:
            expected_value = float(expected_amount)
        except (TypeError, ValueError):
            return False
        for record in reversed(records):
            if record.get("is_error"):
                continue
            record_arguments = record.get("arguments", {})
            if (
                expected_customer is not None
                and record_arguments.get("customer_id") not in {None, expected_customer}
            ):
                continue
            if expected_line is not None and record_arguments.get("line_id") not in {None, expected_line}:
                continue
            result = record.get("result")
            if not isinstance(result, Mapping):
                continue
            if result.get("line_id") not in {None, expected_line}:
                continue
            for key in ("new_data_refueling_gb", "data_refueling_gb"):
                if key not in result:
                    continue
                try:
                    return float(result[key]) == expected_value
                except (TypeError, ValueError):
                    return False
        return False
    if name == "assert_can_send_mms":
        expected = bool(arguments.get("expected_status"))
        for record in reversed(records):
            if record.get("tool") != "can_send_mms" or record.get("is_error"):
                continue
            text = _telecom_result_text(record.get("result")).lower()
            if "cannot" in text or "can't" in text or "unable" in text:
                return not expected
            if "can send mms" in text:
                return expected
        return False
    if name == "assert_no_overdue_bill":
        bill_id = arguments.get("overdue_bill_id")
        for record in reversed(records):
            if record.get("tool") != "get_bills_for_customer" or record.get("is_error"):
                text = _telecom_result_text(record.get("result"))
                if (
                    record.get("tool") == "make_payment"
                    and not record.get("is_error")
                    and bill_id is not None
                    and str(bill_id) in text
                ):
                    return True
                continue
            result = record.get("result")
            if not isinstance(result, list):
                continue
            for bill in result:
                if not isinstance(bill, Mapping) or bill.get("bill_id") != bill_id:
                    continue
                return str(bill.get("status", "")).lower() != "overdue"
        return False
    return False


def _telecom_environment_differences(
    task: Mapping[str, Any], trace: AgentTrace
) -> List[Dict[str, Any]]:
    differences: List[Dict[str, Any]] = []
    records = _telecom_result_records(trace)
    assertions = _array(
        _evaluation_criteria(task).get("env_assertions", []) or [],
        "tau2 task evaluation_criteria.env_assertions",
    )
    for index, raw_assertion in enumerate(assertions):
        assertion = _object(raw_assertion, f"telecom environment assertion[{index}]")
        if _telecom_environment_assertion_met(assertion, records):
            continue
        differences.append(
            {
                "category": "environment_assertion",
                "path": f"evaluation_criteria.env_assertions[{index}]",
                "baseline": deepcopy(dict(assertion)),
                "candidate": {"met": False},
                "message": "telecom environment assertion was not evidenced by the trace",
            }
        )
    if trace.metadata.get("termination_reason") == "max_steps":
        differences.append(
            {
                "category": "termination",
                "path": "metadata.termination_reason",
                "baseline": "user_stop",
                "candidate": "max_steps",
                "message": "simulation terminated at the step limit",
            }
        )
    return differences


def _evaluate_tau2_results(
    payload: Mapping[str, Any],
    *,
    domain: str,
    write_tools: Iterable[str],
    contract_builder: Callable[[Mapping[str, Any]], ContractPolicy],
    source: Mapping[str, Any] | None = None,
    sample_limit: int = 5,
    include_user_tools: bool = False,
    expected_requestors: Iterable[str] | None = None,
    environment_checker: Callable[[Mapping[str, Any], AgentTrace], List[Dict[str, Any]]] | None = None,
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
        if not _expected_writes(task, write_tools, requestors=expected_requestors):
            excluded += 1
            continue
        trace = trace_from_tau2_simulation(
            simulation,
            task,
            source=source_info,
            agent=agent_identity,
            domain=domain,
            include_user_tools=include_user_tools,
            preserve_raw_arguments=include_user_tools,
        )
        contract = contract_builder(task)
        contract_trace = trace
        if include_user_tools:
            contract_trace = trace_from_tau2_simulation(
                simulation,
                task,
                source=source_info,
                agent=agent_identity,
                domain=domain,
            )
        differences = contract.check(contract_trace, contract_trace)
        if environment_checker is not None:
            differences.extend(environment_checker(task, trace))
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


def evaluate_tau2_telecom_results(
    payload: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None = None,
    sample_limit: int = 5,
) -> Dict[str, Any]:
    """Compare telecom contracts with tau2's independent reward labels."""

    return _evaluate_tau2_results(
        payload,
        domain="telecom",
        write_tools=TAU2_TELECOM_WRITE_TOOLS,
        contract_builder=build_tau2_telecom_contract,
        source=source,
        sample_limit=sample_limit,
        include_user_tools=True,
        expected_requestors=("assistant",),
        environment_checker=_telecom_environment_differences,
    )
