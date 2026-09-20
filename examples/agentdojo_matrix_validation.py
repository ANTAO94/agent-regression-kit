"""Validate a pinned matrix of exported AgentDojo runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Mapping

from agent_regression import (
    DEFAULT_REDACTION_POLICY,
    evaluate_agentdojo_run,
    trace_from_agentdojo_run,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "examples" / "agentdojo" / "matrix.json"
CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_value(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _immutable_revision(value: Any) -> str:
    revision = _string(value, "manifest.revision")
    if revision.lower() in {"main", "master", "latest", "head", "trunk"}:
        raise ValueError("manifest.revision must not be a moving branch name")
    return revision


def _cases(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("manifest.cases must be a non-empty array")
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for index, raw_case in enumerate(raw_cases):
        case = _object(raw_case, f"manifest.cases[{index}]")
        case_id = _string(case.get("case_id"), f"manifest.cases[{index}].case_id")
        if not CASE_ID_RE.fullmatch(case_id):
            raise ValueError(f"invalid case_id: {case_id}")
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        result.append(case)
    return result


def _validate_case_metadata(run: Mapping[str, Any], case: Mapping[str, Any]) -> None:
    for key in ("suite_name", "pipeline_name", "user_task_id", "injection_task_id", "attack_type"):
        if key in case and run.get(key) != case[key]:
            raise ValueError(
                f"AgentDojo result metadata mismatch for {key}: "
                f"expected {case[key]!r}, observed {run.get(key)!r}"
            )


def _has_key(value: Any, key: str) -> bool:
    if isinstance(value, Mapping):
        return key in value or any(_has_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_has_key(item, key) for item in value)
    return False


def _label_checks(report: Mapping[str, Any], case: Mapping[str, Any]) -> Dict[str, bool]:
    expected = _object(case.get("expected_oracle", {}), "case.expected_oracle")
    observed = _object(report.get("external_oracle", {}), "report.external_oracle")
    checks: Dict[str, bool] = {}
    for key in ("utility", "security"):
        if key in expected:
            if not isinstance(expected[key], bool):
                raise ValueError(f"case.expected_oracle.{key} must be boolean")
            checks[key] = observed.get(key) == expected[key]
    if not checks:
        raise ValueError("case.expected_oracle must declare utility or security")
    return checks


def _redacted_with_hash(value: Mapping[str, Any]) -> Dict[str, Any]:
    safe = dict(DEFAULT_REDACTION_POLICY.redact(value))
    safe.pop("report_sha256", None)
    safe["report_sha256"] = _sha256_value(safe)
    return safe


def _write_json(path: Path, value: Mapping[str, Any]) -> Dict[str, Any]:
    safe = _redacted_with_hash(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return safe


def run(args: argparse.Namespace) -> int:
    manifest = _object(read_json(args.manifest), "matrix manifest")
    revision = _immutable_revision(manifest.get("revision"))
    repository = _string(manifest.get("repository"), "manifest.repository")
    manifest_cases = _cases(manifest)
    contract_provenance = manifest.get("contract_provenance")
    contract_hash_required = contract_provenance is not None
    if contract_hash_required:
        provenance = _object(contract_provenance, "manifest.contract_provenance")
        if provenance.get("scheme") != "sha256-canonical-json":
            raise ValueError(
                "manifest.contract_provenance.scheme must be 'sha256-canonical-json'"
            )
        if provenance.get("frozen_before_oracle") is not True:
            raise ValueError(
                "manifest.contract_provenance.frozen_before_oracle must be true"
            )
    manifest_sha = sha256_file(args.manifest)
    summaries: list[Dict[str, Any]] = []

    for case in manifest_cases:
        case_id = _string(case.get("case_id"), "case.case_id")
        result_file = _string(case.get("result_file"), f"case {case_id}.result_file")
        relative_result = Path(result_file)
        if relative_result.is_absolute() or ".." in relative_result.parts:
            raise ValueError(f"case {case_id}.result_file must stay below results-dir")
        results_path = args.results_dir / result_file
        if not results_path.is_file():
            raise ValueError(f"missing result file for {case_id}: {results_path}")
        expected_sha = _string(case.get("sha256"), f"case {case_id}.sha256").lower()
        if len(expected_sha) != 64:
            raise ValueError(f"case {case_id}.sha256 must be a 64-character SHA-256 value")
        actual_sha = sha256_file(results_path)
        if actual_sha != expected_sha:
            raise ValueError(
                f"AgentDojo result SHA-256 mismatch for {case_id}: "
                f"expected {expected_sha}, observed {actual_sha}"
            )

        run_data = _object(read_json(results_path), f"AgentDojo result {case_id}")
        _validate_case_metadata(run_data, case)
        dataset_path = _string(case.get("dataset_path"), f"case {case_id}.dataset_path")
        download_url = _string(case.get("download_url"), f"case {case_id}.download_url")
        expected_url_suffix = f"/{revision}/{dataset_path}"
        if not download_url.endswith(expected_url_suffix):
            raise ValueError(
                f"case {case_id}.download_url must point to the pinned revision and dataset_path"
            )
        source = {
            "repository": repository,
            "revision": revision,
            "dataset_path": dataset_path,
            "result_sha256": actual_sha,
            "case_id": case_id,
        }
        contract = _object(case.get("contract"), f"case {case_id}.contract")
        declared_contract_sha = case.get("contract_sha256")
        if contract_hash_required and declared_contract_sha is None:
            raise ValueError(f"case {case_id}.contract_sha256 is required by manifest")
        contract_hash_check = True
        if declared_contract_sha is not None:
            declared_contract_sha = _string(
                declared_contract_sha, f"case {case_id}.contract_sha256"
            ).lower()
            if len(declared_contract_sha) != 64:
                raise ValueError(
                    f"case {case_id}.contract_sha256 must be a 64-character SHA-256 value"
                )
            actual_contract_sha = _sha256_value(contract)
            contract_hash_check = actual_contract_sha == declared_contract_sha
            if not contract_hash_check:
                raise ValueError(
                    f"Contract SHA-256 mismatch for {case_id}: "
                    f"expected {declared_contract_sha}, observed {actual_contract_sha}"
                )
        report = evaluate_agentdojo_run(
            run_data,
            contract,
            source=source,
        )
        trace = trace_from_agentdojo_run(run_data, source=source)
        expected_contract_passed = case.get("expected_contract_passed", True)
        if not isinstance(expected_contract_passed, bool):
            raise ValueError(f"case {case_id}.expected_contract_passed must be boolean")
        label_checks = _label_checks(report, case)
        boundary_checks = {
            "external_labels_not_in_trace": not any(
                _has_key(trace.to_dict(), key) for key in ("utility", "security")
            )
        }
        checks = {
            "result_sha256": True,
            "metadata": True,
            "contract_expectation": report["contract_passed"] == expected_contract_passed,
            "contract_provenance": contract_hash_check,
            "external_oracle": all(label_checks.values()),
            **boundary_checks,
        }
        report["matrix_case_id"] = case_id
        report["expected_contract_passed"] = expected_contract_passed
        report["contract_outcome_match"] = report["contract_passed"] == expected_contract_passed
        report["contract_sha256"] = declared_contract_sha
        report["contract_provenance"] = contract_provenance
        report["provenance"] = {
            **report["provenance"],
            "matrix_manifest": str(args.manifest),
            "matrix_manifest_sha256": manifest_sha,
            "result_file": result_file,
            "result_sha256": actual_sha,
            "revision": revision,
        }
        report["gate"] = {"passed": all(checks.values()), "checks": checks}
        report_path = args.out.parent / "cases" / f"{case_id}.report.json"
        trace_path = args.trace_dir / f"{case_id}.trace.json"
        safe_report = _write_json(report_path, report)
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(DEFAULT_REDACTION_POLICY.redact(trace.to_dict()), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        summaries.append(
            {
                "case_id": case_id,
                "suite_name": run_data.get("suite_name"),
                "user_task_id": run_data.get("user_task_id"),
                "injection_task_id": run_data.get("injection_task_id"),
                "attack_type": run_data.get("attack_type"),
                "tool_names": report["trace_summary"]["tool_names"],
                "external_oracle": report["external_oracle"],
                "contract_passed": report["contract_passed"],
                "expected_contract_passed": expected_contract_passed,
                "contract_outcome_match": safe_report["contract_outcome_match"],
                "contract_sha256": safe_report["contract_sha256"],
                "gate_passed": safe_report["gate"]["passed"],
                "checks": safe_report["gate"]["checks"],
                "result_sha256": actual_sha,
                "report": str(report_path.relative_to(args.out.parent)),
                "trace": str(trace_path.relative_to(args.trace_dir.parent)),
            }
        )

    aggregate_checks = {
        "non_empty_matrix": bool(summaries),
        "all_cases_passed": all(item["gate_passed"] for item in summaries),
        "all_contract_expectations_match": all(
            item["contract_outcome_match"] for item in summaries
        ),
        "all_contract_provenance_bound": all(
            item["checks"]["contract_provenance"] for item in summaries
        ),
        "all_source_hashes_checked": all(item["checks"]["result_sha256"] for item in summaries),
        "all_external_oracles_match": all(item["checks"]["external_oracle"] for item in summaries),
        "all_trace_boundaries_closed": all(
            item["checks"]["external_labels_not_in_trace"] for item in summaries
        ),
    }
    aggregate = {
        "schema_version": "0.1",
        "report_type": "agentdojo_matrix_validation",
        "case_count": len(summaries),
        "passed_case_count": sum(1 for item in summaries if item["gate_passed"]),
        "repository": repository,
        "revision": revision,
        "manifest_sha256": manifest_sha,
        "cases": summaries,
        "gate": {"passed": all(aggregate_checks.values()), "checks": aggregate_checks},
        "limitations": [
            "This is a pinned exported-run matrix, not a full AgentDojo rerun.",
            "Contracts are manually reviewed per case and are not derived from utility/security labels.",
            "The matrix does not establish universal security or cross-model generalization.",
        ],
    }
    safe_aggregate = _write_json(args.out, aggregate)
    print(
        json.dumps(
            {
                "case_count": safe_aggregate["case_count"],
                "passed_case_count": safe_aggregate["passed_case_count"],
                "gate_passed": safe_aggregate["gate"]["passed"],
                "manifest_sha256": manifest_sha,
                "report": str(args.out),
            },
            ensure_ascii=False,
        )
    )
    return 0 if safe_aggregate["gate"]["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--trace-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"AgentDojo matrix validation input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
