"""Evaluate a task-disjoint telecom split without using labels to select it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from agent_regression import evaluate_tau2_telecom_results, split_tau2_payload_by_task

# Keep the validator runnable both as ``python examples/...`` and when loaded
# by the repository's script tests.
EXAMPLES_DIR = str(Path(__file__).resolve().parent)
if EXAMPLES_DIR not in sys.path:
    sys.path.insert(0, EXAMPLES_DIR)

from tau2_telecom_validation import (
    bind_results_to_source,
    export_sample_traces,
    read_json,
    sha256_file,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "examples" / "tau2-telecom" / "source.json"
DEFAULT_SPLIT = ROOT / "examples" / "tau2-telecom" / "task-split.json"


def verify_split_definition(
    provenance: Mapping[str, Any], definition: Mapping[str, Any]
) -> None:
    """Fail closed if the checked-in split no longer matches the payload IDs."""

    fields = (
        "strategy",
        "holdout_modulus",
        "holdout_bucket_limit",
        "task_count",
        "all_task_ids_sha256",
        "calibration_task_count",
        "calibration_task_ids_sha256",
        "holdout_task_count",
        "holdout_task_ids_sha256",
    )
    for field in fields:
        if provenance.get(field) != definition.get(field):
            raise ValueError(
                f"task split definition mismatch for {field}: "
                f"expected {definition.get(field)!r}, observed {provenance.get(field)!r}"
            )


def run(args: argparse.Namespace) -> int:
    payload = read_json(args.results)
    source = read_json(args.source_manifest)
    split_definition = read_json(args.split_definition)
    input_provenance = bind_results_to_source(args.results, source)
    split = split_tau2_payload_by_task(
        payload,
        holdout_modulus=split_definition["holdout_modulus"],
        holdout_bucket_limit=split_definition["holdout_bucket_limit"],
    )
    verify_split_definition(split["provenance"], split_definition)
    if args.partition not in {"calibration", "holdout"}:
        raise ValueError("partition must be calibration or holdout")
    selected_payload = split[args.partition]
    report_source = {
        **source,
        "task_split": {
            "name": split_definition.get("name"),
            "partition": args.partition,
            "definition_sha256": sha256_file(args.split_definition),
        },
    }
    report = evaluate_tau2_telecom_results(
        selected_payload,
        source=report_source,
        sample_limit=args.sample_limit,
    )
    scope = report["scope"]
    matrix = report["confusion_matrix"]
    metrics = report["metrics"]
    checks = {
        "eligible_write_scenarios": scope["eligible_write_scenarios"] >= args.min_eligible,
        "oracle_failures": matrix["true_block"] + matrix["missed_failure"] >= args.min_failures,
        "failure_recall": metrics["failure_recall"] is not None
        and metrics["failure_recall"] >= args.min_failure_recall,
        "false_alarm_rate": metrics["false_alarm_rate"] is not None
        and metrics["false_alarm_rate"] <= args.max_false_alarm_rate,
        "missed_failure_rate": metrics["missed_failure_rate"] is not None
        and metrics["missed_failure_rate"] <= args.max_missed_failure_rate,
    }
    report["split"] = {
        **split["provenance"],
        "definition_name": split_definition.get("name"),
        "definition_sha256": sha256_file(args.split_definition),
        "partition": args.partition,
        "label_boundary": (
            "partition selection used task IDs and SHA-256 only; reward labels "
            "were not used to select the split"
        ),
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
        "split_definition": str(args.split_definition),
        "split_definition_sha256": sha256_file(args.split_definition),
    }
    write_json(args.out, report)
    if args.traces_dir is not None:
        export_sample_traces(selected_payload, report, args.traces_dir, report_source)
    print(
        json.dumps(
            {
                "domain": "telecom",
                "partition": args.partition,
                "eligible": scope["eligible_write_scenarios"],
                "excluded": scope["excluded_without_write_action"],
                "oracle_failures": matrix["true_block"] + matrix["missed_failure"],
                **matrix,
                **metrics,
                "results_sha256": input_provenance["results_sha256"],
                "split_definition_sha256": report["split"]["definition_sha256"],
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
    parser.add_argument("--split-definition", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--partition", choices=("calibration", "holdout"), default="holdout")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--traces-dir", type=Path)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--min-eligible", type=int, default=80)
    parser.add_argument("--min-failures", type=int, default=30)
    parser.add_argument("--min-failure-recall", type=float, default=0.99)
    parser.add_argument("--max-false-alarm-rate", type=float, default=0.10)
    parser.add_argument("--max-missed-failure-rate", type=float, default=0.0)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"tau2 telecom holdout validation input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
