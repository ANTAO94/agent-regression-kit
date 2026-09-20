"""Auditable evaluation of recorded online-Agent sampling studies.

The framework cannot safely infer a provider's hidden prompt, account state or
sampling population.  This module therefore accepts traces recorded by the
caller and a small public provenance manifest.  It evaluates the traces with
the existing Contract/Comparison/Stability machinery without storing prompts,
API keys or raw provider responses in the study report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .compare import ComparisonPolicy
from .contracts import ContractPolicy
from .model import AgentTrace
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy
from .stability import StabilityPolicy, StabilityReport, evaluate_stability


STUDY_SCHEMA_VERSION = "0.1"
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth(?:orization)?|credential|password|secret)",
    re.IGNORECASE,
)
_PROVENANCE_FIELDS = {
    "provider",
    "model",
    "adapter",
    "study_id",
    "input_sha256",
    "tool_schema_sha256",
    "dataset_revision",
    "parameters",
}
_COMPARISON_FIELDS = {
    "mode",
    "allowed_categories",
    "allowed_paths",
    "final_answer_mode",
    "result_alignment",
    "contract",
}
_POLICY_FIELDS = {
    "min_pass_rate",
    "min_claims_match_rate",
    "max_tool_error_rate",
    "max_path_variants",
    "min_runs",
}
_INTEGRITY_FIELDS = {
    "require_trace_hashes",
    "baseline_sha256",
    "comparison_policy_sha256",
}


def canonical_sha256(value: Any) -> str:
    """Hash a JSON-compatible input without storing the input itself."""
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash one evidence file without loading its contents into a report."""
    return hashlib.sha256(Path(path).expanduser().read_bytes()).hexdigest()


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a 64-character SHA-256 hex string")
    return value.lower()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _public_json(value: Any, path: str) -> Any:
    """Validate JSON metadata and reject fields that commonly carry secrets."""
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{path} object keys must be non-empty strings")
            if _SECRET_KEY_RE.search(key):
                raise ValueError(f"{path}.{key} must not contain credentials or secrets")
            result[key] = _public_json(child, f"{path}.{key}")
        return result
    if isinstance(value, list):
        return [_public_json(child, f"{path}[{index}]") for index, child in enumerate(value)]
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise ValueError(f"{path} must not contain NaN or infinity")
        return value
    raise ValueError(f"{path} must contain JSON-compatible values")


