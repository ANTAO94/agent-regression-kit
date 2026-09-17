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
    max_steps: int | None = None

    def __post_init__(self) -> None:
        if self.max_steps is not None and (
            not isinstance(self.max_steps, int) or self.max_steps < 0
        ):
            raise ValueError("contract.max_steps must be a non-negative integer")
        for path in self.ignore_paths:
            _tokens(path)
        for normalizer in self.normalizers:
            if not isinstance(normalizer, dict):
                raise ValueError("contract.normalizers must contain objects")
            _tokens(normalizer.get("path", ""))
            if normalizer.get("type") not in {"timestamp", "sort"}:
                raise ValueError("normalizer.type must be 'timestamp' or 'sort'")
        for assertion in self.assertions:
            if not isinstance(assertion, dict) or not isinstance(assertion.get("path"), str):
                raise ValueError("contract.assertions must contain path objects")
            _tokens(assertion["path"])
            operators = {"equals", "contains", "exists"} & set(assertion)
            if len(operators) != 1:
                raise ValueError("each assertion needs exactly one of equals, contains, or exists")
        for raw_rule in [*self.must_call, *self.must_not_call]:
            rule = {"tool": raw_rule} if isinstance(raw_rule, str) else raw_rule
            if not isinstance(rule, dict) or not isinstance(rule.get("tool"), str) or not rule["tool"]:
                raise ValueError("contract tool rules must contain a non-empty tool")
            if "arguments" in rule and not isinstance(rule["arguments"], dict):
                raise ValueError("contract tool rule arguments must be an object")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ContractPolicy":
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise ValueError("contract must be an object")

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
        return cls(
            assertions=rules("assertions"),
            ignore_paths=list(ignore_paths),
            normalizers=[dict(item) for item in normalizers],
            must_call=rules("must_call"),
            must_not_call=forbidden_rules,
            max_steps=value.get("max_steps"),
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
            "max_steps": self.max_steps,
        }

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

        candidate_calls = [event for event in candidate.events if event["type"] == "tool_call"]
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

    @staticmethod
    def _tool_rule_matches(rule: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
        return event.get("tool") == rule.get("tool") and (
            "arguments" not in rule or event.get("arguments") == rule["arguments"]
        )
