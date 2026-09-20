"""Deterministic Agent behavior contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Mapping, Sequence

from .model import AgentTrace


_PATH_TOKEN = re.compile(r"([^.[\]]+)|\[([^\]]+)\]")
_MISSING = object()
_IGNORED = object()
_PATH_RULE_MODES = {"exact", "ordered_subsequence", "unordered_subset"}


def _reject_unknown_fields(
    value: Mapping[str, Any],
    allowed: set[str],
    label: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unsupported {label} fields: " + ", ".join(map(str, unknown)))


def _tokens(path: str) -> List[str]:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("contract paths must be non-empty strings")
    tokens: List[str] = []
    position = 0
    for match in _PATH_TOKEN.finditer(path):
        if match.start() != position and path[position:match.start()] != ".":
            raise ValueError(f"invalid contract path: {path!r}")
        token = match.group(1) or match.group(2)
        if token == "":
            raise ValueError(f"invalid contract path: {path!r}")
        tokens.append(token)
        position = match.end()
    if position != len(path):
        raise ValueError(f"invalid contract path: {path!r}")
    return tokens


def _matches(pattern: Sequence[str], actual: Sequence[str]) -> bool:
    return len(pattern) == len(actual) and all(
        expected in {"*", value} for expected, value in zip(pattern, actual)
    )


def _prune(value: Any, base: Sequence[str], patterns: Sequence[Sequence[str]]) -> Any:
    if any(_matches(pattern, base) for pattern in patterns):
        return _IGNORED
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, child in value.items():
            normalized = _prune(child, [*base, str(key)], patterns)
            if normalized is not _IGNORED:
                result[key] = normalized
        return result
    if isinstance(value, list):
        result_list = []
        for index, child in enumerate(value):
            normalized = _prune(child, [*base, str(index)], patterns)
            result_list.append(None if normalized is _IGNORED else normalized)
        return result_list
    return deepcopy(value)


def _normalize(
    value: Any,
    base: Sequence[str],
    normalizers: Sequence[Mapping[str, Any]],
) -> Any:
    for normalizer in normalizers:
        if _matches(_tokens(normalizer["path"]), base):
            if normalizer["type"] == "timestamp":
                return "<timestamp>"
            if normalizer["type"] == "sort" and isinstance(value, list):
                return sorted(value, key=lambda item: repr(item))
    if isinstance(value, dict):
        return {
            key: _normalize(child, [*base, str(key)], normalizers)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            _normalize(child, [*base, str(index)], normalizers)
            for index, child in enumerate(value)
        ]
    return value


def _lookup(value: Any, pattern: Sequence[str]) -> List[Any]:
    if not pattern:
        return [value]
    token, *rest = pattern
    if isinstance(value, dict):
        if token == "*":
            values: List[Any] = []
            for child in value.values():
                values.extend(_lookup(child, rest))
            return values
        if token not in value:
            return []
        return _lookup(value[token], rest)
    if isinstance(value, list):
        if token == "*":
            values = []
            for child in value:
                values.extend(_lookup(child, rest))
            return values
        try:
            index = int(token)
        except ValueError:
            return []
        if index < 0 or index >= len(value):
            return []
        return _lookup(value[index], rest)
    return []


def _rule_value(rule: Mapping[str, Any], key: str) -> Any:
    return rule[key] if key in rule else _MISSING


@dataclass(frozen=True)
class ContractPolicy:
    """Explicit, deterministic constraints for one AgentTrace comparison."""

    assertions: List[Dict[str, Any]] = field(default_factory=list)
    ignore_paths: List[str] = field(default_factory=list)
    normalizers: List[Dict[str, Any]] = field(default_factory=list)
    must_call: List[Dict[str, Any]] = field(default_factory=list)
    must_not_call: List[Dict[str, Any]] = field(default_factory=list)
    path_rules: Dict[str, Any] = field(default_factory=dict)
    side_effects: List[Dict[str, Any]] = field(default_factory=list)
    max_steps: int | None = None
    required_claims: List[str] = field(default_factory=list)
    relations: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.max_steps is not None and (
            not isinstance(self.max_steps, int) or self.max_steps < 0
        ):
            raise ValueError("contract.max_steps must be a non-negative integer")
        for path in self.required_claims:
            _tokens(path)
        for path in self.ignore_paths:
            _tokens(path)
        for normalizer in self.normalizers:
            if not isinstance(normalizer, dict):
                raise ValueError("contract.normalizers must contain objects")
            _reject_unknown_fields(normalizer, {"path", "type"}, "normalizer")
            _tokens(normalizer.get("path", ""))
            if normalizer.get("type") not in {"timestamp", "sort"}:
                raise ValueError("normalizer.type must be 'timestamp' or 'sort'")
        for assertion in self.assertions:
            if not isinstance(assertion, dict) or not isinstance(assertion.get("path"), str):
                raise ValueError("contract.assertions must contain path objects")
            _reject_unknown_fields(
                assertion,
                {"path", "equals", "contains", "exists"},
                "assertion",
            )
            _tokens(assertion["path"])
            operators = {"equals", "contains", "exists"} & set(assertion)
            if len(operators) != 1:
                raise ValueError("each assertion needs exactly one of equals, contains, or exists")
        for raw_rule in [*self.must_call, *self.must_not_call]:
            rule = {"tool": raw_rule} if isinstance(raw_rule, str) else raw_rule
            if not isinstance(rule, dict) or not isinstance(rule.get("tool"), str) or not rule["tool"]:
                raise ValueError("contract tool rules must contain a non-empty tool")
            _reject_unknown_fields(rule, {"tool", "arguments"}, "tool rule")
            if "arguments" in rule and not isinstance(rule["arguments"], dict):
                raise ValueError("contract tool rule arguments must be an object")
        if not isinstance(self.path_rules, dict):
            raise ValueError("contract.path_rules must be an object")
        _reject_unknown_fields(
            self.path_rules,
            {"any_of", "ordered", "mode"},
            "path_rules",
        )
        alternatives = self.path_rules.get("any_of", [])
        if not isinstance(alternatives, list) or not alternatives:
            if self.path_rules:
                raise ValueError("contract.path_rules.any_of must be a non-empty array")
        for path in alternatives:
            if not isinstance(path, list) or not path:
                raise ValueError("each contract path alternative must be a non-empty array")
            for raw_rule in path:
                rule = {"tool": raw_rule} if isinstance(raw_rule, str) else raw_rule
                if not isinstance(rule, dict) or not isinstance(rule.get("tool"), str) or not rule["tool"]:
                    raise ValueError("path rules must contain tool names")
                _reject_unknown_fields(
                    rule,
                    {"tool", "arguments", "result", "is_error"},
                    "path rule",
                )
                if "arguments" in rule and not isinstance(rule["arguments"], dict):
                    raise ValueError("path rule arguments must be an object")
                if "result" in rule and not isinstance(
                    rule["result"], (dict, list, str, int, float, bool, type(None))
                ):
                    raise ValueError("path rule result must be JSON-compatible")
                if "is_error" in rule and not isinstance(rule["is_error"], bool):
                    raise ValueError("path rule is_error must be a boolean")
        if "ordered" in self.path_rules and not isinstance(self.path_rules["ordered"], bool):
            raise ValueError("contract.path_rules.ordered must be a boolean")
        mode = self.path_rules.get("mode", "exact")
        if not isinstance(mode, str) or mode not in _PATH_RULE_MODES:
            raise ValueError(
                "contract.path_rules.mode must be one of: "
                + ", ".join(sorted(_PATH_RULE_MODES))
            )
        if mode != "exact" and "ordered" in self.path_rules:
            raise ValueError(
                "contract.path_rules.ordered is only valid when mode is 'exact'"
            )
        for effect in self.side_effects:
            if not isinstance(effect, dict) or not isinstance(effect.get("path"), str):
                raise ValueError("contract.side_effects must contain path objects")
            _reject_unknown_fields(effect, {"path", "from", "to"}, "side effect")
            _tokens(effect["path"])
            if "from" not in effect and "to" not in effect:
                raise ValueError("a side effect needs at least one of from or to")
        for relation in self.relations:
            if not isinstance(relation, dict):
                raise ValueError("contract.relations must contain objects")
            _reject_unknown_fields(
                relation,
                {"left", "operator", "right_path", "value", "message"},
                "relation",
            )
            if not isinstance(relation.get("left"), str) or not relation["left"].strip():
                raise ValueError("contract relation left must be a non-empty path")
            _tokens(relation["left"])
            operator = relation.get("operator")
            if operator not in {
                "equals_path",
                "not_equals_path",
                "less_than_path",
                "less_or_equal_path",
                "greater_than_path",
                "greater_or_equal_path",
                "equals",
                "not_equals",
                "less_than",
                "less_or_equal",
                "greater_than",
                "greater_or_equal",
                "in",
            }:
                raise ValueError("unsupported contract relation operator")
            needs_path = operator.endswith("_path")
            if needs_path:
                if not isinstance(relation.get("right_path"), str) or not relation["right_path"].strip():
                    raise ValueError(f"relation operator {operator} requires right_path")
                _tokens(relation["right_path"])
                if "value" in relation:
                    raise ValueError(f"relation operator {operator} cannot use value")
            else:
                if "value" not in relation:
                    raise ValueError(f"relation operator {operator} requires value")
                if "right_path" in relation:
                    raise ValueError(f"relation operator {operator} cannot use right_path")
            if "message" in relation and (
                not isinstance(relation["message"], str) or not relation["message"].strip()
            ):
                raise ValueError("relation.message must be a non-empty string")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ContractPolicy":
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise ValueError("contract must be an object")
        allowed_fields = {
            "assertions",
            "ignore_paths",
            "normalizers",
            "must_call",
            "must_not_call",
            "path_rules",
            "side_effects",
            "relations",
            "max_steps",
            "required_claims",
        }
        unknown_fields = sorted(set(value) - allowed_fields)
        if unknown_fields:
            raise ValueError(
                "unsupported contract fields: " + ", ".join(map(str, unknown_fields))
            )

        def rules(key: str) -> List[Dict[str, Any]]:
            configured = value.get(key, [])
            if not isinstance(configured, list) or not all(isinstance(item, dict) for item in configured):
                raise ValueError(f"contract.{key} must be an array of objects")
            return [dict(item) for item in configured]

        forbidden = value.get("must_not_call", [])
        if not isinstance(forbidden, list):
            raise ValueError("contract.must_not_call must be an array")
        if not all(isinstance(item, (str, dict)) for item in forbidden):
            raise ValueError("contract.must_not_call entries must be strings or objects")
        forbidden_rules = [
            {"tool": item} if isinstance(item, str) else dict(item)
            for item in forbidden
        ]
        ignore_paths = value.get("ignore_paths", [])
        if not isinstance(ignore_paths, list) or not all(isinstance(item, str) for item in ignore_paths):
            raise ValueError("contract.ignore_paths must be an array of strings")
        normalizers = value.get("normalizers", [])
        if not isinstance(normalizers, list) or not all(isinstance(item, dict) for item in normalizers):
            raise ValueError("contract.normalizers must be an array of objects")
        path_rules = value.get("path_rules", {})
        if not isinstance(path_rules, dict):
            raise ValueError("contract.path_rules must be an object")
        side_effects = value.get("side_effects", [])
        if not isinstance(side_effects, list) or not all(isinstance(item, dict) for item in side_effects):
            raise ValueError("contract.side_effects must be an array of objects")
        relations = value.get("relations", [])
        if not isinstance(relations, list) or not all(isinstance(item, dict) for item in relations):
            raise ValueError("contract.relations must be an array of objects")
        required_claims = value.get("required_claims", [])
        if not isinstance(required_claims, list) or not all(
            isinstance(item, str) and item.strip() for item in required_claims
        ):
            raise ValueError("contract.required_claims must be an array of non-empty strings")
        return cls(
            assertions=rules("assertions"),
            ignore_paths=list(ignore_paths),
            normalizers=[dict(item) for item in normalizers],
            must_call=rules("must_call"),
            must_not_call=forbidden_rules,
            path_rules=deepcopy(path_rules),
            side_effects=[dict(item) for item in side_effects],
            relations=[dict(item) for item in relations],
            max_steps=value.get("max_steps"),
            required_claims=list(required_claims),
        )

    def to_dict(self) -> Dict[str, Any]:
        def tool_rules(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            return [
                {"tool": rule} if isinstance(rule, str) else deepcopy(rule)
                for rule in rules
            ]

        return {
            "assertions": deepcopy(self.assertions),
            "ignore_paths": list(self.ignore_paths),
            "normalizers": deepcopy(self.normalizers),
            "must_call": tool_rules(self.must_call),
            "must_not_call": tool_rules(self.must_not_call),
            "path_rules": deepcopy(self.path_rules),
            "side_effects": deepcopy(self.side_effects),
            "relations": deepcopy(self.relations),
            "max_steps": self.max_steps,
            "required_claims": list(self.required_claims),
        }

    @property
    def has_path_rules(self) -> bool:
        return bool(self.path_rules.get("any_of"))

    def _patterns(self) -> List[List[str]]:
        return [_tokens(path) for path in self.ignore_paths]

    def sanitize(self, value: Any, path: str) -> Any:
        """Remove ignored fields and apply the small deterministic normalizer set."""
        patterns = self._patterns()
        normalized = _prune(value, _tokens(path), patterns)
        if normalized is _IGNORED:
            return _IGNORED
        return _normalize(normalized, _tokens(path), self.normalizers)

    def check(self, baseline: AgentTrace, candidate: AgentTrace) -> List[Dict[str, Any]]:
        """Return blocking contract differences for a candidate trace."""
        differences: List[Dict[str, Any]] = []
        candidate_data = candidate.to_dict()
        candidate_data.update(
            {
                "tool_calls": [
                    event for event in candidate.events if event["type"] == "tool_call"
                ],
                "tool_results": [
                    event for event in candidate.events if event["type"] == "tool_result"
                ],
                "final_answer": next(
                    event for event in candidate.events if event["type"] == "final_answer"
                ),
                "world_state": candidate.metadata.get("world_state", {}),
            }
        )
        for assertion in self.assertions:
            path = assertion["path"]
            values = _lookup(candidate_data, _tokens(path))
            expected = _rule_value(assertion, "equals")
            contains = _rule_value(assertion, "contains")
            exists = _rule_value(assertion, "exists")
            passed = bool(values)
            if expected is not _MISSING:
                passed = len(values) > 0 and all(value == expected for value in values)
            elif contains is not _MISSING:
                def contains_value(value: Any) -> bool:
                    if isinstance(value, (str, list, dict)):
                        return contains in value
                    return False

                passed = len(values) > 0 and all(contains_value(value) for value in values)
            elif exists is not _MISSING:
                passed = bool(values) == bool(exists)
            if not passed:
                differences.append(
                    {
                        "category": "contract_assertion",
                        "path": path,
                        "baseline": expected if expected is not _MISSING else None,
                        "candidate": values if values else None,
                        "message": "contract assertion failed",
                    }
                )

        for path in self.required_claims:
            values = _lookup(candidate_data, _tokens(path))
            if not values:
                differences.append(
                    {
                        "category": "required_claim",
                        "path": path,
                        "baseline": "present",
                        "candidate": None,
                        "message": "required claim was not observed",
                    }
                )

        for relation in self.relations:
            left_values = _lookup(candidate_data, _tokens(relation["left"]))
            if relation["operator"].endswith("_path"):
                right_values = _lookup(candidate_data, _tokens(relation["right_path"]))
            else:
                right_values = [relation["value"]]
            passed = self._relation_matches(
                relation["operator"], left_values, right_values
            )
            if not passed:
                right_label = (
                    relation.get("right_path")
                    if relation["operator"].endswith("_path")
                    else relation.get("value")
                )
                differences.append(
                    {
                        "category": "contract_relation",
                        "path": relation["left"],
                        "baseline": {
                            "operator": relation["operator"],
                            "right": right_label,
                        },
                        "candidate": {
                            "left_values": left_values or None,
                            "right_values": right_values or None,
                        },
                        "message": relation.get(
                            "message", "contract relation failed"
                        ),
                    }
                )

        candidate_calls = [event for event in candidate.events if event["type"] == "tool_call"]
        candidate_results = {
            event["call_id"]: event
            for event in candidate.events
            if event["type"] == "tool_result"
        }
        for raw_rule in self.must_call:
            rule = {"tool": raw_rule} if isinstance(raw_rule, str) else raw_rule
            if not any(self._tool_rule_matches(rule, event) for event in candidate_calls):
                differences.append(
                    {
                        "category": "required_tool",
                        "path": "tool_calls",
                        "baseline": rule,
                        "candidate": [event.get("tool") for event in candidate_calls],
                        "message": "required tool call was not observed",
                    }
                )
        for raw_rule in self.must_not_call:
            rule = {"tool": raw_rule} if isinstance(raw_rule, str) else raw_rule
            matches = [event for event in candidate_calls if self._tool_rule_matches(rule, event)]
            if matches:
                differences.append(
                    {
                        "category": "forbidden_tool",
                        "path": "tool_calls",
                        "baseline": None,
                        "candidate": rule,
                        "message": "forbidden tool call was observed",
                    }
                )
        if self.has_path_rules and not self._path_matches(candidate_calls, candidate_results):
            differences.append(
                {
                    "category": "behavior_path",
                    "path": "tool_calls.path",
                    "baseline": deepcopy(self.path_rules),
                    "candidate": [
                        {"tool": event.get("tool"), "arguments": event.get("arguments", {})}
                        for event in candidate_calls
                    ],
                    "message": "observed tool path is not one of the allowed paths",
                }
            )
        for effect in self.side_effects:
            initial_values = _lookup(
                candidate_data.get("world_state", {}).get("initial", {}),
                _tokens(effect["path"]),
            )
            final_values = _lookup(
                candidate_data.get("world_state", {}).get("final", {}),
                _tokens(effect["path"]),
            )
            if "from" in effect and (
                not initial_values or any(value != effect["from"] for value in initial_values)
            ):
                differences.append(
                    {
                        "category": "side_effect",
                        "path": f"world_state.initial.{effect['path']}",
                        "baseline": effect["from"],
                        "candidate": initial_values or None,
                        "message": "side-effect initial state did not match",
                    }
                )
            if "to" in effect and (
                not final_values or any(value != effect["to"] for value in final_values)
            ):
                differences.append(
                    {
                        "category": "side_effect",
                        "path": f"world_state.final.{effect['path']}",
                        "baseline": effect["to"],
                        "candidate": final_values or None,
                        "message": "side-effect final state did not match",
                    }
                )
        if self.max_steps is not None and len(candidate_calls) > self.max_steps:
            differences.append(
                {
                    "category": "step_limit",
                    "path": "events.tool_call.count",
                    "baseline": self.max_steps,
                    "candidate": len(candidate_calls),
                    "message": "maximum tool-call step count exceeded",
                }
            )
        return differences

    def _path_matches(
        self,
        candidate_calls: Sequence[Mapping[str, Any]],
        candidate_results: Mapping[str, Mapping[str, Any]],
    ) -> bool:
        observed = []
        for event in candidate_calls:
            observed_event = {
                "tool": event.get("tool"),
                "arguments": event.get("arguments", {}),
            }
            result = candidate_results.get(event.get("call_id"))
            if result is not None:
                observed_event["result"] = result.get("result")
                observed_event["is_error"] = result.get("is_error", False)
            observed.append(observed_event)
        mode = self.path_rules.get("mode", "exact")
        ordered = self.path_rules.get("ordered", True)
        for alternative in self.path_rules.get("any_of", []):
            expected = [
                {"tool": rule}
                if isinstance(rule, str)
                else rule
                for rule in alternative
            ]
            if mode == "ordered_subsequence":
                observed_index = 0
                for rule in expected:
                    match_index = next(
                        (
                            index
                            for index, event in enumerate(observed[observed_index:], observed_index)
                            if self._path_rule_matches(rule, event)
                        ),
                        None,
                    )
                    if match_index is None:
                        break
                    observed_index = match_index + 1
                else:
                    return True
            elif mode == "unordered_subset":
                if self._unordered_path_rules_match(expected, observed):
                    return True
            elif ordered:
                if len(expected) == len(observed) and all(
                    self._path_rule_matches(rule, event)
                    for rule, event in zip(expected, observed)
                ):
                    return True
            else:
                if len(expected) == len(observed):
                    if self._unordered_path_rules_match(expected, observed):
                        return True
        return False

    def _unordered_path_rules_match(
        self,
        expected: Sequence[Mapping[str, Any]],
        observed: Sequence[Mapping[str, Any]],
    ) -> bool:
        """Match each rule to a distinct event without greedy false negatives."""
        if len(expected) > len(observed):
            return False
        candidates = [
            [
                index
                for index, event in enumerate(observed)
                if self._path_rule_matches(rule, event)
            ]
            for rule in expected
        ]
        if any(not matches for matches in candidates):
            return False
        order = sorted(range(len(expected)), key=lambda index: len(candidates[index]))

        matched_events: Dict[int, int] = {}

        def assign(rule_index: int, visited: set[int]) -> bool:
            for event_index in candidates[rule_index]:
                if event_index in visited:
                    continue
                visited.add(event_index)
                previous_rule = matched_events.get(event_index)
                if previous_rule is None or assign(previous_rule, visited):
                    matched_events[event_index] = rule_index
                    return True
            return False

        return all(assign(rule_index, set()) for rule_index in order)

    @staticmethod
    def _tool_rule_matches(rule: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
        return event.get("tool") == rule.get("tool") and (
            "arguments" not in rule or event.get("arguments") == rule["arguments"]
        )

    @staticmethod
    def _relation_matches(
        operator: str, left_values: Sequence[Any], right_values: Sequence[Any]
    ) -> bool:
        """Evaluate a relation over JSON paths without executing user code.

        A relation succeeds when every resolved left value has a matching right
        value. Empty paths fail, which turns missing evidence into a visible
        contract failure instead of silently passing it.
        """
        if not left_values or not right_values:
            return False

        def compare(left: Any, right: Any, op: str) -> bool:
            try:
                if op in {"equals_path", "equals"}:
                    return left == right
                if op in {"not_equals_path", "not_equals"}:
                    return left != right
                if op in {"less_than_path", "less_than"}:
                    return left < right
                if op in {"less_or_equal_path", "less_or_equal"}:
                    return left <= right
                if op in {"greater_than_path", "greater_than"}:
                    return left > right
                if op in {"greater_or_equal_path", "greater_or_equal"}:
                    return left >= right
                if op == "in":
                    return left in right if isinstance(right, (list, str, dict)) else False
            except (TypeError, ValueError):
                return False
            return False

        return all(
            any(compare(left, right, operator) for right in right_values)
            for left in left_values
        )

    @staticmethod
    def _path_rule_matches(rule: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
        if not ContractPolicy._tool_rule_matches(rule, event):
            return False
        if "result" in rule and event.get("result") != rule["result"]:
            return False
        return "is_error" not in rule or event.get("is_error", False) == rule["is_error"]
