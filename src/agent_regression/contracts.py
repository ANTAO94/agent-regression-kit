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
_ARGUMENT_POLICY_OPERATORS = {
    "equals",
    "not_equals",
    "less_than",
    "less_or_equal",
    "greater_than",
    "greater_or_equal",
    "in",
    "exists",
    "absent",
    "equals_path",
    "not_equals_path",
    "less_than_path",
    "less_or_equal_path",
    "greater_than_path",
    "greater_or_equal_path",
}
_STATE_EQUIVALENCE_MODES = {"exact", "outcome", "hybrid"}


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
    tool_limits: List[Dict[str, Any]] = field(default_factory=list)
    # None means that the scenario does not constrain the tool catalog. An
    # explicit empty list is intentionally different: it denies every tool.
    tool_allowlist: List[Dict[str, Any]] | None = None
    # Rules are evaluated against every candidate call for the named tool. The
    # argument path is relative to that call's arguments object.
    argument_rules: List[Dict[str, Any]] = field(default_factory=list)
    # Outcome-mode comparison can declare equivalent intents without changing
    # the positional ordering of the original public constructor fields.
    state_equivalence: Dict[str, Any] | None = None

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
        for limit in self.tool_limits:
            if not isinstance(limit, dict) or not isinstance(limit.get("tool"), str) or not limit["tool"]:
                raise ValueError("contract tool limits must contain a non-empty tool")
            _reject_unknown_fields(
                limit,
                {"tool", "arguments", "min_calls", "max_calls"},
                "tool limit",
            )
            if "arguments" in limit and not isinstance(limit["arguments"], dict):
                raise ValueError("tool limit arguments must be an object")
            if "min_calls" not in limit and "max_calls" not in limit:
                raise ValueError("a tool limit needs min_calls or max_calls")
            for bound in ("min_calls", "max_calls"):
                if bound in limit and (
                    not isinstance(limit[bound], int) or isinstance(limit[bound], bool) or limit[bound] < 0
                ):
                    raise ValueError(f"tool limit {bound} must be a non-negative integer")
            if (
                "min_calls" in limit
                and "max_calls" in limit
                and limit["min_calls"] > limit["max_calls"]
            ):
                raise ValueError("tool limit min_calls cannot exceed max_calls")
        if self.tool_allowlist is not None:
            if not isinstance(self.tool_allowlist, list):
                raise ValueError("contract.tool_allowlist must be an array")
            for raw_rule in self.tool_allowlist:
                rule = {"tool": raw_rule} if isinstance(raw_rule, str) else raw_rule
                if (
                    not isinstance(rule, dict)
                    or not isinstance(rule.get("tool"), str)
                    or not rule["tool"].strip()
                ):
                    raise ValueError(
                        "contract tool allowlist must contain a non-empty tool"
                    )
                _reject_unknown_fields(
                    rule,
                    {"tool", "arguments"},
                    "tool allowlist rule",
                )
                if "arguments" in rule and not isinstance(rule["arguments"], dict):
                    raise ValueError(
                        "tool allowlist rule arguments must be an object"
                    )
        for rule in self.argument_rules:
            if (
                not isinstance(rule, dict)
                or not isinstance(rule.get("tool"), str)
                or not rule["tool"].strip()
            ):
                raise ValueError(
                    "contract argument rules must contain a non-empty tool"
                )
            _reject_unknown_fields(
                rule,
                {"tool", "path", "operator", "value", "right_path", "message"},
                "argument rule",
            )
            if not isinstance(rule.get("path"), str) or not rule["path"].strip():
                raise ValueError("argument rule path must be a non-empty string")
            _tokens(rule["path"])
            operator = rule.get("operator")
            if not isinstance(operator, str) or operator not in _ARGUMENT_POLICY_OPERATORS:
                raise ValueError("unsupported contract argument rule operator")
            if "message" in rule and (
                not isinstance(rule["message"], str) or not rule["message"].strip()
            ):
                raise ValueError("argument rule message must be a non-empty string")
            if operator in {"exists", "absent"}:
                if "value" in rule or "right_path" in rule:
                    raise ValueError(
                        f"argument rule operator {operator} cannot use value or right_path"
                    )
            elif operator.endswith("_path"):
                if (
                    not isinstance(rule.get("right_path"), str)
                    or not rule["right_path"].strip()
                ):
                    raise ValueError(
                        f"argument rule operator {operator} requires right_path"
                    )
                _tokens(rule["right_path"])
                if "value" in rule:
                    raise ValueError(
                        f"argument rule operator {operator} cannot use value"
                    )
            else:
                if "value" not in rule:
                    raise ValueError(
                        f"argument rule operator {operator} requires value"
                    )
                if "right_path" in rule:
                    raise ValueError(
                        f"argument rule operator {operator} cannot use right_path"
                    )
        if not isinstance(self.path_rules, dict):
            raise ValueError("contract.path_rules must be an object")
        _reject_unknown_fields(
            self.path_rules,
            {"any_of", "ordered", "mode", "extra_calls"},
            "path_rules",
        )
        alternatives = self.path_rules.get("any_of", [])
        if not isinstance(alternatives, list) or not alternatives:
            if self.path_rules:
                raise ValueError("contract.path_rules.any_of must be a non-empty array")

        def validate_path_rule(raw_rule: Any, label: str = "path rule") -> None:
            rule = {"tool": raw_rule} if isinstance(raw_rule, str) else raw_rule
            if not isinstance(rule, dict) or not isinstance(rule.get("tool"), str) or not rule["tool"]:
                raise ValueError(f"{label}s must contain tool names")
            _reject_unknown_fields(
                rule,
                {"tool", "arguments", "result", "is_error"},
                label,
            )
            if "arguments" in rule and not isinstance(rule["arguments"], dict):
                raise ValueError(f"{label} arguments must be an object")
            if "result" in rule and not isinstance(
                rule["result"], (dict, list, str, int, float, bool, type(None))
            ):
                raise ValueError(f"{label} result must be JSON-compatible")
            if "is_error" in rule and not isinstance(rule["is_error"], bool):
                raise ValueError(f"{label} is_error must be a boolean")

        for path in alternatives:
            if not isinstance(path, list) or not path:
                raise ValueError("each contract path alternative must be a non-empty array")
            for raw_rule in path:
                validate_path_rule(raw_rule)
        extra_calls = self.path_rules.get("extra_calls", [])
        if "extra_calls" in self.path_rules:
            if not isinstance(extra_calls, list):
                raise ValueError("contract.path_rules.extra_calls must be an array")
            for raw_rule in extra_calls:
                validate_path_rule(raw_rule, "extra call rule")
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
        if mode == "exact" and "extra_calls" in self.path_rules:
            raise ValueError(
                "contract.path_rules.extra_calls requires a tolerant path mode"
            )
        if self.state_equivalence is not None:
            if not isinstance(self.state_equivalence, dict):
                raise ValueError("contract.state_equivalence must be an object")
            _reject_unknown_fields(
                self.state_equivalence,
                {
                    "mode",
                    "paths",
                    "ignore_argument_paths",
                    "tool_aliases",
                    "allow_failed_expected",
                    "idempotent_tools",
                },
                "state equivalence",
            )
            equivalence_mode = self.state_equivalence.get("mode", "exact")
            if equivalence_mode not in _STATE_EQUIVALENCE_MODES:
                raise ValueError(
                    "contract.state_equivalence.mode must be one of: "
                    + ", ".join(sorted(_STATE_EQUIVALENCE_MODES))
                )
            for key in ("paths", "ignore_argument_paths", "idempotent_tools"):
                values = self.state_equivalence.get(key, [])
                if not isinstance(values, list) or not all(
                    isinstance(item, str) and item.strip() for item in values
                ):
                    raise ValueError(
                        f"contract.state_equivalence.{key} must be an array of non-empty strings"
                    )
                if key != "idempotent_tools":
                    for path in values:
                        _tokens(path)
            aliases = self.state_equivalence.get("tool_aliases", [])
            if not isinstance(aliases, list) or not all(
                isinstance(group, list)
                and len(group) >= 2
                and all(isinstance(tool, str) and tool.strip() for tool in group)
                for group in aliases
            ):
                raise ValueError(
                    "contract.state_equivalence.tool_aliases must contain tool groups"
                )
            if any(len(set(group)) != len(group) for group in aliases):
                raise ValueError(
                    "contract.state_equivalence.tool_aliases cannot repeat a tool"
                )
            alias_tools = [tool for group in aliases for tool in group]
            if len(set(alias_tools)) != len(alias_tools):
                raise ValueError(
                    "contract.state_equivalence.tool_aliases cannot overlap groups"
                )
            if not isinstance(
                self.state_equivalence.get("allow_failed_expected", False), bool
            ):
                raise ValueError(
                    "contract.state_equivalence.allow_failed_expected must be a boolean"
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
            "state_equivalence",
            "side_effects",
            "relations",
            "max_steps",
            "required_claims",
            "tool_limits",
            "tool_allowlist",
            "argument_rules",
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
        state_equivalence = value.get("state_equivalence")
        if state_equivalence is not None and not isinstance(state_equivalence, dict):
            raise ValueError("contract.state_equivalence must be an object")
        side_effects = value.get("side_effects", [])
        if not isinstance(side_effects, list) or not all(isinstance(item, dict) for item in side_effects):
            raise ValueError("contract.side_effects must be an array of objects")
        relations = value.get("relations", [])
        if not isinstance(relations, list) or not all(isinstance(item, dict) for item in relations):
            raise ValueError("contract.relations must be an array of objects")
        tool_limits = value.get("tool_limits", [])
        if not isinstance(tool_limits, list) or not all(
            isinstance(item, dict) for item in tool_limits
        ):
            raise ValueError("contract.tool_limits must be an array of objects")
        raw_allowlist = value.get("tool_allowlist")
        if raw_allowlist is not None:
            if not isinstance(raw_allowlist, list):
                raise ValueError("contract.tool_allowlist must be an array")
            if not all(isinstance(item, (str, dict)) for item in raw_allowlist):
                raise ValueError(
                    "contract.tool_allowlist entries must be strings or objects"
                )
            tool_allowlist = [
                {"tool": item} if isinstance(item, str) else dict(item)
                for item in raw_allowlist
            ]
        else:
            tool_allowlist = None
        argument_rules = value.get("argument_rules", [])
        if not isinstance(argument_rules, list) or not all(
            isinstance(item, dict) for item in argument_rules
        ):
            raise ValueError("contract.argument_rules must be an array of objects")
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
            state_equivalence=deepcopy(state_equivalence),
            side_effects=[dict(item) for item in side_effects],
            relations=[dict(item) for item in relations],
            max_steps=value.get("max_steps"),
            required_claims=list(required_claims),
            tool_limits=[dict(item) for item in tool_limits],
            tool_allowlist=tool_allowlist,
            argument_rules=[dict(item) for item in argument_rules],
        )

    def to_dict(self) -> Dict[str, Any]:
        def tool_rules(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            return [
                {"tool": rule} if isinstance(rule, str) else deepcopy(rule)
                for rule in rules
            ]

        result = {
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
            "tool_limits": deepcopy(self.tool_limits),
            "argument_rules": deepcopy(self.argument_rules),
        }
        if self.state_equivalence is not None:
            result["state_equivalence"] = deepcopy(self.state_equivalence)
        if self.tool_allowlist is not None:
            result["tool_allowlist"] = tool_rules(self.tool_allowlist)
        return result

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

    def _state_equivalence_mode(self) -> str:
        if not self.state_equivalence:
            return "exact"
        return str(self.state_equivalence.get("mode", "exact"))

    def _trace_data(self, trace: AgentTrace) -> Dict[str, Any]:
        data = trace.to_dict()
        data.update(
            {
                "tool_calls": [
                    event for event in trace.events if event["type"] == "tool_call"
                ],
                "tool_results": [
                    event for event in trace.events if event["type"] == "tool_result"
                ],
                "final_answer": next(
                    event for event in trace.events if event["type"] == "final_answer"
                ),
                "world_state": trace.metadata.get("world_state", {}),
            }
        )
        return data

    def check(self, baseline: AgentTrace, candidate: AgentTrace) -> List[Dict[str, Any]]:
        """Return blocking contract differences for a candidate trace."""
        differences: List[Dict[str, Any]] = []
        baseline_data = self._trace_data(baseline)
        candidate_data = self._trace_data(candidate)

        for path in (self.state_equivalence or {}).get("paths", []):
            baseline_values = _lookup(baseline_data, _tokens(path))
            candidate_values = _lookup(candidate_data, _tokens(path))
            if not baseline_values or not candidate_values or baseline_values != candidate_values:
                differences.append(
                    {
                        "category": "state_equivalence",
                        "path": path,
                        "baseline": baseline_values or None,
                        "candidate": candidate_values or None,
                        "message": "declared outcome state is not equivalent",
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
        for limit in self.tool_limits:
            matches = [
                event
                for event in candidate_calls
                if self._tool_rule_matches(limit, event)
            ]
            count = len(matches)
            minimum = limit.get("min_calls")
            maximum = limit.get("max_calls")
            below_minimum = minimum is not None and count < minimum
            above_maximum = maximum is not None and count > maximum
            if below_minimum or above_maximum:
                if minimum is not None and maximum is not None:
                    expected = f"between {minimum} and {maximum}"
                elif minimum is not None:
                    expected = f"at least {minimum}"
                else:
                    expected = f"at most {maximum}"
                differences.append(
                    {
                        "category": "tool_count",
                        "path": f"tool_calls.count.{limit['tool']}",
                        "baseline": deepcopy(limit),
                        "candidate": count,
                        "message": (
                            f"tool call count for {limit['tool']!r} must be {expected}; "
                            f"observed {count}"
                        ),
                    }
                )
        if self.tool_allowlist is not None:
            allowlist_rules = [
                {"tool": rule} if isinstance(rule, str) else rule
                for rule in self.tool_allowlist
            ]
            for index, event in enumerate(candidate_calls):
                if not any(
                    self._tool_rule_matches(rule, event) for rule in allowlist_rules
                ):
                    differences.append(
                        {
                            "category": "unauthorized_tool_call",
                            "path": f"tool_calls[{index}]",
                            "baseline": deepcopy(self.tool_allowlist),
                            "candidate": deepcopy(event),
                            "message": (
                                "tool call is not permitted by "
                                "contract.tool_allowlist"
                            ),
                        }
                    )
        for rule in self.argument_rules:
            matching_calls = [
                (index, event)
                for index, event in enumerate(candidate_calls)
                if event.get("tool") == rule["tool"]
            ]
            for index, event in matching_calls:
                arguments = event.get("arguments", {})
                left_values = _lookup(arguments, _tokens(rule["path"]))
                operator = rule["operator"]
                if operator == "exists":
                    passed = bool(left_values)
                    right_values: List[Any] = []
                elif operator == "absent":
                    passed = not left_values
                    right_values = []
                elif operator.endswith("_path"):
                    right_values = _lookup(
                        candidate_data, _tokens(rule["right_path"])
                    )
                    passed = self._relation_matches(
                        operator, left_values, right_values
                    )
                else:
                    right_values = [rule["value"]]
                    passed = self._relation_matches(
                        operator, left_values, right_values
                    )
                if not passed:
                    differences.append(
                        {
                            "category": "tool_argument_policy",
                            "path": f"tool_calls[{index}].arguments.{rule['path']}",
                            "baseline": deepcopy(rule),
                            "candidate": {
                                "value": left_values or None,
                                "right_values": right_values or None,
                            },
                            "message": rule.get(
                                "message", "tool argument policy failed"
                            ),
                        }
                    )
        path_details = self._path_match_details(candidate_calls, candidate_results)
        if self.has_path_rules and not path_details["passed"]:
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
            for index, event in path_details["disallowed_extra_calls"]:
                differences.append(
                    {
                        "category": "extra_tool_call",
                        "path": f"tool_calls[{index}]",
                        "baseline": deepcopy(self.path_rules.get("extra_calls", [])),
                        "candidate": deepcopy(event),
                        "message": "extra tool call is not allowed by path_rules.extra_calls",
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
        return bool(self._path_match_details(candidate_calls, candidate_results)["passed"])

    def _path_match_details(
        self,
        candidate_calls: Sequence[Mapping[str, Any]],
        candidate_results: Mapping[str, Mapping[str, Any]],
    ) -> Dict[str, Any]:
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
        has_extra_allowlist = "extra_calls" in self.path_rules
        extra_rules = [
            {"tool": rule} if isinstance(rule, str) else rule
            for rule in self.path_rules.get("extra_calls", [])
        ]
        first_disallowed_extra_calls: List[tuple[int, Dict[str, Any]]] = []
        for alternative in self.path_rules.get("any_of", []):
            expected = [
                {"tool": rule}
                if isinstance(rule, str)
                else rule
                for rule in alternative
            ]
            state_mode = self._state_equivalence_mode()
            if state_mode in {"outcome", "hybrid"}:
                matched_indexes = self._state_equivalent_path_indexes(
                    expected,
                    observed,
                    ordered=state_mode == "hybrid" and ordered,
                    grouped=state_mode == "outcome",
                )
            else:
                matched_indexes = self._path_match_indexes(
                    expected, observed, mode=mode, ordered=ordered
                )
            if matched_indexes is None:
                continue
            state_mode = self._state_equivalence_mode()
            enforce_state_extras = (
                state_mode in {"outcome", "hybrid"} and mode == "exact"
            )
            if not has_extra_allowlist and not enforce_state_extras:
                return {"passed": True, "disallowed_extra_calls": []}
            disallowed = [
                (index, event)
                for index, event in enumerate(observed)
                if index not in matched_indexes
                and not any(self._path_rule_matches(rule, event) for rule in extra_rules)
                and not self._is_allowed_idempotent_extra(expected, event)
                and not self._is_allowed_failed_expected_extra(expected, event)
            ]
            if not disallowed:
                return {"passed": True, "disallowed_extra_calls": []}
            if not first_disallowed_extra_calls:
                first_disallowed_extra_calls = disallowed
        return {
            "passed": False,
            "disallowed_extra_calls": first_disallowed_extra_calls,
        }

    def _state_equivalence_config(self) -> Mapping[str, Any]:
        return self.state_equivalence or {}

    def _equivalent_tools(self, left: str, right: str) -> bool:
        if left == right:
            return True
        for group in self._state_equivalence_config().get("tool_aliases", []):
            if left in group and right in group:
                return True
        return False

    def _equivalent_rule_matches(
        self, rule: Mapping[str, Any], event: Mapping[str, Any]
    ) -> bool:
        if not self._equivalent_tools(str(rule.get("tool")), str(event.get("tool"))):
            return False
        if "arguments" in rule and event.get("arguments") != rule["arguments"]:
            return False
        if "result" in rule and event.get("result") != rule["result"]:
            return False
        return "is_error" not in rule or event.get("is_error", False) == rule["is_error"]

    def _intent_key(self, rule: Mapping[str, Any]) -> tuple[str, str]:
        arguments = deepcopy(rule.get("arguments", {}))
        patterns = [
            _tokens(path)
            for path in self._state_equivalence_config().get(
                "ignore_argument_paths", []
            )
        ]
        normalized = _prune(arguments, [], patterns)
        if normalized is _IGNORED:
            normalized = {}
        tool = str(rule.get("tool"))
        for group in self._state_equivalence_config().get("tool_aliases", []):
            if tool in group:
                tool = "alias:" + "|".join(sorted(group))
                break
        return tool, repr(normalized)

    def _state_equivalent_path_indexes(
        self,
        expected: Sequence[Mapping[str, Any]],
        observed: Sequence[Mapping[str, Any]],
        *,
        ordered: bool,
        grouped: bool,
    ) -> set[int] | None:
        if grouped:
            groups: List[List[Mapping[str, Any]]] = []
            by_key: Dict[tuple[str, str], List[Mapping[str, Any]]] = {}
            for rule in expected:
                by_key.setdefault(self._intent_key(rule), []).append(rule)
            groups = list(by_key.values())
        else:
            groups = [[rule] for rule in expected]

        allow_failed = bool(
            self._state_equivalence_config().get("allow_failed_expected", False)
        )

        def candidates(rules: Sequence[Mapping[str, Any]]) -> List[int]:
            matches = [
                index
                for index, event in enumerate(observed)
                if any(
                    (
                        (allow_failed or not event.get("is_error", False) or rule.get("is_error") is True)
                        and (
                            self._path_rule_matches(rule, event)
                            if grouped
                            else self._equivalent_rule_matches(rule, event)
                        )
                    )
                    for rule in rules
                )
            ]
            if not ordered:
                matches.sort(key=lambda index: bool(observed[index].get("is_error", False)))
            return matches

        possible = [candidates(group) for group in groups]
        if any(not indexes for indexes in possible):
            return None
        if ordered:
            matched: set[int] = set()
            cursor = 0
            for indexes in possible:
                match = next((index for index in indexes if index >= cursor), None)
                if match is None:
                    return None
                matched.add(match)
                cursor = match + 1
            return matched

        matched_events: Dict[int, int] = {}
        order = sorted(range(len(possible)), key=lambda index: len(possible[index]))

        def assign(group_index: int, visited: set[int]) -> bool:
            for event_index in possible[group_index]:
                if event_index in visited:
                    continue
                visited.add(event_index)
                previous_group = matched_events.get(event_index)
                if previous_group is None or assign(previous_group, visited):
                    matched_events[event_index] = group_index
                    return True
            return False

        if not all(assign(group_index, set()) for group_index in order):
            return None
        return set(matched_events)

    def _is_allowed_idempotent_extra(
        self, expected: Sequence[Mapping[str, Any]], event: Mapping[str, Any]
    ) -> bool:
        if self._state_equivalence_mode() not in {"outcome", "hybrid"}:
            return False
        if event.get("is_error", False):
            return False
        if event.get("tool") not in self._state_equivalence_config().get(
            "idempotent_tools", []
        ):
            return False
        return any(self._equivalent_rule_matches(rule, event) for rule in expected)

    def _is_allowed_failed_expected_extra(
        self, expected: Sequence[Mapping[str, Any]], event: Mapping[str, Any]
    ) -> bool:
        if self._state_equivalence_mode() not in {"outcome", "hybrid"}:
            return False
        if not self._state_equivalence_config().get("allow_failed_expected", False):
            return False
        if not event.get("is_error", False):
            return False
        return any(self._path_rule_matches(rule, event) for rule in expected)

    def _path_match_indexes(
        self,
        expected: Sequence[Mapping[str, Any]],
        observed: Sequence[Mapping[str, Any]],
        *,
        mode: str,
        ordered: bool,
    ) -> set[int] | None:
        if mode == "ordered_subsequence":
            matched: set[int] = set()
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
                    return None
                matched.add(match_index)
                observed_index = match_index + 1
            return matched
        if mode == "unordered_subset":
            return self._unordered_path_rule_indexes(expected, observed)
        if ordered:
            if len(expected) == len(observed) and all(
                self._path_rule_matches(rule, event)
                for rule, event in zip(expected, observed)
            ):
                return set(range(len(observed)))
            return None
        if len(expected) != len(observed):
            return None
        return self._unordered_path_rule_indexes(expected, observed)

    def _unordered_path_rules_match(
        self,
        expected: Sequence[Mapping[str, Any]],
        observed: Sequence[Mapping[str, Any]],
    ) -> bool:
        """Match each rule to a distinct event without greedy false negatives."""
        return self._unordered_path_rule_indexes(expected, observed) is not None

    def _unordered_path_rule_indexes(
        self,
        expected: Sequence[Mapping[str, Any]],
        observed: Sequence[Mapping[str, Any]],
    ) -> set[int] | None:
        """Return a deterministic distinct-event assignment for unordered rules."""
        if len(expected) > len(observed):
            return None
        candidates = [
            [
                index
                for index, event in enumerate(observed)
                if self._path_rule_matches(rule, event)
            ]
            for rule in expected
        ]
        if any(not matches for matches in candidates):
            return None
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

        if not all(assign(rule_index, set()) for rule_index in order):
            return None
        return set(matched_events)

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
