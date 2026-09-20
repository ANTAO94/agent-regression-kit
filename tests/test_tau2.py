import unittest

from agent_regression import (
    build_tau2_airline_contract,
    build_tau2_retail_contract,
    build_tau2_telecom_contract,
    evaluate_tau2_airline_results,
    evaluate_tau2_retail_results,
    evaluate_tau2_telecom_results,
    split_tau2_payload_by_task,
    trace_from_tau2_simulation,
)


def task(task_id="1", communicate=None):
    return {
        "id": task_id,
        "evaluation_criteria": {
            "actions": [
                {
                    "action_id": f"{task_id}_0",
                    "name": "return_delivered_order_items",
                    "arguments": {
                        "order_id": "#W1",
                        "item_ids": ["item-b", "item-a"],
                        "payment_method_id": "card-1",
                    },
                }
            ],
            "communicate_info": communicate or [],
        },
    }


def simulation(simulation_id, *, reward, calls, text="done", task_id="1"):
    messages = []
    for index, (name, arguments, error) in enumerate(calls):
        call_id = f"call-{simulation_id}-{index}"
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "name": name,
                            "arguments": arguments,
                            "requestor": "assistant",
                        }
                    ],
                    "turn_idx": index * 2,
                },
                {
                    "role": "tool",
                    "id": call_id,
                    "content": "Error" if error else '{"status":"ok"}',
                    "error": error,
                    "turn_idx": index * 2 + 1,
                },
            ]
        )
    messages.append({"role": "assistant", "content": text, "tool_calls": None})
    return {
        "id": simulation_id,
        "task_id": task_id,
        "trial": 0,
        "termination_reason": "user_stop",
        "reward_info": {"reward": reward},
        "messages": messages,
    }


EXPECTED_ARGUMENTS = {
    "order_id": "#W1",
    "item_ids": ["item-a", "item-b"],
    "payment_method_id": "card-1",
}


