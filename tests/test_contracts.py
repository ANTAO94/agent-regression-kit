import unittest

from agent_regression import AgentTrace, ComparisonPolicy, ContractPolicy, compare_traces


def make_trace(
    *,
    tool="get_order",
    arguments=None,
    result=None,
    text="订单尚未发货。",
    claims=None,
):
    return AgentTrace.from_dict(
        {
            "schema_version": "0.1",
            "run_id": "contract-test",
            "agent": {"name": "contract-test"},
            "events": [
                {
                    "sequence": 1,
                    "type": "tool_call",
                    "call_id": "call-1",
                    "tool": tool,
                    "arguments": arguments or {"order_id": "123"},
                },
                {
                    "sequence": 2,
                    "type": "tool_result",
                    "call_id": "call-1",
                    "result": result or {"status": "not_shipped"},
                    "is_error": False,
                },
                {
                    "sequence": 3,
                    "type": "final_answer",
                    "text": text,
                    "claims": claims or {"order_status": "not_shipped"},
                },
            ],
        }
    )


def make_refund_trace(*, amount=88, order_id="123"):
    return AgentTrace.from_dict(
        {
            "schema_version": "0.1",
            "run_id": "refund-contract-test",
            "agent": {"name": "refund-contract-test"},
            "events": [
                {
                    "sequence": 1,
                    "type": "tool_call",
                    "call_id": "call-1",
                    "tool": "get_order",
                    "arguments": {"order_id": order_id, "tenant_id": "tenant-a"},
                },
                {
                    "sequence": 2,
                    "type": "tool_result",
                    "call_id": "call-1",
                    "result": {"order_id": order_id, "paid_amount": 88},
                    "is_error": False,
                },
                {
                    "sequence": 3,
                    "type": "tool_call",
                    "call_id": "call-2",
                    "tool": "refund_order",
                    "arguments": {"order_id": order_id, "amount": amount},
                },
                {
                    "sequence": 4,
                    "type": "tool_result",
                    "call_id": "call-2",
                    "result": {"order_id": order_id, "refunded_amount": amount},
                    "is_error": False,
                },
                {
                    "sequence": 5,
                    "type": "final_answer",
                    "text": "退款完成。",
                    "claims": {"order_id": order_id, "refund_amount": amount},
                },
            ],
            "metadata": {
                "input": {
                    "order_id": order_id,
                    "tenant_id": "tenant-a",
                }
            },
        }
    )


def make_path_trace(tools, *, run_id="path-mode-test"):
    events = []
    for index, tool in enumerate(tools, start=1):
        call_id = f"call-{index}"
        events.extend(
            [
                {
                    "sequence": len(events) + 1,
                    "type": "tool_call",
                    "call_id": call_id,
                    "tool": tool,
                    "arguments": {"order_id": "123"},
                },
                {
                    "sequence": len(events) + 2,
                    "type": "tool_result",
                    "call_id": call_id,
                    "result": {"tool": tool, "ok": True},
                    "is_error": False,
                },
            ]
        )
    events.append(
        {
            "sequence": len(events) + 1,
            "type": "final_answer",
            "text": "订单已处理。",
            "claims": {"order_id": "123", "status": "paid"},
        }
    )
    return AgentTrace.from_dict(
        {
            "schema_version": "0.1",
            "run_id": run_id,
            "agent": {"name": "path-mode-test"},
            "events": events,
        }
    )


