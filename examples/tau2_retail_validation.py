"""Validate Agent Regression Kit against pinned tau2-bench retail results."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, Mapping

from agent_regression import evaluate_tau2_retail_results, trace_from_tau2_simulation


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "examples" / "tau2-retail" / "source.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bind_results_to_source(results_path: Path, source: Mapping[str, Any]) -> Dict[str, Any]:
    """Fail closed when a result file does not match its source manifest.

    The validator historically accepted any JSON file together with the default
    retail manifest.  That made it possible to produce a report whose metrics
    came from one model while its provenance described another model.  A
    manifest with ``sha256`` is now an explicit binding between the downloaded
    result bytes and the report metadata.
    """
    observed = sha256_file(results_path)
    expected = source.get("sha256")
    if expected is not None:
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("source manifest sha256 must be a 64-character hex string")
        try:
            expected_normalized = expected.lower()
            int(expected_normalized, 16)
        except ValueError as exc:
            raise ValueError("source manifest sha256 must be a 64-character hex string") from exc
        if observed != expected_normalized:
            raise ValueError(
                "results SHA-256 does not match source manifest: "
                f"expected {expected_normalized}, observed {observed}"
            )
    return {
        "results_file": results_path.name,
        "results_sha256": observed,
        "manifest_sha256": expected.lower() if isinstance(expected, str) else None,
    }


def export_sample_traces(
    payload: Mapping[str, Any],
    report: Mapping[str, Any],
    directory: Path,
    source: Mapping[str, Any],
) -> None:
    tasks = {str(task["id"]): task for task in payload["tasks"]}
    simulations = {str(item["id"]): item for item in payload["simulations"]}
    agent_info = payload.get("info", {}).get("agent_info", {})
    identity = {
        "name": str(agent_info.get("implementation") or "tau2-published-agent"),
        "model": str(agent_info.get("llm") or "unknown"),
        "framework": "tau2-bench",
    }
    for classification, samples in report["samples"].items():
        if not samples:
            continue
        sample = samples[0]
        simulation = simulations[sample["simulation_id"]]
        trace = trace_from_tau2_simulation(
            simulation,
            tasks[str(simulation["task_id"])],
            source=source,
            agent=identity,
        )
        write_json(directory / f"{classification}.trace.json", trace.to_dict())


def run(args: argparse.Namespace) -> int:
    payload = read_json(args.results)
    source = read_json(args.source_manifest)
    input_provenance = bind_results_to_source(args.results, source)
    report = evaluate_tau2_retail_results(
        payload,
        source=source,
        sample_limit=args.sample_limit,
    )
    scope = report["scope"]
    matrix = report["confusion_matrix"]
    metrics = report["metrics"]
    checks = {
        "eligible_write_scenarios": scope["eligible_write_scenarios"] >= args.min_eligible,
        "oracle_failures": (
            matrix["true_block"] + matrix["missed_failure"] >= args.min_failures
        ),
        "failure_recall": metrics["failure_recall"] is not None
        and metrics["failure_recall"] >= args.min_failure_recall,
        "false_alarm_rate": metrics["false_alarm_rate"] is not None
        and metrics["false_alarm_rate"] <= args.max_false_alarm_rate,
        "missed_failure_rate": metrics["missed_failure_rate"] is not None
        and metrics["missed_failure_rate"] <= args.max_missed_failure_rate,
    }
    report["gate"] = {
        "passed": all(checks.values()),
        "checks": checks,
        "thresholds": {
            "min_eligible": args.min_eligible,
            "min_failures": args.min_failures,
            "min_failure_recall": args.min_failure_recall,
            "max_false_alarm_rate": args.max_false_alarm_rate,
            "max_missed_failure_rate": args.max_missed_failure_rate,
        },
    }
    report["provenance"] = {
        "results": input_provenance,
        "source_manifest": str(args.source_manifest),
        "source_manifest_sha256": sha256_file(args.source_manifest),
    }
    write_json(args.out, report)
    if args.traces_dir is not None:
        export_sample_traces(payload, report, args.traces_dir, source)
    print(
        json.dumps(
            {
                "eligible": scope["eligible_write_scenarios"],
                "oracle_failures": matrix["true_block"] + matrix["missed_failure"],
                **matrix,
                **metrics,
                "results_sha256": input_provenance["results_sha256"],
                "gate_passed": report["gate"]["passed"],
                "report": str(args.out),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["gate"]["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--traces-dir", type=Path)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--min-eligible", type=int, default=400)
    parser.add_argument("--min-failures", type=int, default=50)
    parser.add_argument("--min-failure-recall", type=float, default=0.99)
    parser.add_argument("--max-false-alarm-rate", type=float, default=0.06)
    parser.add_argument("--max-missed-failure-rate", type=float, default=0.0)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"tau2 validation input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