class Tau2IntegrationTests(unittest.TestCase):
    def test_telecom_contract_separates_user_actions_from_agent_writes(self):
        source_task = {
            "id": "telecom-1",
            "evaluation_criteria": {
                "actions": [
                    {"requestor": "user", "name": "toggle_data", "arguments": {}},
                    {
                        "requestor": "assistant",
                        "name": "transfer_to_human_agents",
                        "arguments": {"summary": "I cannot fix the issue."},
                    },
                ],
                "env_assertions": [
                    {
                        "func_name": "assert_mobile_data_status",
                        "arguments": {"expected_status": True},
                    }
                ],
                "communicate_info": [],
            },
        }
        source_simulation = {
            "id": "telecom-pass",
            "task_id": "telecom-1",
            "trial": 0,
            "termination_reason": "user_stop",
            "reward_info": {"reward": 1.0},
            "messages": [
                {
                    "role": "user",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "user-call",
                            "name": "toggle_data",
                            "arguments": {},
                            "requestor": "user",
                        }
                    ],
                },
                {
                    "role": "tool",
                    "id": "user-call",
                    "content": "Mobile Data is now ON. Status Bar: Data Enabled",
                    "error": False,
                },
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "assistant-call",
                            "name": "transfer_to_human_agents",
                            "arguments": {"summary": "A generated handoff summary."},
                            "requestor": "assistant",
                        }
                    ],
                },
                {
                    "role": "tool",
                    "id": "assistant-call",
                    "content": "Transfer successful",
                    "error": False,
                },
                {"role": "assistant", "content": "Transferred", "tool_calls": None},
            ],
        }
        trace = trace_from_tau2_simulation(
            source_simulation,
            source_task,
            domain="telecom",
            include_user_tools=True,
            preserve_raw_arguments=True,
        )
        self.assertEqual("user", trace.events[0]["metadata"]["requestor"])
        self.assertEqual(
            "A generated handoff summary.",
            trace.events[2]["arguments"]["summary"],
        )
        report = evaluate_tau2_telecom_results(
            {
                "info": {"agent_info": {"implementation": "test", "llm": "fixture"}},
                "tasks": [source_task],
                "simulations": [source_simulation],
            },
            source={"tag": "fixture"},
        )
        self.assertEqual({"true_pass": 1, "true_block": 0, "false_alarm": 0, "missed_failure": 0}, report["confusion_matrix"])
        self.assertEqual("telecom", report["project"]["domain"])
        self.assertEqual([], build_tau2_telecom_contract(source_task).check(
            trace_from_tau2_simulation(source_simulation, source_task, domain="telecom"),
            trace_from_tau2_simulation(source_simulation, source_task, domain="telecom"),
        ))

    def test_airline_contract_can_ignore_explicit_payment_noise(self):
        source_task = {
            "id": "airline-1",
            "evaluation_criteria": {
                "actions": [
                    {
                        "name": "update_reservation_flights",
                        "arguments": {
                            "reservation_id": "R1",
                            "cabin": "economy",
                            "flights": [{"flight_number": "HAT001", "date": "2024-05-20"}],
                        },
                    }
                ],
                "communicate_info": [],
            },
        }
        source_simulation = simulation(
            "airline-pass",
            reward=1.0,
            calls=[
                (
                    "update_reservation_flights",
                    {
                        "reservation_id": "R1",
                        "cabin": "economy",
                        "flights": [{"flight_number": "HAT001", "date": "2024-05-20"}],
                        "payment_id": "gift_card-1",
                    },
                    False,
                )
            ],
        )
        trace = trace_from_tau2_simulation(
            source_simulation,
            source_task,
            domain="airline",
        )
        self.assertEqual([], build_tau2_airline_contract(source_task).check(trace, trace))

    def test_task_split_is_disjoint_and_does_not_read_reward_labels(self):
        payload = {
            "tasks": [{"id": "task-a"}, {"id": "task-b"}, {"id": "task-c"}],
            "simulations": [
                {"id": "sim-a", "task_id": "task-a"},
                {"id": "sim-b", "task_id": "task-b"},
                {"id": "sim-c", "task_id": "task-c"},
            ],
        }
        split = split_tau2_payload_by_task(
            payload,
            holdout_modulus=3,
            holdout_bucket_limit=1,
        )
        calibration_ids = {task["id"] for task in split["calibration"]["tasks"]}
        holdout_ids = {task["id"] for task in split["holdout"]["tasks"]}
        self.assertTrue(calibration_ids.isdisjoint(holdout_ids))
        self.assertEqual({"task-a", "task-b", "task-c"}, calibration_ids | holdout_ids)
        self.assertEqual(3, split["provenance"]["task_count"])
        self.assertEqual(
            3,
            split["provenance"]["holdout_task_count"]
            + split["provenance"]["calibration_task_count"],
        )
        for partition in (split["calibration"], split["holdout"]):
            for simulation in partition["simulations"]:
                self.assertNotIn("reward", simulation)

    def test_airline_external_report_is_domain_scoped(self):
        source_task = {
            "id": "airline-1",
            "evaluation_criteria": {
                "actions": [
                    {
                        "name": "update_reservation_flights",
                        "arguments": {
                            "reservation_id": "R1",
                            "cabin": "economy",
                            "flights": [{"flight_number": "HAT001", "date": "2024-05-20"}],
                        },
                    }
                ],
                "communicate_info": [],
            },
        }
        payload = {
            "info": {
                "git_commit": "airline-upstream",
                "agent_info": {"implementation": "llm_agent", "llm": "test-model"},
            },
            "tasks": [source_task],
            "simulations": [
                simulation(
                    "airline-pass",
                    reward=1.0,
                    calls=[
                        (
                            "update_reservation_flights",
                            {
                                "reservation_id": "R1",
                                "cabin": "economy",
                                "flights": [{"flight_number": "HAT001", "date": "2024-05-20"}],
                                "payment_id": "gift_card-1",
                            },
                            False,
                        )
                    ],
                    task_id="airline-1",
                )
            ],
        }
        report = evaluate_tau2_airline_results(payload, source={"tag": "v1.0.1"})
        self.assertEqual("airline", report["project"]["domain"])
        self.assertEqual(1, report["confusion_matrix"]["true_pass"])
        self.assertEqual(0, report["confusion_matrix"]["false_alarm"])

    def test_trace_imports_tools_without_leaking_the_external_reward(self):
        source_task = task(communicate=["refund submitted"])
        source_simulation = simulation(
            "pass",
            reward=1.0,
            calls=[("return_delivered_order_items", EXPECTED_ARGUMENTS, False)],
            text="Refund submitted",
        )
        trace = trace_from_tau2_simulation(source_simulation, source_task)
        trace.validate()
        self.assertEqual(["tool_call", "tool_result", "final_answer"], [event["type"] for event in trace.events])
        self.assertEqual(["item-a", "item-b"], trace.events[0]["arguments"]["item_ids"])
        self.assertTrue(trace.events[-1]["claims"]["communication_met"])
        self.assertNotIn("reward", repr(trace.to_dict()).lower())

    def test_contract_allows_failed_attempt_before_the_expected_success(self):
        source_task = task()
        source_simulation = simulation(
            "retry",
            reward=1.0,
            calls=[
                (
                    "return_delivered_order_items",
                    {**EXPECTED_ARGUMENTS, "payment_method_id": "bad-card"},
                    True,
                ),
                ("return_delivered_order_items", EXPECTED_ARGUMENTS, False),
            ],
        )
        trace = trace_from_tau2_simulation(source_simulation, source_task)
        self.assertEqual([], build_tau2_retail_contract(source_task).check(trace, trace))

    def test_contract_blocks_missing_communication_and_unexpected_successful_write(self):
        source_task = task(communicate=["confirmation 42"])
        source_simulation = simulation(
            "wrong",
            reward=0.0,
            calls=[
                (
                    "return_delivered_order_items",
                    {**EXPECTED_ARGUMENTS, "payment_method_id": "other-card"},
                    False,
                )
            ],
            text="done",
        )
        trace = trace_from_tau2_simulation(source_simulation, source_task)
        categories = {
            item["category"]
            for item in build_tau2_retail_contract(source_task).check(trace, trace)
        }
        self.assertIn("behavior_path", categories)
        self.assertIn("contract_assertion", categories)

    def test_external_report_keeps_confusion_matrix_honest(self):
        source_task = task(communicate=["confirmation 42"])
        payload = {
            "info": {
                "git_commit": "upstream-commit",
                "agent_info": {"implementation": "llm_agent", "llm": "published-model"},
            },
            "tasks": [source_task],
            "simulations": [
                simulation(
                    "true-pass",
                    reward=1.0,
                    calls=[("return_delivered_order_items", EXPECTED_ARGUMENTS, False)],
                    text="confirmation 42",
                ),
                simulation("true-block", reward=0.0, calls=[], text="missing"),
                simulation(
                    "false-alarm",
                    reward=1.0,
                    calls=[
                        (
                            "return_delivered_order_items",
                            {**EXPECTED_ARGUMENTS, "payment_method_id": "equivalent-card"},
                            False,
                        )
                    ],
                    text="confirmation 42",
                ),
                simulation(
                    "missed-failure",
                    reward=0.0,
                    calls=[("return_delivered_order_items", EXPECTED_ARGUMENTS, False)],
                    text="confirmation 42",
                ),
            ],
        }
        report = evaluate_tau2_retail_results(payload, source={"tag": "v1.0.1"})
        self.assertEqual(
            {"true_pass": 1, "true_block": 1, "false_alarm": 1, "missed_failure": 1},
            report["confusion_matrix"],
        )
        self.assertEqual(0.5, report["metrics"]["accuracy"])
        self.assertIn("reward is read after", report["benchmark"]["decision_boundary"])

    def test_unknown_task_and_read_only_task_are_explicit(self):
        with self.assertRaisesRegex(ValueError, "unknown task_id"):
            evaluate_tau2_retail_results(
                {"info": {}, "tasks": [], "simulations": [simulation("x", reward=0, calls=[])]}
            )
        read_only = {
            "id": "2",
            "evaluation_criteria": {
                "actions": [{"name": "get_order_details", "arguments": {"order_id": "#W1"}}],
                "communicate_info": [],
            },
        }
        report = evaluate_tau2_retail_results(
            {
                "info": {},
                "tasks": [read_only],
                "simulations": [simulation("read", reward=1, calls=[], task_id="2")],
            }
        )
        self.assertEqual(0, report["scope"]["eligible_write_scenarios"])
        self.assertEqual(1, report["scope"]["excluded_without_write_action"])
        with self.assertRaisesRegex(ValueError, "no write action"):
            build_tau2_retail_contract(read_only)


if __name__ == "__main__":
    unittest.main()
