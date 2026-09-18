"""Multi-turn Agent sessions and deterministic session comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from typing import Any, Dict, List, Mapping, Sequence

from .compare import ComparisonPolicy, compare_traces
from .model import AgentTrace, TraceValidationError
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


SUPPORTED_SESSION_SCHEMA_VERSION = "0.1"


@dataclass(frozen=True)
class AgentSession:
    """A validated sequence of one-answer AgentTrace turns."""

    session_id: str
    agent: Dict[str, Any]
    turns: List[AgentTrace]
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = SUPPORTED_SESSION_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AgentSession":
        session = cls(
            schema_version=value.get("schema_version", ""),
            session_id=value.get("session_id", ""),
            agent=dict(value.get("agent", {})),
            turns=[AgentTrace.from_dict(item) for item in value.get("turns", [])],
            metadata=dict(value.get("metadata", {})),
        )
        session.validate()
        return session

    def validate(self) -> None:
        if self.schema_version != SUPPORTED_SESSION_SCHEMA_VERSION:
            raise TraceValidationError(
                f"unsupported session schema_version {self.schema_version!r}; "
                f"expected {SUPPORTED_SESSION_SCHEMA_VERSION!r}"
            )
        if not self.session_id:
            raise TraceValidationError("session_id must be a non-empty string")
        if not isinstance(self.agent.get("name"), str) or not self.agent["name"]:
            raise TraceValidationError("session agent.name must be a non-empty string")
        if not self.turns:
            raise TraceValidationError("session turns must not be empty")
        run_ids = set()
        for index, turn in enumerate(self.turns, start=1):
            turn.validate()
            if turn.run_id in run_ids:
                raise TraceValidationError("session turn run_id values must be unique")
            run_ids.add(turn.run_id)
            turn_number = turn.metadata.get("turn")
            if turn_number is not None and turn_number != index:
                raise TraceValidationError(
                    f"session turn metadata.turn must be {index}, got {turn_number!r}"
                )

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "agent": deepcopy(self.agent),
            "turns": [turn.to_dict() for turn in self.turns],
            "metadata": deepcopy(self.metadata),
        }


def compare_sessions(
    baseline: AgentSession,
    candidate: AgentSession,
    policy: ComparisonPolicy | None = None,
    redaction_policy: RedactionPolicy | None = None,
) -> Dict[str, Any]:
    """Compare matching turns and preserve each turn's blocking differences."""
    baseline.validate()
    candidate.validate()
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    active_policy = policy or ComparisonPolicy()
    differences: List[Dict[str, Any]] = []
    if len(baseline.turns) != len(candidate.turns):
        differences.append(
            {
                "category": "session_turn_count",
                "path": "turns.count",
                "baseline": len(baseline.turns),
                "candidate": len(candidate.turns),
                "allowed": False,
            }
        )

    turns: List[Dict[str, Any]] = []
    for index, (left, right) in enumerate(zip(baseline.turns, candidate.turns), start=1):
        comparison = compare_traces(
            left,
            right,
            policy=active_policy,
            redaction_policy=active_redaction,
        )
        turns.append({"turn": index, **comparison})
        differences.extend(
            {
                "turn": index,
                **difference,
            }
            for difference in comparison["differences"]
            if not difference.get("allowed", False)
        )

    differences = active_redaction.redact(differences)
    return {
        "schema_version": SUPPORTED_SESSION_SCHEMA_VERSION,
        "baseline_session_id": baseline.session_id,
        "candidate_session_id": candidate.session_id,
        "turn_count": len(turns),
        "passed": not differences,
        "difference_count": len(differences),
        "blocking_difference_count": len(differences),
        "policy": active_policy.to_dict(),
        "turns": turns,
        "differences": differences,
    }