@dataclass(frozen=True)
class SamplingProvenance:
    """Non-secret identity of the provider run represented by a study."""

    provider: str
    model: str
    input_sha256: str
    adapter: str | None = None
    study_id: str | None = None
    tool_schema_sha256: str | None = None
    dataset_revision: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _text(self.provider, "provider"))
        object.__setattr__(self, "model", _text(self.model, "model"))
        object.__setattr__(self, "input_sha256", _digest(self.input_sha256, "input_sha256"))
        for name in ("adapter", "study_id", "dataset_revision"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _text(value, name))
        if self.tool_schema_sha256 is not None:
            object.__setattr__(
                self,
                "tool_schema_sha256",
                _digest(self.tool_schema_sha256, "tool_schema_sha256"),
            )
        if not isinstance(self.parameters, Mapping):
            raise ValueError("parameters must be an object")
        safe_parameters = _public_json(dict(self.parameters), "parameters")
        if not isinstance(safe_parameters, dict):
            raise ValueError("parameters must be an object")
        object.__setattr__(self, "parameters", safe_parameters)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SamplingProvenance":
        if not isinstance(value, Mapping):
            raise ValueError("provenance must be an object")
        unknown = sorted(set(value) - _PROVENANCE_FIELDS)
        if unknown:
            raise ValueError("unsupported provenance fields: " + ", ".join(unknown))
        return cls(
            provider=value.get("provider"),
            model=value.get("model"),
            input_sha256=value.get("input_sha256"),
            adapter=value.get("adapter"),
            study_id=value.get("study_id"),
            tool_schema_sha256=value.get("tool_schema_sha256"),
            dataset_revision=value.get("dataset_revision"),
            parameters=value.get("parameters", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        value: Dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "input_sha256": self.input_sha256,
            "parameters": dict(self.parameters),
        }
        for name in ("adapter", "study_id", "tool_schema_sha256", "dataset_revision"):
            optional = getattr(self, name)
            if optional is not None:
                value[name] = optional
        return value


@dataclass(frozen=True)
class SamplingStudyReport:
    """Stability result plus the provenance needed to interpret its sample."""

    study_id: str
    manifest_sha256: str
    provenance: SamplingProvenance
    stability: StabilityReport
    evidence_integrity: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.stability.passed

    def to_dict(self) -> Dict[str, Any]:
        value = self.stability.to_dict()
        value.update(
            {
                "schema_version": STUDY_SCHEMA_VERSION,
                "report_type": "agent_sampling_study",
                "study_id": self.study_id,
                "manifest_sha256": self.manifest_sha256,
                "provenance": self.provenance.to_dict(),
                "evidence_integrity": dict(self.evidence_integrity),
            }
        )
        return value


def _relative_file(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError(f"{label} must be relative to the study manifest")
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the study directory") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} not found: {value}")
    return resolved


def _load_trace(path: Path, label: str) -> AgentTrace:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        trace = AgentTrace.from_dict(value)
        trace.validate()
        return trace
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not a valid AgentTrace: {path}") from exc


def _comparison_policy(value: Any) -> ComparisonPolicy:
    if value is None:
        return ComparisonPolicy()
    if not isinstance(value, Mapping):
        raise ValueError("comparison_policy must be an object")
    unknown = sorted(set(value) - _COMPARISON_FIELDS)
    if unknown:
        raise ValueError("unsupported comparison_policy fields: " + ", ".join(unknown))
    categories = value.get("allowed_categories", [])
    paths = value.get("allowed_paths", [])
    mode = value.get("mode")
    if mode is not None and mode not in {"strict", "allow_list"}:
        raise ValueError("comparison_policy.mode must be 'strict' or 'allow_list'")
    if not isinstance(categories, list) or not all(isinstance(item, str) for item in categories):
        raise ValueError("comparison_policy.allowed_categories must be an array of strings")
    if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
        raise ValueError("comparison_policy.allowed_paths must be an array of strings")
    contract = value.get("contract")
    if contract is not None and not isinstance(contract, Mapping):
        raise ValueError("comparison_policy.contract must be an object")
    return ComparisonPolicy(
        allowed_categories=set(categories),
        allowed_paths=set(paths),
        final_answer_mode=value.get("final_answer_mode", "exact"),
        result_alignment=value.get("result_alignment", "call_id"),
        contract=ContractPolicy.from_dict(contract or {}),
    )


def _stability_policy(value: Any) -> StabilityPolicy:
    if value is None:
        return StabilityPolicy()
    if not isinstance(value, Mapping):
        raise ValueError("policy must be an object")
    unknown = sorted(set(value) - _POLICY_FIELDS)
    if unknown:
        raise ValueError("unsupported policy fields: " + ", ".join(unknown))
    return StabilityPolicy(**dict(value))


def _integrity_policy(value: Any) -> Dict[str, Any]:
    if value is None:
        return {
            "require_trace_hashes": False,
            "baseline_sha256": None,
            "comparison_policy_sha256": None,
        }
    if not isinstance(value, Mapping):
        raise ValueError("integrity must be an object")
    unknown = sorted(set(value) - _INTEGRITY_FIELDS)
    if unknown:
        raise ValueError("unsupported integrity fields: " + ", ".join(unknown))
    require = value.get("require_trace_hashes", False)
    if not isinstance(require, bool):
        raise ValueError("integrity.require_trace_hashes must be boolean")
    baseline_sha256 = value.get("baseline_sha256")
    if baseline_sha256 is not None:
        baseline_sha256 = _digest(baseline_sha256, "integrity.baseline_sha256")
    comparison_sha256 = value.get("comparison_policy_sha256")
    if comparison_sha256 is not None:
        comparison_sha256 = _digest(
            comparison_sha256,
            "integrity.comparison_policy_sha256",
        )
    if require and baseline_sha256 is None:
        raise ValueError(
            "integrity.baseline_sha256 is required when trace hashes are required"
        )
    return {
        "require_trace_hashes": require,
        "baseline_sha256": baseline_sha256,
        "comparison_policy_sha256": comparison_sha256,
    }


def evaluate_sampling_study(
    manifest_path: str | Path,
    *,
    redaction_policy: RedactionPolicy | None = None,
) -> SamplingStudyReport:
    """Evaluate traces listed by a provider-neutral sampling-study manifest.

    The manifest is the audit boundary: it fixes the input/tool-schema hashes,
    comparison Contract and policy, while the report stores only those public
    identifiers and per-run outcomes.
    """
    manifest_file = Path(manifest_path).expanduser().resolve()
    try:
        raw = json.loads(manifest_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"study manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"study manifest is not valid JSON: {manifest_path}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("study manifest must be an object")
    allowed = {
        "schema_version",
        "study_id",
        "baseline",
        "runs",
        "provenance",
        "comparison_policy",
        "policy",
        "integrity",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError("unsupported study manifest fields: " + ", ".join(unknown))
    if raw.get("schema_version") != STUDY_SCHEMA_VERSION:
        raise ValueError(f"study manifest schema_version must be {STUDY_SCHEMA_VERSION!r}")
    study_id = _text(raw.get("study_id"), "study_id")
    provenance = SamplingProvenance.from_dict(raw.get("provenance", {}))
    if provenance.study_id is not None and provenance.study_id != study_id:
        raise ValueError("provenance.study_id must match study_id")
    root = manifest_file.parent
    integrity_policy = _integrity_policy(raw.get("integrity"))
    baseline_path = _relative_file(root, raw.get("baseline"), "baseline")
    observed_baseline_sha256 = sha256_file(baseline_path)
    expected_baseline_sha256 = integrity_policy["baseline_sha256"]
    if expected_baseline_sha256 and observed_baseline_sha256 != expected_baseline_sha256:
        raise ValueError(
            "baseline SHA-256 mismatch: "
            f"expected {expected_baseline_sha256}, observed {observed_baseline_sha256}"
        )
    baseline = _load_trace(baseline_path, "baseline")
    raw_runs = raw.get("runs")
    if not isinstance(raw_runs, list) or not raw_runs:
        raise ValueError("runs must be a non-empty array")
    runs: List[AgentTrace] = []
    run_evidence: List[Dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_runs):
        if not isinstance(item, Mapping):
            raise ValueError(f"runs[{index}] must be an object")
        allowed_run_fields = {"id", "trace", "sha256"}
        if not set(item).issubset(allowed_run_fields):
            unknown_run_fields = sorted(set(item) - allowed_run_fields)
            if unknown_run_fields:
                raise ValueError(
                    f"unsupported runs[{index}] fields: " + ", ".join(unknown_run_fields)
                )
        if "id" not in item or "trace" not in item:
            raise ValueError(f"runs[{index}] must contain id and trace")
        run_id = _text(item.get("id"), f"runs[{index}].id")
        if run_id in seen:
            raise ValueError(f"duplicate run id: {run_id}")
        seen.add(run_id)
        trace_path = _relative_file(root, item.get("trace"), f"runs[{index}].trace")
        observed_trace_sha256 = sha256_file(trace_path)
        expected_trace_sha256 = item.get("sha256")
        if expected_trace_sha256 is not None:
            expected_trace_sha256 = _digest(
                expected_trace_sha256,
                f"runs[{index}].sha256",
            )
        if integrity_policy["require_trace_hashes"] and expected_trace_sha256 is None:
            raise ValueError(
                f"runs[{index}].sha256 is required when trace hashes are required"
            )
        if expected_trace_sha256 and observed_trace_sha256 != expected_trace_sha256:
            raise ValueError(
                f"runs[{index}] SHA-256 mismatch: expected {expected_trace_sha256}, "
                f"observed {observed_trace_sha256}"
            )
        trace = _load_trace(trace_path, f"runs[{index}].trace")
        if trace.run_id != run_id:
            raise ValueError(
                f"runs[{index}] id must match trace.run_id: {run_id!r} != {trace.run_id!r}"
            )
        runs.append(trace)
        run_evidence.append({"id": run_id, "sha256": observed_trace_sha256})
    comparison = _comparison_policy(raw.get("comparison_policy"))
    observed_comparison_sha256 = canonical_sha256(comparison.to_dict())
    expected_comparison_sha256 = integrity_policy["comparison_policy_sha256"]
    if (
        expected_comparison_sha256
        and observed_comparison_sha256 != expected_comparison_sha256
    ):
        raise ValueError(
            "comparison policy SHA-256 mismatch: "
            f"expected {expected_comparison_sha256}, observed {observed_comparison_sha256}"
        )
    policy = _stability_policy(raw.get("policy"))
    stability = evaluate_stability(
        baseline,
        runs,
        comparison_policy=comparison,
        policy=policy,
        redaction_policy=redaction_policy or DEFAULT_REDACTION_POLICY,
    )
    manifest_sha256 = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    return SamplingStudyReport(
        study_id=study_id,
        manifest_sha256=manifest_sha256,
        provenance=provenance,
        stability=stability,
        evidence_integrity={
            "trace_hashes_required": integrity_policy["require_trace_hashes"],
            "trace_hashes_verified": bool(integrity_policy["require_trace_hashes"]),
            "baseline_sha256": observed_baseline_sha256,
            "comparison_policy_sha256": observed_comparison_sha256,
            "runs": run_evidence,
        },
    )


__all__ = [
    "STUDY_SCHEMA_VERSION",
    "SamplingProvenance",
    "SamplingStudyReport",
    "canonical_sha256",
    "evaluate_sampling_study",
    "sha256_file",
]
