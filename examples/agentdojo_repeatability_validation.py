"""Prove that a pinned AgentDojo decision is reproducible across repeats."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Dict, Mapping


ROOT = Path(__file__).resolve().parents[1]
MATRIX_SCRIPT = ROOT / "examples" / "agentdojo_matrix_validation.py"


def _load_matrix_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "agentdojo_matrix_validation_for_repeatability", MATRIX_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load matrix validator: {MATRIX_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATRIX = _load_matrix_module()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_report(path: Path, value: Mapping[str, Any]) -> Dict[str, Any]:
    safe = dict(value)
    safe.pop("report_sha256", None)
    safe["report_sha256"] = hashlib.sha256(
        json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return safe


def _snapshot(run_root: Path) -> Dict[str, Any]:
    report_path = run_root / "report.json"
    report = _read_json(report_path)
    case_reports = {}
    for path in sorted((run_root / "cases").glob("*.report.json")):
        case_reports[path.name] = _read_json(path).get("report_sha256")
    traces = {}
    for path in sorted((run_root / "traces").glob("*.trace.json")):
        traces[path.name] = _sha256_file(path)
    return {
        "aggregate_report_sha256": report.get("report_sha256"),
        "case_report_sha256": case_reports,
        "trace_sha256": traces,
        "case_count": report.get("case_count"),
        "passed_case_count": report.get("passed_case_count"),
        "gate_passed": report.get("gate", {}).get("passed"),
    }


def run(args: argparse.Namespace) -> int:
    if args.repeats < 2:
        raise ValueError("--repeats must be at least 2")
    if args.repeats > 100:
        raise ValueError("--repeats must not exceed 100")

    snapshots = []
    for index in range(1, args.repeats + 1):
        run_root = args.out.parent / "runs" / str(index)
        validator_args = argparse.Namespace(
            manifest=args.manifest,
            results_dir=args.results_dir,
            out=run_root / "report.json",
            trace_dir=run_root / "traces",
        )
        exit_code = MATRIX.run(validator_args)
        if exit_code != 0:
            raise ValueError(f"matrix gate failed during repeat {index}")
        snapshots.append(_snapshot(run_root))

    first = snapshots[0]
    stable = all(snapshot == first for snapshot in snapshots[1:])
    manifest = _read_json(args.manifest)
    aggregate = {
        "schema_version": "0.1",
        "report_type": "agentdojo_repeatability_validation",
        "run_count": args.repeats,
        "manifest_sha256": _sha256_file(args.manifest),
        "revision": manifest.get("revision"),
        "stable": stable,
        "runs": snapshots,
        "gate": {
            "passed": stable and all(snapshot["gate_passed"] for snapshot in snapshots),
            "checks": {
                "minimum_repeats": args.repeats >= 2,
                "all_matrix_gates_passed": all(snapshot["gate_passed"] for snapshot in snapshots),
                "aggregate_reports_stable": all(
                    snapshot["aggregate_report_sha256"] == first["aggregate_report_sha256"]
                    for snapshot in snapshots
                ),
                "case_reports_stable": all(
                    snapshot["case_report_sha256"] == first["case_report_sha256"]
                    for snapshot in snapshots
                ),
                "traces_stable": all(
                    snapshot["trace_sha256"] == first["trace_sha256"]
                    for snapshot in snapshots
                ),
            },
        },
        "limitations": [
            "This repeats decisions over pinned exported inputs; it is not a stochastic online model study.",
            "Stable hashes demonstrate deterministic artifact generation, not universal model reliability.",
        ],
    }
    safe = _write_report(args.out, aggregate)
    print(
        json.dumps(
            {
                "run_count": safe["run_count"],
                "stable": safe["stable"],
                "gate_passed": safe["gate"]["passed"],
                "manifest_sha256": safe["manifest_sha256"],
                "report": str(args.out),
            },
            ensure_ascii=False,
        )
    )
    return 0 if safe["gate"]["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"AgentDojo repeatability validation input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
