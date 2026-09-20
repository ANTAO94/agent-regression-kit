"""Create a small recorded sampling-study bundle for the CLI example."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_regression import canonical_sha256


ROOT = Path(__file__).resolve().parents[2]


def _write_trace(source: Path, destination: Path, run_id: str) -> None:
    trace = json.loads(source.read_text(encoding="utf-8"))
    trace["run_id"] = run_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, help="directory for the study bundle")
    parser.add_argument("--provider", default="fixture-provider")
    parser.add_argument("--model", default="fixture-model-v1")
    args = parser.parse_args()

    output = Path(args.out_dir).expanduser().resolve()
    baseline_source = ROOT / "baselines/order-123.trace.json"
    baseline = output / "baseline.trace.json"
    _write_trace(baseline_source, baseline, "order-123-baseline")
    run_paths = []
    for ordinal in (1, 2):
        run_id = f"order-123-study-{ordinal}"
        path = output / "runs" / f"run-{ordinal}.trace.json"
        _write_trace(baseline_source, path, run_id)
        run_paths.append({"id": run_id, "trace": str(path.relative_to(output))})

    manifest = {
        "schema_version": "0.1",
        "study_id": "order-123-demo-sampling",
        "baseline": str(baseline.relative_to(output)),
        "runs": run_paths,
        "provenance": {
            "provider": args.provider,
            "model": args.model,
            "adapter": "recorded-trace-import",
            "study_id": "order-123-demo-sampling",
            "input_sha256": canonical_sha256({"request": "查询订单 123"}),
            "tool_schema_sha256": canonical_sha256(
                {"tools": ["get_order"], "protocol": "mcp-fixture"}
            ),
            "dataset_revision": "local-fixture-v1",
            "parameters": {"temperature": 0.0, "seed": 7},
        },
        "comparison_policy": {
            "final_answer_mode": "claims-only",
            "contract": {
                "required_claims": ["final_answer.claims.order_status"],
                "must_call": [
                    {"tool": "get_order", "arguments": {"order_id": "123"}}
                ],
                "must_not_call": [{"tool": "refund_order"}],
                "max_steps": 1,
            },
        },
        "policy": {"min_runs": 2},
    }
    manifest_path = output / "study.json"
    output.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
