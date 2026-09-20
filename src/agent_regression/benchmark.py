"""Hash-bound benchmark preparation, decision and scoring utilities.

The benchmark workflow intentionally separates three concerns:

* ``prepare`` validates immutable inputs and sample/Contract coverage;
* ``decide`` reads evidence and Contracts but never reads outcome labels;
* ``score`` reads the frozen decisions and labels only after their input
  fingerprints have been checked.

The module is dependency-free and stores relative paths plus SHA-256 digests,
not copies of Trace contents, in its provenance reports.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .compare import ComparisonPolicy, compare_traces
from .contracts import ContractPolicy
from .model import AgentTrace
from .statistics import wilson_interval
from .version import __version__


_HEX_SHA256_LENGTH = 64
_MUTABLE_REVISIONS = {"", "head", "latest", "main", "master", "trunk"}


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path, label: str) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc


def _canonical_digest(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(rendered)


def _sha256_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != _HEX_SHA256_LENGTH:
        raise ValueError(f"{label} must be a 64-character SHA-256 hex string")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be a 64-character SHA-256 hex string") from exc
    return value.lower()


def _resolve(base: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    path = (base / value).resolve()
    return path


def _verify_hashed_file(
    base: Path,
    descriptor: Mapping[str, Any],
    *,
    label: str,
) -> Dict[str, Any]:
    if not isinstance(descriptor.get("path"), str) or not descriptor["path"].strip():
        raise ValueError(f"{label}.path must be a non-empty relative path")
    expected = _sha256_value(descriptor.get("sha256"), f"{label}.sha256")
    path = _resolve(base, descriptor["path"], f"{label}.path")
    actual = _sha256_file(path, label)
    if actual != expected:
        raise ValueError(
            f"{label} SHA-256 mismatch: expected {expected}, observed {actual}"
        )
    return {
        "path": str(path),
        "relative_path": descriptor["path"],
        "sha256": actual,
    }


def _validate_revision(source: Mapping[str, Any]) -> None:
    repository = source.get("repository")
    revision = source.get("revision")
    if not isinstance(repository, str) or not repository.strip():
        raise ValueError("benchmark.source.repository must be a non-empty string")
    if not isinstance(revision, str) or revision.strip().lower() in _MUTABLE_REVISIONS:
        raise ValueError(
            "benchmark.source.revision must be an immutable tag or commit, not a moving name"
        )


def _sample_records(evidence: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw_samples = _array(evidence.get("samples"), "benchmark evidence.samples")
    result: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_sample in enumerate(raw_samples):
        sample = _object(raw_sample, f"benchmark evidence.samples[{index}]")
        sample_id = sample.get("id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError("benchmark sample id must be a non-empty string")
        if sample_id in seen:
            raise ValueError(f"duplicate benchmark sample id: {sample_id}")
        seen.add(sample_id)
        baseline = sample.get("baseline")
        candidate = sample.get("candidate")
        if not isinstance(baseline, str) or not baseline.strip():
            raise ValueError(f"benchmark sample {sample_id} baseline must be a path")
        if not isinstance(candidate, str) or not candidate.strip():
            raise ValueError(f"benchmark sample {sample_id} candidate must be a path")
        result.append(
            {
                "id": sample_id,
                "baseline": baseline,
                "candidate": candidate,
            }
        )
    if not result:
        raise ValueError("benchmark evidence.samples must not be empty")
    return result


def _case_records(bundle: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw_cases = _array(bundle.get("cases"), "benchmark contract_bundle.cases")
    result: Dict[str, Dict[str, Any]] = {}
    for index, raw_case in enumerate(raw_cases):
        case = _object(raw_case, f"benchmark contract_bundle.cases[{index}]")
        sample_id = case.get("id", case.get("sample_id"))
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError("benchmark Contract case id must be a non-empty string")
        if sample_id in result:
            raise ValueError(f"duplicate benchmark Contract case id: {sample_id}")
        contract = case.get("contract", {})
        comparison = case.get("comparison", {})
        if not isinstance(contract, Mapping):
            raise ValueError(f"benchmark Contract {sample_id} must be an object")
        if not isinstance(comparison, Mapping):
            raise ValueError(f"benchmark comparison policy {sample_id} must be an object")
        result[sample_id] = {
            "id": sample_id,
            "contract": deepcopy(dict(contract)),
            "comparison": deepcopy(dict(comparison)),
        }
    if not result:
        raise ValueError("benchmark contract_bundle.cases must not be empty")
    return result


def _comparison_policy(case: Mapping[str, Any]) -> ComparisonPolicy:
    raw = case.get("comparison", {})
    allowed_categories = raw.get("allowed_categories", [])
    allowed_paths = raw.get("allowed_paths", [])
    if not isinstance(allowed_categories, list) or not all(
        isinstance(item, str) for item in allowed_categories
    ):
        raise ValueError("benchmark comparison.allowed_categories must be an array of strings")
    if not isinstance(allowed_paths, list) or not all(
        isinstance(item, str) for item in allowed_paths
    ):
        raise ValueError("benchmark comparison.allowed_paths must be an array of strings")
    contract = ContractPolicy.from_dict(case.get("contract", {}))
    return ComparisonPolicy(
        allowed_categories=set(allowed_categories),
        allowed_paths=set(allowed_paths),
        final_answer_mode=raw.get("final_answer_mode", "exact"),
        result_alignment=raw.get("result_alignment", "call_id"),
        contract=contract,
    )


def _validate_case_inputs(
    base: Path,
    samples: Iterable[Mapping[str, Any]],
    cases: Mapping[str, Mapping[str, Any]],
) -> None:
    sample_ids = {str(sample["id"]) for sample in samples}
    case_ids = set(cases)
    if sample_ids != case_ids:
        missing = sorted(sample_ids - case_ids)
        extra = sorted(case_ids - sample_ids)
        details = []
        if missing:
            details.append("missing Contracts: " + ", ".join(missing))
        if extra:
            details.append("extra Contracts: " + ", ".join(extra))
        raise ValueError("benchmark sample/Contract IDs do not match; " + "; ".join(details))
    for sample in samples:
        sample_id = str(sample["id"])
        for role in ("baseline", "candidate"):
            path = _resolve(base, sample[role], f"benchmark sample {sample_id} {role}")
            raw = _read_json(path, f"benchmark sample {sample_id} {role}")
            try:
                AgentTrace.from_dict(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"benchmark sample {sample_id} {role} is not a valid AgentTrace"
                ) from exc
        _comparison_policy(cases[sample_id])


def _load_context(manifest_path: str | Path) -> Dict[str, Any]:
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest = _read_json(manifest_file, "benchmark manifest")
    manifest = dict(_object(manifest, "benchmark manifest"))
    allowed = {
        "schema_version",
        "benchmark_id",
        "source",
        "split",
        "contract_bundle",
        "evidence",
        "labels",
        "decision_bundle",
        "agent_regression",
    }
    unknown = sorted(set(manifest) - allowed)
    if unknown:
        raise ValueError("unsupported benchmark manifest fields: " + ", ".join(unknown))
    if manifest.get("schema_version") != "0.1":
        raise ValueError("benchmark manifest schema_version must be '0.1'")
    benchmark_id = manifest.get("benchmark_id")
    if not isinstance(benchmark_id, str) or not benchmark_id.strip():
        raise ValueError("benchmark_id must be a non-empty string")
    base = manifest_file.parent
    source = _object(manifest.get("source"), "benchmark.source")
    _validate_revision(source)
    data_descriptor = dict(source)
    data_path = data_descriptor.pop("data_path", None)
    data_sha = _sha256_value(data_descriptor.get("data_sha256"), "benchmark.source.data_sha256")
    source_info: Dict[str, Any] = {
        "repository": source["repository"],
        "revision": source["revision"],
        "data_sha256": data_sha,
    }
    if data_path is not None:
        actual_source = _verify_hashed_file(
            base,
            {"path": data_path, "sha256": data_sha},
            label="benchmark.source.data",
        )
        source_info["data_path"] = actual_source["relative_path"]
    split = _object(manifest.get("split"), "benchmark.split")
    if not isinstance(split.get("name"), str) or not split["name"].strip():
        raise ValueError("benchmark.split.name must be a non-empty string")
    split_info = _verify_hashed_file(base, split, label="benchmark.split.definition")
    contract_descriptor = _object(manifest.get("contract_bundle"), "benchmark.contract_bundle")
    contract_info = _verify_hashed_file(base, contract_descriptor, label="benchmark.contract_bundle")
    evidence_descriptor = _object(manifest.get("evidence"), "benchmark.evidence")
    evidence_info = _verify_hashed_file(base, evidence_descriptor, label="benchmark.evidence")
    labels_descriptor = _object(manifest.get("labels"), "benchmark.labels")
    labels_info = _verify_hashed_file(base, labels_descriptor, label="benchmark.labels")
    agent_info = _object(manifest.get("agent_regression"), "benchmark.agent_regression")
    if not isinstance(agent_info.get("version"), str) or not agent_info["version"].strip():
        raise ValueError("benchmark.agent_regression.version must be a non-empty string")
    if not isinstance(agent_info.get("commit"), str) or not agent_info["commit"].strip():
        raise ValueError("benchmark.agent_regression.commit must be a non-empty string")
    evidence = _object(_read_json(Path(evidence_info["path"]), "benchmark evidence"), "benchmark evidence")
    bundle = _object(_read_json(Path(contract_info["path"]), "benchmark Contract bundle"), "benchmark Contract bundle")
    samples = _sample_records(evidence)
    cases = _case_records(bundle)
    _validate_case_inputs(base, samples, cases)
    decision_descriptor = manifest.get("decision_bundle")
    decision_info = None
    if decision_descriptor is not None:
        decision_info = _verify_hashed_file(
            base,
            _object(decision_descriptor, "benchmark.decision_bundle"),
            label="benchmark.decision_bundle",
        )
    return {
        "manifest": manifest,
        "manifest_path": manifest_file,
        "manifest_sha256": _sha256_file(manifest_file, "benchmark manifest"),
        "base": base,
        "benchmark_id": benchmark_id,
        "source": source_info,
        "split": split_info,
        "contract_bundle": contract_info,
        "evidence": evidence_info,
        "labels": labels_info,
        "agent_regression": dict(agent_info),
        "decision_bundle": decision_info,
        "samples": samples,
        "cases": cases,
    }


def _provenance(context: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "manifest_sha256": context["manifest_sha256"],
        "source": deepcopy(context["source"]),
        "split_sha256": context["split"]["sha256"],
        "contract_bundle_sha256": context["contract_bundle"]["sha256"],
        "evidence_sha256": context["evidence"]["sha256"],
        "labels_sha256": context["labels"]["sha256"],
        "agent_regression": deepcopy(context["agent_regression"]),
    }


def prepare_benchmark(manifest_path: str | Path) -> Dict[str, Any]:
    """Validate all benchmark inputs without making a behavior decision."""
    context = _load_context(manifest_path)
    return {
        "schema_version": "0.1",
        "report_type": "benchmark_preparation",
        "ok": True,
        "benchmark_id": context["benchmark_id"],
        "scope": {
            "sample_count": len(context["samples"]),
            "sample_ids": [sample["id"] for sample in context["samples"]],
            "contract_count": len(context["cases"]),
        },
        "provenance": _provenance(context),
        "decision_boundary": (
            "prepare validates source, split, evidence and Contract hashes; "
            "it does not inspect label meaning"
        ),
    }


def _decision_digest(payload: Mapping[str, Any]) -> str:
    value = deepcopy(dict(payload))
    value.pop("decision_digest", None)
    return _canonical_digest(value)


def decide_benchmark(manifest_path: str | Path) -> Dict[str, Any]:
    """Make per-sample decisions from evidence without reading labels."""
    context = _load_context(manifest_path)
    decisions: List[Dict[str, Any]] = []
    for sample in context["samples"]:
        sample_id = sample["id"]
        baseline = AgentTrace.from_dict(
            _read_json(
                _resolve(context["base"], sample["baseline"], f"benchmark sample {sample_id} baseline"),
                f"benchmark sample {sample_id} baseline",
            )
        )
        candidate = AgentTrace.from_dict(
            _read_json(
                _resolve(context["base"], sample["candidate"], f"benchmark sample {sample_id} candidate"),
                f"benchmark sample {sample_id} candidate",
            )
        )
        report = compare_traces(
            baseline,
            candidate,
            _comparison_policy(context["cases"][sample_id]),
        )
        decisions.append(
            {
                "sample_id": sample_id,
                "status": "pass" if report["passed"] else "block",
                "passed": bool(report["passed"]),
                "difference_count": report["difference_count"],
                "blocking_difference_count": report["blocking_difference_count"],
                "difference_categories": sorted(
                    {str(item.get("category")) for item in report["differences"]}
                ),
                "difference_paths": sorted(
                    {str(item.get("path")) for item in report["differences"]}
                ),
            }
        )
    result: Dict[str, Any] = {
        "schema_version": "0.1",
        "report_type": "benchmark_decisions",
        "ok": True,
        "benchmark_id": context["benchmark_id"],
        "provenance": _provenance(context),
        "scope": {"sample_count": len(decisions)},
        "decisions": decisions,
        "decision_boundary": (
            "decide reads only hashed evidence and Contracts; labels are not loaded "
            "or used to make any decision"
        ),
    }
    result["decision_digest"] = _decision_digest(result)
    return result


def _labels(path: Path) -> Dict[str, bool]:
    raw = _object(_read_json(path, "benchmark labels"), "benchmark labels")
    labels = _array(raw.get("labels"), "benchmark labels.labels")
    result: Dict[str, bool] = {}
    for index, raw_label in enumerate(labels):
        label = _object(raw_label, f"benchmark labels.labels[{index}]")
        sample_id = label.get("sample_id", label.get("id"))
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError("benchmark label sample_id must be a non-empty string")
        if sample_id in result:
            raise ValueError(f"duplicate benchmark label: {sample_id}")
        passed = label.get("passed")
        if not isinstance(passed, bool):
            raise ValueError(f"benchmark label {sample_id}.passed must be boolean")
        result[sample_id] = passed
    if not result:
        raise ValueError("benchmark labels.labels must not be empty")
    return result


def _wilson(successes: int, total: int) -> Dict[str, float] | None:
    interval = wilson_interval(successes, total)
    if interval is None:
        return None
    return {"low": interval["low"], "high": interval["high"]}


def score_benchmark(
    manifest_path: str | Path,
    decisions_path: str | Path,
) -> Dict[str, Any]:
    """Score frozen decisions against labels after fingerprint validation."""
    context = _load_context(manifest_path)
    decisions_file = Path(decisions_path).expanduser().resolve()
    decisions = _object(_read_json(decisions_file, "benchmark decisions"), "benchmark decisions")
    if decisions.get("report_type") != "benchmark_decisions":
        raise ValueError("decisions file must be a benchmark_decisions report")
    if decisions.get("benchmark_id") != context["benchmark_id"]:
        raise ValueError("decisions benchmark_id does not match the manifest")
    if decisions.get("provenance", {}).get("manifest_sha256") != context["manifest_sha256"]:
        raise ValueError("decisions manifest fingerprint does not match the manifest")
    if decisions.get("decision_digest") != _decision_digest(decisions):
        raise ValueError("decisions digest mismatch; the decision file was modified")
    expected_decision = context.get("decision_bundle")
    if expected_decision is not None:
        if decisions_file != Path(expected_decision["path"]):
            raise ValueError("decisions path does not match manifest.decision_bundle.path")
        actual = _sha256_file(decisions_file, "benchmark decisions")
        if actual != expected_decision["sha256"]:
            raise ValueError("benchmark decisions SHA-256 does not match the manifest")
    labels = _labels(Path(context["labels"]["path"]))
    raw_decisions = _array(decisions.get("decisions"), "benchmark decisions.decisions")
    decision_map: Dict[str, Dict[str, Any]] = {}
    for index, raw_decision in enumerate(raw_decisions):
        decision = _object(raw_decision, f"benchmark decisions.decisions[{index}]")
        sample_id = decision.get("sample_id")
        status = decision.get("status")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError("benchmark decision sample_id must be a non-empty string")
        if sample_id in decision_map:
            raise ValueError(f"duplicate benchmark decision: {sample_id}")
        if status not in {"pass", "block", "unsupported"}:
            raise ValueError(f"unsupported benchmark decision status: {status!r}")
        decision_map[sample_id] = dict(decision)
    expected_ids = {sample["id"] for sample in context["samples"]}
    if set(decision_map) != expected_ids:
        raise ValueError("benchmark decisions do not cover exactly the manifest samples")
    valid_ids = {sample_id for sample_id, decision in decision_map.items() if decision["status"] != "unsupported"}
    if valid_ids - set(labels):
        raise ValueError("benchmark labels are missing a decided sample")
    if set(labels) - expected_ids:
        raise ValueError("benchmark labels contain an unknown sample")

    true_pass = true_block = false_alarm = missed_failure = 0
    for sample_id in sorted(valid_ids):
        decision_passed = decision_map[sample_id]["status"] == "pass"
        oracle_passed = labels[sample_id]
        if decision_passed and oracle_passed:
            true_pass += 1
        elif not decision_passed and not oracle_passed:
            true_block += 1
        elif not decision_passed and oracle_passed:
            false_alarm += 1
        else:
            missed_failure += 1
    evaluated = true_pass + true_block + false_alarm + missed_failure
    oracle_passes = true_pass + false_alarm
    oracle_failures = true_block + missed_failure
    rates = {
        "accuracy": _rate(true_pass + true_block, evaluated),
        "failure_precision": _rate(true_block, true_block + false_alarm),
        "failure_recall": _rate(true_block, oracle_failures),
        "false_alarm_rate": _rate(false_alarm, oracle_passes),
        "missed_failure_rate": _rate(missed_failure, oracle_failures),
    }
    result: Dict[str, Any] = {
        "schema_version": "0.1",
        "report_type": "benchmark_score",
        "ok": True,
        "benchmark_id": context["benchmark_id"],
        "scope": {
            "total_samples": len(expected_ids),
            "evaluated_samples": evaluated,
            "unsupported": len(expected_ids - valid_ids),
            "unsupported_sample_ids": sorted(expected_ids - valid_ids),
        },
        "confusion_matrix": {
            "true_pass": true_pass,
            "true_block": true_block,
            "false_alarm": false_alarm,
            "missed_failure": missed_failure,
        },
        "metrics": rates,
        "wilson_95": {
            key: _wilson(value, denominator)
            for key, value, denominator in (
                ("accuracy", true_pass + true_block, evaluated),
                ("failure_precision", true_block, true_block + false_alarm),
                ("failure_recall", true_block, oracle_failures),
                ("false_alarm_rate", false_alarm, oracle_passes),
                ("missed_failure_rate", missed_failure, oracle_failures),
            )
        },
        "provenance": {
            **_provenance(context),
            "decisions_sha256": _sha256_file(decisions_file, "benchmark decisions"),
            "decision_digest": decisions["decision_digest"],
            "labels_sha256": context["labels"]["sha256"],
        },
        "decision_boundary": (
            "score reads labels only after validating the manifest, decision digest, "
            "sample coverage and all input hashes"
        ),
    }
    result["report_digest"] = _canonical_digest(result)
    return result


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


__all__ = ["decide_benchmark", "prepare_benchmark", "score_benchmark"]
