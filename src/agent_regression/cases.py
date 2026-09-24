"""Evaluation case definitions, immutable evidence references, and approval fingerprints."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
from pathlib import Path
import re
import uuid
from typing import Any, Mapping

from .contracts import ContractPolicy, _tokens
from .incidents import (
    IncidentValidationError,
    canonical_sha256,
    make_reference,
    resolve_reference,
    safe_input_path,
    safe_output_path,
    atomic_write_json,
)
from .model import AgentTrace


CASE_SCHEMA_VERSION = "0.1"
CASE_KINDS = {"trace"}
CASE_STATUSES = {"draft", "approved", "retired"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CaseValidationError(ValueError):
    """Raised when a case definition, its evidence, or approval is invalid."""


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseValidationError(f"cannot read {label} JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CaseValidationError(f"{label} must be a JSON object")
    return value


def _check_policy(path: Path) -> dict[str, Any]:
    raw = _load_json(path, "case policy")
    allowed = {
        "schema_version", "policy_id", "baseline", "candidate", "report", "format",
        "final_answer_mode", "result_alignment", "allow_categories", "allow_paths",
        "contract", "secret_values", "evidence_requirements",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise CaseValidationError("unsupported case policy fields: " + ", ".join(sorted(unknown)))
    for key in ("allow_categories", "allow_paths", "secret_values"):
        if key in raw and (
            not isinstance(raw[key], list)
            or not all(isinstance(value, str) for value in raw[key])
        ):
            raise CaseValidationError(f"policy.{key} must be an array of strings")
    if raw.get("final_answer_mode", "exact") not in {"exact", "claims-only"}:
        raise CaseValidationError("policy.final_answer_mode must be exact or claims-only")
    if raw.get("result_alignment", "call_id") not in {"call_id", "order"}:
        raise CaseValidationError("policy.result_alignment must be call_id or order")
    try:
        ContractPolicy.from_dict(raw.get("contract", {}))
    except (TypeError, ValueError) as exc:
        raise CaseValidationError(f"invalid case Contract: {exc}") from exc
    requirements = raw.get("evidence_requirements", [])
    if not isinstance(requirements, list) or not all(isinstance(item, dict) for item in requirements):
        raise CaseValidationError("policy.evidence_requirements must be an array of objects")
    for item in requirements:
        if set(item) - {"path", "exists", "type"}:
            raise CaseValidationError("evidence requirement supports only path, exists, and type")
        if not isinstance(item.get("path"), str) or not item["path"].strip():
            raise CaseValidationError("evidence requirement path must be a non-empty string")
        try:
            _tokens(item["path"])
        except ValueError as exc:
            raise CaseValidationError(f"invalid evidence requirement path: {item['path']!r}") from exc
        if "exists" in item and not isinstance(item["exists"], bool):
            raise CaseValidationError("evidence requirement exists must be a boolean")
        if "type" in item and item["type"] not in {
            "string", "number", "integer", "boolean", "object", "array", "null"
        }:
            raise CaseValidationError("evidence requirement type is unsupported")
    contract_paths: list[str] = []
    contract_raw = raw.get("contract") or {}
    for assertion in contract_raw.get("assertions", []):
        if isinstance(assertion, dict) and isinstance(assertion.get("path"), str):
            contract_paths.append(assertion["path"])
    for path in contract_raw.get("required_claims", []):
        if isinstance(path, str):
            contract_paths.append(path)
    for relation in contract_raw.get("relations", []):
        if isinstance(relation, dict):
            contract_paths.extend(
                value for key in ("left", "right_path")
                if isinstance((value := relation.get(key)), str)
            )
    for side_effect in contract_raw.get("side_effects", []):
        if isinstance(side_effect, dict) and isinstance(side_effect.get("path"), str):
            contract_paths.append(side_effect["path"])

    def path_segments(path: str) -> tuple[str, ...]:
        return tuple(token for token in path.replace("[", ".").replace("]", "").split(".") if token)

    for requirement in requirements:
        required_path = path_segments(requirement["path"])
        for contract_path in contract_paths:
            business_path = path_segments(contract_path)
            shared_prefix = required_path[: min(len(required_path), len(business_path))] == business_path[: min(len(required_path), len(business_path))]
            if shared_prefix:
                raise CaseValidationError(
                    "evidence_requirements path conflicts with a Contract business assertion: "
                    f"{requirement['path']!r} overlaps {contract_path!r}"
                )
    if any(key in raw for key in ("baseline", "candidate", "report")):
        # Old compare configs can be used as policies, but these path fields
        # never control the lifecycle runner's evidence selection.
        for key in ("baseline", "candidate", "report"):
            if key in raw and not isinstance(raw[key], str):
                raise CaseValidationError(f"policy.{key} must be a string")
    return raw


@dataclass(frozen=True)
class EvaluationCase:
    schema_version: str
    case_id: str
    revision: int
    title: str
    kind: str
    status: str
    tags: list[str]
    baseline_ref: dict[str, str]
    policy_ref: dict[str, str]
    expected_behavior: str
    incident_refs: list[str] = field(default_factory=list)
    input_ref: dict[str, str] | None = None
    environment_ref: dict[str, str] | None = None
    evidence_requirements: list[dict[str, Any]] = field(default_factory=list)
    review: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvaluationCase":
        if not isinstance(value, Mapping):
            raise CaseValidationError("case must be an object")
        allowed = {
            "schema_version", "case_id", "revision", "title", "kind", "status", "tags",
            "baseline_ref", "policy_ref", "expected_behavior", "incident_refs", "input_ref",
            "environment_ref", "evidence_requirements", "review",
        }
        unknown = set(value) - allowed
        if unknown:
            raise CaseValidationError("unsupported case fields: " + ", ".join(sorted(unknown)))
        for key in ("tags", "incident_refs", "evidence_requirements"):
            if not isinstance(value.get(key, []), list):
                raise CaseValidationError(f"case.{key} must be an array")
        try:
            case = cls(
                schema_version=value.get("schema_version", ""),
                case_id=value.get("case_id", ""),
                revision=value.get("revision", 0),
                title=value.get("title", ""),
                kind=value.get("kind", ""),
                status=value.get("status", ""),
                tags=list(value.get("tags", [])),
                baseline_ref=dict(value.get("baseline_ref", {})),
                policy_ref=dict(value.get("policy_ref", {})),
                expected_behavior=value.get("expected_behavior", ""),
                incident_refs=list(value.get("incident_refs", [])),
                input_ref=dict(value["input_ref"]) if isinstance(value.get("input_ref"), Mapping) else value.get("input_ref"),
                environment_ref=dict(value["environment_ref"]) if isinstance(value.get("environment_ref"), Mapping) else value.get("environment_ref"),
                evidence_requirements=[dict(item) for item in value.get("evidence_requirements", [])],
                review=dict(value["review"]) if isinstance(value.get("review"), Mapping) else value.get("review"),
            )
        except (TypeError, ValueError) as exc:
            raise CaseValidationError(f"invalid case fields: {exc}") from exc
        case.validate()
        return case

    def validate(self) -> None:
        if self.schema_version != CASE_SCHEMA_VERSION:
            raise CaseValidationError(f"unsupported case schema_version {self.schema_version!r}")
        for field_name in ("case_id", "title", "expected_behavior"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise CaseValidationError(f"case.{field_name} must be a non-empty string")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise CaseValidationError("case.revision must be a positive integer")
        if self.kind not in CASE_KINDS:
            if self.kind == "session":
                raise CaseValidationError("session cases are not supported by this lifecycle version")
            raise CaseValidationError("case.kind must be 'trace'")
        if self.status not in CASE_STATUSES:
            raise CaseValidationError("case.status must be draft, approved, or retired")
        if not isinstance(self.tags, list) or not all(isinstance(item, str) and item.strip() for item in self.tags):
            raise CaseValidationError("case.tags must be an array of non-empty strings")
        if not isinstance(self.incident_refs, list) or not all(isinstance(item, str) and item.strip() for item in self.incident_refs):
            raise CaseValidationError("case.incident_refs must be an array of incident IDs")
        for label, ref, required in (
            ("baseline_ref", self.baseline_ref, True),
            ("policy_ref", self.policy_ref, True),
            ("input_ref", self.input_ref, False),
            ("environment_ref", self.environment_ref, False),
        ):
            if ref is None and not required:
                continue
            if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
                raise CaseValidationError(f"case.{label} must contain path and sha256")
            if not isinstance(ref.get("path"), str) or not ref["path"].strip():
                raise CaseValidationError(f"case.{label}.path must be a non-empty string")
            if not isinstance(ref.get("sha256"), str) or not _SHA256_RE.fullmatch(ref["sha256"]):
                raise CaseValidationError(f"case.{label}.sha256 must be a SHA-256 hex digest")
        if not isinstance(self.evidence_requirements, list):
            raise CaseValidationError("case.evidence_requirements must be an array")
        for item in self.evidence_requirements:
            if not isinstance(item, dict) or set(item) - {"path", "exists", "type"}:
                raise CaseValidationError("case evidence requirement has unsupported fields")
            if not isinstance(item.get("path"), str) or not item["path"].strip():
                raise CaseValidationError("case evidence requirement path must be non-empty")
            try:
                _tokens(item["path"])
            except ValueError as exc:
                raise CaseValidationError(f"invalid case evidence path: {item['path']!r}") from exc
            if "exists" in item and not isinstance(item["exists"], bool):
                raise CaseValidationError("case evidence requirement exists must be a boolean")
            if "type" in item and item["type"] not in {
                "string", "number", "integer", "boolean", "object", "array", "null"
            }:
                raise CaseValidationError("case evidence requirement type is unsupported")
        if self.status == "approved":
            if not isinstance(self.review, dict):
                raise CaseValidationError("approved cases require a review record")
            for key in ("reviewer", "reviewed_at", "reason", "definition_sha256"):
                if not isinstance(self.review.get(key), str) or not self.review[key].strip():
                    raise CaseValidationError(f"approved case review.{key} must be non-empty")
            if not _SHA256_RE.fullmatch(self.review["definition_sha256"]):
                raise CaseValidationError("review.definition_sha256 must be a SHA-256 hex digest")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_case(path: str | Path) -> EvaluationCase:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseValidationError(f"cannot read case {path}: {exc}") from exc
    return EvaluationCase.from_dict(raw)


def create_case_draft(
    *, root: str | Path, baseline_path: str | Path, policy_path: str | Path,
    title: str, expected_behavior: str, case_id: str | None = None,
    revision: int = 1,
    incident_refs: list[str] | None = None, tags: list[str] | None = None,
    input_path: str | Path | None = None, environment_path: str | Path | None = None,
    evidence_requirements: list[dict[str, Any]] | None = None,
) -> EvaluationCase:
    root_path = Path(root).expanduser().resolve()
    baseline_abs = safe_input_path(root_path, baseline_path)
    policy_abs = safe_input_path(root_path, policy_path)
    baseline_ref_full = make_reference(root_path, baseline_path, role="baseline")
    policy_ref_full = make_reference(root_path, policy_path, role="policy")
    baseline_data = _load_json(baseline_abs, "baseline Trace")
    AgentTrace.from_dict(baseline_data)
    _check_policy(policy_abs)
    optional_refs = {}
    for key, path in (("input_ref", input_path), ("environment_ref", environment_path)):
        if path is None:
            optional_refs[key] = None
            continue
        safe_input_path(root_path, path)
        full_ref = make_reference(root_path, path, role=key)
        optional_refs[key] = {"path": full_ref["path"], "sha256": full_ref["sha256"]}
    case = EvaluationCase(
        schema_version=CASE_SCHEMA_VERSION,
        case_id=case_id or "case-" + uuid.uuid4().hex[:12],
        revision=revision,
        title=title,
        kind="trace",
        status="draft",
        tags=list(tags or []),
        baseline_ref={"path": baseline_ref_full["path"], "sha256": baseline_ref_full["sha256"]},
        policy_ref={"path": policy_ref_full["path"], "sha256": policy_ref_full["sha256"]},
        expected_behavior=expected_behavior,
        incident_refs=list(incident_refs or []),
        input_ref=optional_refs["input_ref"],
        environment_ref=optional_refs["environment_ref"],
        evidence_requirements=list(evidence_requirements or []),
    )
    case.validate()
    return case


def revise_case(
    *, root: str | Path, case_path: str | Path,
    baseline_path: str | Path | None = None, policy_path: str | Path | None = None,
    input_path: str | Path | None = None, environment_path: str | Path | None = None,
    title: str | None = None, expected_behavior: str | None = None,
) -> EvaluationCase:
    """Create a new draft revision without mutating the previously reviewed case."""
    old = load_case(safe_input_path(root, case_path))
    return create_case_draft(
        root=root,
        baseline_path=baseline_path or old.baseline_ref["path"],
        policy_path=policy_path or old.policy_ref["path"],
        title=title or old.title,
        expected_behavior=expected_behavior or old.expected_behavior,
        case_id=old.case_id,
        revision=old.revision + 1,
        incident_refs=old.incident_refs,
        tags=old.tags,
        input_path=input_path or (old.input_ref["path"] if old.input_ref else None),
        environment_path=environment_path or (
            old.environment_ref["path"] if old.environment_ref else None
        ),
        evidence_requirements=old.evidence_requirements,
    )


def case_definition_payload(case: EvaluationCase) -> dict[str, Any]:
    return {
        "schema_version": case.schema_version,
        "case_id": case.case_id,
        "revision": case.revision,
        "title": case.title,
        "kind": case.kind,
        "tags": case.tags,
        "input_ref": case.input_ref,
        "environment_ref": case.environment_ref,
        "baseline_ref": case.baseline_ref,
        "policy_ref": case.policy_ref,
        "expected_behavior": case.expected_behavior,
        "incident_refs": case.incident_refs,
        "evidence_requirements": case.evidence_requirements,
    }


def case_definition_sha256(case: EvaluationCase) -> str:
    return canonical_sha256(case_definition_payload(case))


def validate_case(case: EvaluationCase, root: str | Path, *, require_approved: bool = False) -> dict[str, Path]:
    case.validate()
    if require_approved and case.status != "approved":
        raise CaseValidationError("case is not approved; draft cases cannot be used as CI gates")
    paths: dict[str, Path] = {}
    for key in ("baseline_ref", "policy_ref", "input_ref", "environment_ref"):
        reference = getattr(case, key)
        if reference is None:
            continue
        try:
            paths[key] = resolve_reference(root, reference)
        except IncidentValidationError as exc:
            raise CaseValidationError(str(exc)) from exc
    AgentTrace.from_dict(_load_json(paths["baseline_ref"], "baseline Trace"))
    _check_policy(paths["policy_ref"])
    if case.status == "approved":
        expected = case.review["definition_sha256"]
        actual = case_definition_sha256(case)
        if actual != expected:
            raise CaseValidationError("approved case definition changed; create a new revision and review it again")
        if require_approved:
            _validate_review_evidence(case, root, paths)
    return paths


def _validate_review_evidence(
    case: EvaluationCase, root: str | Path, paths: dict[str, Path],
) -> None:
    """Re-evaluate both samples against a draft view to avoid approval recursion."""
    runs = case.review.get("validation_runs")
    if not isinstance(runs, list) or len(runs) != 2:
        raise CaseValidationError("approved case requires positive and negative validation_runs; revise and re-review")
    by_role: dict[str, dict[str, Any]] = {}
    for run in runs:
        if not isinstance(run, dict) or set(run) != {"role", "candidate_ref", "run_id", "outcome", "report_ref"}:
            raise CaseValidationError("review.validation_runs entries require role, candidate_ref, run_id, outcome, and report_ref")
        role = run["role"]
        if role not in {"positive", "negative"} or role in by_role:
            raise CaseValidationError("review.validation_runs must contain one positive and one negative role")
        if not isinstance(run["run_id"], str) or not run["run_id"].strip():
            raise CaseValidationError(f"review {role} run_id must be non-empty")
        if run["outcome"] != {"positive": "pass", "negative": "fail"}[role]:
            raise CaseValidationError(f"review {role} outcome must be {('pass' if role == 'positive' else 'fail')}")
        by_role[role] = run

    from .case_runner import _compare

    draft = replace(case, status="draft", review=None)
    for role in ("positive", "negative"):
        run = by_role[role]
        for label in ("candidate_ref", "report_ref"):
            ref = run[label]
            if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
                raise CaseValidationError(f"review {role} {label} must contain path and sha256")
            try:
                path = resolve_reference(root, ref)
            except (IncidentValidationError, OSError) as exc:
                raise CaseValidationError(f"review {role} {label}: {exc}") from exc
            paths[f"review_{role}_{label}"] = path
        candidate = AgentTrace.from_dict(_load_json(paths[f"review_{role}_candidate_ref"], f"review {role} Trace"))
        report = _load_json(paths[f"review_{role}_report_ref"], f"review {role} report")
        if candidate.run_id != run["run_id"] or report.get("candidate_run_id") != run["run_id"]:
            raise CaseValidationError(f"review {role} run_id does not match candidate Trace and report")
        baseline = AgentTrace.from_dict(_load_json(paths["baseline_ref"], "baseline Trace"))
        if report.get("baseline_run_id") != baseline.run_id:
            raise CaseValidationError(f"review {role} report baseline_run_id does not match baseline Trace")
        recalculated, _, _ = _compare(draft, root, run["candidate_ref"]["path"])
        if (report.get("report_type") != "agent_case_compare"
                or report.get("outcome") != run["outcome"]
                or report.get("passed") != recalculated.get("passed")
                or report.get("difference_count") != recalculated.get("difference_count")
                or report.get("blocking_difference_count") != recalculated.get("blocking_difference_count")
                or report.get("policy") != recalculated.get("policy")
                or recalculated.get("outcome") != run["outcome"]):
            raise CaseValidationError(f"review {role} report outcome does not match recalculated comparison")
        # Redaction can change values, but must not change which differences block.
        def signatures(value: dict[str, Any]) -> list[tuple[Any, Any, Any]]:
            differences = value.get("differences")
            if not isinstance(differences, list) or not all(isinstance(item, dict) for item in differences):
                raise CaseValidationError(f"review {role} report differences must be an array of objects")
            return [
                (item.get("category"), item.get("path"), item.get("allowed"))
                for item in differences
            ]
        if signatures(report) != signatures(recalculated):
            raise CaseValidationError(f"review {role} report differences do not match recalculated comparison")


def save_case(case: EvaluationCase, *, root: str | Path, out_path: str | Path, overwrite: bool = False) -> Path:
    case.validate()
    try:
        path = safe_output_path(root, out_path)
        atomic_write_json(path, case.to_dict(), overwrite=overwrite)
    except IncidentValidationError as exc:
        raise CaseValidationError(str(exc)) from exc
    return path