class ContractTests(unittest.TestCase):
    def test_ignore_paths_and_timestamp_normalizer_remove_known_noise(self):
        baseline = make_trace(
            result={"status": "not_shipped", "request_id": "req-1", "created_at": "2026-09-18T08:00:00Z"}
        )
        candidate = make_trace(
            result={"status": "not_shipped", "request_id": "req-2", "created_at": "2026-09-18T08:01:00Z"}
        )
        policy = ComparisonPolicy(
            contract=ContractPolicy(
                ignore_paths=["tool_results[*].result.request_id"],
                normalizers=[
                    {"path": "tool_results[*].result.created_at", "type": "timestamp"}
                ],
            )
        )
        report = compare_traces(baseline, candidate, policy)
        self.assertTrue(report["passed"])
        self.assertEqual([], report["differences"])

    def test_assertions_required_and_forbidden_tools_and_step_limit(self):
        policy = ComparisonPolicy(
            contract=ContractPolicy(
                assertions=[
                    {"path": "final_answer.claims.order_status", "equals": "not_shipped"},
                    {"path": "tool_calls[0].arguments.order_id", "exists": True},
                ],
                must_call=[{"tool": "get_order", "arguments": {"order_id": "123"}}],
                must_not_call=[{"tool": "delete_order"}],
                max_steps=1,
            )
        )
        report = compare_traces(make_trace(), make_trace(), policy)
        self.assertTrue(report["passed"])

        bad = make_trace(tool="delete_order", claims={"order_status": "shipped"})
        report = compare_traces(bad, bad, policy)
        categories = {item["category"] for item in report["differences"]}
        self.assertFalse(report["passed"])
        self.assertEqual(
            {"contract_assertion", "required_tool", "forbidden_tool"}, categories
        )

    def test_contract_policy_rejects_unsupported_normalizers(self):
        with self.assertRaises(ValueError):
            ContractPolicy(normalizers=[{"path": "events", "type": "regex"}])

    def test_required_claims_fail_when_the_agent_omits_a_business_result(self):
        policy = ComparisonPolicy(
            contract=ContractPolicy(
                required_claims=["final_answer.claims.order_status"]
            )
        )
        missing = make_trace(claims={"order_id": "123"})
        report = compare_traces(missing, missing, policy)
        self.assertFalse(report["passed"])
        self.assertEqual("required_claim", report["differences"][0]["category"])

    def test_required_claims_are_serialized_and_validated(self):
        policy = ContractPolicy.from_dict(
            {"required_claims": ["final_answer.claims.order_status"]}
        )
        self.assertEqual(
            ["final_answer.claims.order_status"], policy.to_dict()["required_claims"]
        )
        with self.assertRaises(ValueError):
            ContractPolicy.from_dict({"required_claims": "final_answer.claims"})

    def test_relations_check_cross_step_business_values(self):
        policy = ComparisonPolicy(
            contract=ContractPolicy(
                relations=[
                    {
                        "left": "tool_calls[1].arguments.order_id",
                        "operator": "equals_path",
                        "right_path": "tool_results[0].result.order_id",
                        "message": "refund must target the order returned by lookup",
                    },
                    {
                        "left": "tool_calls[1].arguments.amount",
                        "operator": "less_or_equal_path",
                        "right_path": "tool_results[0].result.paid_amount",
                        "message": "refund amount must not exceed the paid amount",
                    },
                ]
            )
        )
        passed = compare_traces(make_refund_trace(), make_refund_trace(), policy)
        self.assertTrue(passed["passed"], passed["differences"])

        bad_amount = make_refund_trace(amount=880)
        report = compare_traces(make_refund_trace(), bad_amount, policy)
        self.assertFalse(report["passed"])
        relation = next(
            item for item in report["differences"] if item["category"] == "contract_relation"
        )
        self.assertEqual("tool_calls[1].arguments.amount", relation["path"])
        self.assertIn("paid amount", relation["message"])

    def test_relations_support_literal_comparisons_and_missing_evidence_fails(self):
        policy = ContractPolicy.from_dict(
            {
                "relations": [
                    {"left": "tool_calls[0].arguments.order_id", "operator": "equals", "value": "123"},
                    {"left": "tool_calls[0].arguments.amount", "operator": "less_or_equal", "value": 88},
                ]
            }
        )
        self.assertEqual(2, len(policy.to_dict()["relations"]))
        report = compare_traces(make_refund_trace(), make_refund_trace(), ComparisonPolicy(contract=policy))
        self.assertFalse(report["passed"])
        self.assertTrue(
            any(item["category"] == "contract_relation" for item in report["differences"])
        )

    def test_relations_reject_unknown_fields_and_invalid_operator(self):
        with self.assertRaisesRegex(ValueError, "unsupported relation fields"):
            ContractPolicy.from_dict(
                {"relations": [{"left": "a", "operator": "equals", "value": 1, "mesage": "typo"}]}
            )
        with self.assertRaisesRegex(ValueError, "unsupported contract relation operator"):
            ContractPolicy.from_dict(
                {"relations": [{"left": "a", "operator": "regex", "value": "x"}]}
            )

    def test_argument_rules_check_every_matching_tool_call(self):
        policy = ComparisonPolicy(
            contract=ContractPolicy.from_dict(
                {
                    "argument_rules": [
                        {
                            "tool": "get_order",
                            "path": "order_id",
                            "operator": "equals_path",
                            "right_path": "metadata.input.order_id",
                            "message": "lookup must use the requested order",
                        },
                        {
                            "tool": "get_order",
                            "path": "tenant_id",
                            "operator": "equals",
                            "value": "tenant-a",
                        },
                        {
                            "tool": "refund_order",
                            "path": "order_id",
                            "operator": "equals_path",
                            "right_path": "metadata.input.order_id",
                        },
                        {
                            "tool": "refund_order",
                            "path": "amount",
                            "operator": "less_or_equal_path",
                            "right_path": "tool_results[0].result.paid_amount",
                        },
                        {
                            "tool": "refund_order",
                            "path": "admin_override",
                            "operator": "absent",
                        },
                    ]
                }
            )
        )
        passed = compare_traces(
            make_refund_trace(), make_refund_trace(), policy
        )
        self.assertTrue(passed["passed"], passed["differences"])

        bad = make_refund_trace(amount=880)
        bad.events[0]["arguments"]["tenant_id"] = "tenant-b"
        bad.events[1]["result"]["paid_amount"] = 88
        bad.events[2]["arguments"]["order_id"] = "456"
        bad.events[2]["arguments"]["admin_override"] = True
        report = compare_traces(make_refund_trace(), bad, policy)
        self.assertFalse(report["passed"])
        argument_diffs = [
            item
            for item in report["differences"]
            if item["category"] == "tool_argument_policy"
        ]
        self.assertEqual(
            {
                "tool_calls[0].arguments.tenant_id",
                "tool_calls[1].arguments.order_id",
                "tool_calls[1].arguments.amount",
                "tool_calls[1].arguments.admin_override",
            },
            {item["path"] for item in argument_diffs},
        )

    def test_argument_rules_apply_to_multiple_calls_and_missing_tool_is_not_a_call_requirement(self):
        trace = make_refund_trace()
        second_call = {
            "sequence": 5,
            "type": "tool_call",
            "call_id": "call-3",
            "tool": "refund_order",
            "arguments": {"order_id": "123", "amount": 880},
        }
        second_result = {
            "sequence": 6,
            "type": "tool_result",
            "call_id": "call-3",
            "result": {"order_id": "123", "refunded_amount": 0},
            "is_error": True,
        }
        final_answer = trace.events.pop()
        trace.events.extend([second_call, second_result, final_answer])
        for sequence, event in enumerate(trace.events, start=1):
            event["sequence"] = sequence
        policy = ComparisonPolicy(
            contract=ContractPolicy.from_dict(
                {
                    "argument_rules": [
                        {
                            "tool": "refund_order",
                            "path": "amount",
                            "operator": "less_or_equal",
                            "value": 88,
                        },
                        {
                            "tool": "archive_order",
                            "path": "reason",
                            "operator": "absent",
                        },
                    ]
                }
            )
        )
        report = compare_traces(trace, trace, policy)
        self.assertFalse(report["passed"])
        self.assertEqual(
            ["tool_calls[2].arguments.amount"],
            [
                item["path"]
                for item in report["differences"]
                if item["category"] == "tool_argument_policy"
            ],
        )

    def test_argument_rules_validate_and_round_trip(self):
        policy = ContractPolicy.from_dict(
            {
                "argument_rules": [
                    {
                        "tool": "refund_order",
                        "path": "amount",
                        "operator": "less_or_equal",
                        "value": 88,
                    }
                ]
            }
        )
        self.assertEqual(policy.to_dict()["argument_rules"][0]["tool"], "refund_order")
        invalid_rules = [
            {"tool": "refund_order", "path": "amount", "operator": "regex", "value": 88},
            {"tool": "refund_order", "path": "amount", "operator": [], "value": 88},
            {"tool": "refund_order", "path": "amount", "operator": "equals"},
            {"tool": "refund_order", "path": "amount", "operator": "equals", "value": 1, "right_path": "a"},
            {"tool": "refund_order", "path": "amount", "operator": "absent", "value": 1},
            {"tool": "refund_order", "path": "amount", "operator": "equals_path", "right_path": ""},
        ]
        for rule in invalid_rules:
            with self.assertRaises(ValueError):
                ContractPolicy.from_dict({"argument_rules": [rule]})

    def test_tool_limits_enforce_call_counts_and_optional_arguments(self):
        policy = ComparisonPolicy(
            final_answer_mode="claims-only",
            contract=ContractPolicy.from_dict(
                {
                    "tool_limits": [
                        {"tool": "get_order", "min_calls": 1, "max_calls": 1},
                        {"tool": "get_payment_status", "min_calls": 1},
                    ]
                }
            ),
        )
        passed = compare_traces(
            make_path_trace(["get_order", "get_payment_status"]),
            make_path_trace(["get_order", "get_payment_status"]),
            policy,
        )
        self.assertTrue(passed["passed"], passed["differences"])

        repeated = compare_traces(
            make_path_trace(["get_order", "get_order"]),
            make_path_trace(["get_order", "get_order"]),
            ComparisonPolicy(
                final_answer_mode="claims-only",
                contract=ContractPolicy.from_dict(
                    {"tool_limits": [{"tool": "get_order", "max_calls": 1}]}
                ),
            ),
        )
        self.assertFalse(repeated["passed"])
        repeated_difference = next(
            item for item in repeated["differences"] if item["category"] == "tool_count"
        )
        self.assertEqual("tool_calls.count.get_order", repeated_difference["path"])
        self.assertEqual(2, repeated_difference["candidate"])

        missing = compare_traces(
            make_path_trace(["get_order"]),
            make_path_trace(["get_order"]),
            policy,
        )
        self.assertFalse(missing["passed"])
        self.assertTrue(
            any(
                item["category"] == "tool_count"
                and item["path"] == "tool_calls.count.get_payment_status"
                for item in missing["differences"]
            )
        )

        argument_scoped = compare_traces(
            make_path_trace(["get_order"]),
            make_path_trace(["get_order"]),
            ComparisonPolicy(
                final_answer_mode="claims-only",
                contract=ContractPolicy.from_dict(
                    {
                        "tool_limits": [
                            {
                                "tool": "get_order",
                                "arguments": {"order_id": "999"},
                                "min_calls": 1,
                            }
                        ]
                    }
                ),
            ),
        )
        self.assertFalse(argument_scoped["passed"])
        self.assertIn(
            "tool_count",
            {item["category"] for item in argument_scoped["differences"]},
        )

    def test_tool_limits_are_validated_and_serialized(self):
        policy = ContractPolicy.from_dict(
            {
                "tool_limits": [
                    {"tool": "get_order", "min_calls": 1, "max_calls": 2}
                ]
            }
        )
        self.assertEqual(
            [{"tool": "get_order", "min_calls": 1, "max_calls": 2}],
            policy.to_dict()["tool_limits"],
        )
        cases = [
            (
                {"tool_limits": [{"tool": "get_order", "limit": 1}]},
                "unsupported tool limit fields",
            ),
            ({"tool_limits": [{"tool": "get_order"}]}, "needs min_calls or max_calls"),
            (
                {"tool_limits": [{"tool": "get_order", "min_calls": -1}]},
                "min_calls must be a non-negative integer",
            ),
            (
                {"tool_limits": [{"tool": "get_order", "min_calls": 2, "max_calls": 1}]},
                "min_calls cannot exceed max_calls",
            ),
            (
                {"tool_limits": [{"tool": "get_order", "max_calls": True}]},
                "max_calls must be a non-negative integer",
            ),
        ]
        for value, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    ContractPolicy.from_dict(value)
        with self.assertRaisesRegex(ValueError, "tool_limits must be an array"):
            ContractPolicy.from_dict({"tool_limits": {"tool": "get_order"}})

    def test_tool_allowlist_is_optional_but_empty_means_deny_all(self):
        unrestricted = ContractPolicy.from_dict({})
        self.assertNotIn("tool_allowlist", unrestricted.to_dict())
        unrestricted_report = compare_traces(
            make_trace(),
            make_trace(),
            ComparisonPolicy(final_answer_mode="claims-only", contract=unrestricted),
        )
        self.assertTrue(unrestricted_report["passed"])

        allowed = ContractPolicy.from_dict(
            {
                "tool_allowlist": [
                    "get_order",
                    {"tool": "get_payment_status", "arguments": {"order_id": "123"}},
                ]
            }
        )
        allowed_report = compare_traces(
            make_trace(),
            make_trace(),
            ComparisonPolicy(final_answer_mode="claims-only", contract=allowed),
        )
        self.assertTrue(allowed_report["passed"], allowed_report["differences"])
        self.assertEqual(
            [
                {"tool": "get_order"},
                {"tool": "get_payment_status", "arguments": {"order_id": "123"}},
            ],
            allowed.to_dict()["tool_allowlist"],
        )

        denied_all = compare_traces(
            make_trace(),
            make_trace(),
            ComparisonPolicy(
                final_answer_mode="claims-only",
                contract=ContractPolicy.from_dict({"tool_allowlist": []}),
            ),
        )
        self.assertFalse(denied_all["passed"])
        self.assertEqual(
            {"unauthorized_tool_call"},
            {item["category"] for item in denied_all["differences"]},
        )

        argument_mismatch = compare_traces(
            make_trace(),
            make_trace(),
            ComparisonPolicy(
                final_answer_mode="claims-only",
                contract=ContractPolicy.from_dict(
                    {
                        "tool_allowlist": [
                            {"tool": "get_order", "arguments": {"order_id": "999"}}
                        ]
                    }
                ),
            ),
        )
        self.assertFalse(argument_mismatch["passed"])
        difference = argument_mismatch["differences"][0]
        self.assertEqual("unauthorized_tool_call", difference["category"])
        self.assertEqual("tool_calls[0]", difference["path"])
        self.assertEqual("get_order", difference["candidate"]["tool"])

    def test_tool_allowlist_validates_nested_rules_and_migration_shape(self):
        cases = [
            ({"tool_allowlist": {"tool": "get_order"}}, "tool_allowlist must be an array"),
            ({"tool_allowlist": [1]}, "tool_allowlist entries must be strings or objects"),
            ({"tool_allowlist": [{"tool": ""}]}, "non-empty tool"),
            (
                {"tool_allowlist": [{"tool": "get_order", "argument": {}}]},
                "unsupported tool allowlist rule fields",
            ),
            (
                {"tool_allowlist": [{"tool": "get_order", "arguments": []}]},
                "tool allowlist rule arguments must be an object",
            ),
        ]
        for value, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    ContractPolicy.from_dict(value)

    def test_contract_rejects_unknown_fields_instead_of_ignoring_typos(self):
        with self.assertRaisesRegex(ValueError, "unsupported contract fields"):
            ContractPolicy.from_dict({"must_not_cal": ["delete_order"]})

    def test_contract_rejects_unknown_nested_rule_fields(self):
        cases = [
            ({"must_call": [{"tool": "get_order", "argument": {}}]}, "tool rule"),
            ({"assertions": [{"path": "final_answer.text", "equals": "ok", "equal": "ok"}]}, "assertion"),
            ({"normalizers": [{"path": "final_answer.text", "type": "timestamp", "format": "iso"}]}, "normalizer"),
            ({"path_rules": {"any_of": [[{"tool": "get_order", "reslt": {}}]]}}, "path rule"),
            ({"side_effects": [{"path": "count", "from": 0, "too": 1}]}, "side effect"),
            ({"relations": [{"left": "a", "operator": "equals", "value": 1, "mesage": "typo"}]}, "relation"),
        ]
        for value, label in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, f"unsupported {label} fields"):
                    ContractPolicy.from_dict(value)

    def test_path_mode_is_backward_compatible_and_serialized(self):
        exact = ContractPolicy.from_dict(
            {"path_rules": {"any_of": [["get_order"]]}}
        )
        self.assertNotIn("mode", exact.to_dict()["path_rules"])
        tolerant = ContractPolicy.from_dict(
            {
                "path_rules": {
                    "mode": "ordered_subsequence",
                    "any_of": [["get_order", "get_payment_status"]],
                }
            }
        )
        self.assertEqual(
            "ordered_subsequence", tolerant.to_dict()["path_rules"]["mode"]
        )
        with self.assertRaisesRegex(ValueError, "path_rules.mode"):
            ContractPolicy.from_dict(
                {"path_rules": {"mode": "fuzzy", "any_of": [["get_order"]]}}
            )
        with self.assertRaisesRegex(ValueError, "path_rules.mode"):
            ContractPolicy.from_dict(
                {"path_rules": {"mode": [], "any_of": [["get_order"]]}}
            )
        with self.assertRaisesRegex(ValueError, "only valid"):
            ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "mode": "unordered_subset",
                        "ordered": False,
                        "any_of": [["get_order"]],
                    }
                }
            )

    def test_extra_calls_allowlist_is_explicit_and_fail_closed(self):
        baseline = make_path_trace(["get_order", "get_payment_status"])
        candidate = make_path_trace(
            ["get_order", "get_shipping", "get_payment_status"],
            run_id="path-extra-allowlist",
        )

        legacy_policy = ComparisonPolicy(
            final_answer_mode="claims-only",
            contract=ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "mode": "ordered_subsequence",
                        "any_of": [["get_order", "get_payment_status"]],
                    }
                }
            ),
        )
        self.assertTrue(
            compare_traces(baseline, candidate, legacy_policy)["passed"],
            "v4.6 tolerant paths must remain open when extra_calls is omitted",
        )

        allowlisted_policy = ComparisonPolicy(
            final_answer_mode="claims-only",
            contract=ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "mode": "ordered_subsequence",
                        "any_of": [["get_order", "get_payment_status"]],
                        "extra_calls": [
                            {
                                "tool": "get_shipping",
                                "result": {"tool": "get_shipping", "ok": True},
                                "is_error": False,
                            }
                        ],
                    }
                }
            ),
        )
        allowed = compare_traces(baseline, candidate, allowlisted_policy)
        self.assertTrue(allowed["passed"], allowed["differences"])

        closed_policy = ComparisonPolicy(
            final_answer_mode="claims-only",
            contract=ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "mode": "ordered_subsequence",
                        "any_of": [["get_order", "get_payment_status"]],
                        "extra_calls": [],
                    }
                }
            ),
        )
        blocked = compare_traces(baseline, candidate, closed_policy)
        self.assertFalse(blocked["passed"])
        extra = next(
            item
            for item in blocked["differences"]
            if item["category"] == "extra_tool_call"
        )
        self.assertEqual("tool_calls[1]", extra["path"])
        self.assertEqual("get_shipping", extra["candidate"]["tool"])

        unknown = compare_traces(
            baseline,
            make_path_trace(
                ["get_order", "delete_order", "get_payment_status"],
                run_id="path-extra-unknown",
            ),
            allowlisted_policy,
        )
        self.assertFalse(unknown["passed"])
        self.assertTrue(
            any(item["category"] == "extra_tool_call" for item in unknown["differences"])
        )

    def test_extra_calls_are_validated_and_serialized(self):
        policy = ContractPolicy.from_dict(
            {
                "path_rules": {
                    "mode": "unordered_subset",
                    "any_of": [["get_order"]],
                    "extra_calls": [],
                }
            }
        )
        self.assertEqual([], policy.to_dict()["path_rules"]["extra_calls"])

        with self.assertRaisesRegex(ValueError, "requires a tolerant"):
            ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "any_of": [["get_order"]],
                        "extra_calls": [],
                    }
                }
            )
        with self.assertRaisesRegex(ValueError, "unsupported extra call rule fields"):
            ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "mode": "ordered_subsequence",
                        "any_of": [["get_order"]],
                        "extra_calls": [{"tool": "get_shipping", "reslt": {}}],
                    }
                }
            )
        with self.assertRaisesRegex(ValueError, "extra_calls must be an array"):
            ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "mode": "ordered_subsequence",
                        "any_of": [["get_order"]],
                        "extra_calls": {"tool": "get_shipping"},
                    }
                }
            )
        with self.assertRaisesRegex(ValueError, "extra call rule is_error must be a boolean"):
            ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "mode": "ordered_subsequence",
                        "any_of": [["get_order"]],
                        "extra_calls": [{"tool": "get_shipping", "is_error": "false"}],
                    }
                }
            )

    def test_ordered_subsequence_allows_extra_observational_queries(self):
        baseline = make_path_trace(["get_order", "get_payment_status"])
        candidate = make_path_trace(
            ["get_order", "get_shipping", "get_payment_status"],
            run_id="path-mode-candidate",
        )
        policy = ComparisonPolicy(
            final_answer_mode="claims-only",
            contract=ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "mode": "ordered_subsequence",
                        "any_of": [["get_order", "get_payment_status"]],
                    },
                    "must_not_call": ["delete_order"],
                    "max_steps": 3,
                }
            ),
        )
        report = compare_traces(baseline, candidate, policy)
        self.assertTrue(report["passed"], report["differences"])

        reordered = make_path_trace(
            ["get_payment_status", "get_order"], run_id="path-mode-reordered"
        )
        report = compare_traces(baseline, reordered, policy)
        self.assertFalse(report["passed"])
        self.assertIn("behavior_path", {item["category"] for item in report["differences"]})

    def test_unordered_subset_allows_extra_calls_and_reordering(self):
        baseline = make_path_trace(["get_order", "get_payment_status"])
        candidate = make_path_trace(
            ["get_shipping", "get_payment_status", "get_order"],
            run_id="unordered-path-candidate",
        )
        policy = ComparisonPolicy(
            final_answer_mode="claims-only",
            contract=ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "mode": "unordered_subset",
                        "any_of": [["get_order", "get_payment_status"]],
                    },
                    "max_steps": 3,
                }
            ),
        )
        report = compare_traces(baseline, candidate, policy)
        self.assertTrue(report["passed"], report["differences"])

    def test_unordered_subset_handles_overlapping_rules_without_greedy_false_negative(self):
        candidate = make_path_trace(["get_order", "get_order"])
        policy = ComparisonPolicy(
            final_answer_mode="claims-only",
            contract=ContractPolicy.from_dict(
                {
                    "path_rules": {
                        "mode": "unordered_subset",
                        "any_of": [[
                            "get_order",
                            {"tool": "get_order", "arguments": {"order_id": "123"}},
                        ]],
                    }
                }
            ),
        )
        report = compare_traces(candidate, candidate, policy)
        self.assertTrue(report["passed"], report["differences"])

    def test_exact_path_mode_still_blocks_extra_calls(self):
        baseline = make_path_trace(["get_order"])
        candidate = make_path_trace(["get_order", "get_shipping"], run_id="exact-extra")
        policy = ComparisonPolicy(
            final_answer_mode="claims-only",
            contract=ContractPolicy.from_dict(
                {"path_rules": {"any_of": [["get_order"]]}}
            ),
        )
        report = compare_traces(baseline, candidate, policy)
        self.assertFalse(report["passed"])
        self.assertIn("behavior_path", {item["category"] for item in report["differences"]})


if __name__ == "__main__":
    unittest.main()
