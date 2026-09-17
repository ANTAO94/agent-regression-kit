"""Record and compare a rule-driven Agent against controlled regressions."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_regression import (  # noqa: E402
    PARAMETER_REGRESSION,
    RESULT_MISREAD,
    RuleBasedOrderAgentAdapter,
    compare_traces,
    record_mcp_run,
    replay_trace,
)


SERVER_COMMAND = [
    sys.executable,
    str(ROOT / "src/agent_regression/fixtures/mcp_stdio_server.py"),
]


def record(behavior: str):
    return record_mcp_run(
        RuleBasedOrderAgentAdapter(behavior),
        "查询订单 123",
        SERVER_COMMAND,
        run_id=f"rule-agent-{behavior}",
    )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    baseline = record("normal")
    parameter_candidate = record(PARAMETER_REGRESSION)
    misread_candidate = record(RESULT_MISREAD)

    write_json(ROOT / "outputs/rule-agent-baseline.trace.json", baseline.to_dict())
    write_json(ROOT / "outputs/rule-agent-baseline.replay.json", replay_trace(baseline))
    write_json(
        ROOT / "outputs/rule-agent-parameter-regression.diff.json",
        compare_traces(baseline, parameter_candidate),
    )
    write_json(
        ROOT / "outputs/rule-agent-result-misread.diff.json",
        compare_traces(baseline, misread_candidate),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
