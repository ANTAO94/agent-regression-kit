"""Project scaffolding for first-time Agent Regression Kit users."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


_FILES: Dict[str, str] = {
    ".agent-regression/config.json": json.dumps(
        {
            "baseline": "baselines/my-agent.trace.json",
            "candidate": "work/my-agent.trace.json",
            "report": "outputs/my-agent.junit.xml",
        },
        indent=2,
    )
    + "\n",
    "baselines/README.md": """# Baselines

Commit reviewed AgentTrace files here. A baseline is the expected behavior
against which pull-request candidate traces are compared. Update it explicitly
after reviewing a deliberate behavior change; CI never overwrites it.
""",
    "scripts/record_agent.py": '''"""Generate a candidate AgentTrace for CI.

Replace ExampleAgent.run with your Agent integration. Keep tool calls routed
through context.call_tool and finish through context.final_answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_regression import record_mcp_run


class ExampleAgent:
    identity = {"name": "my-agent", "version": "0.1.0"}

    def run(self, request, context):
        order_id = str(request).rsplit(" ", 1)[-1]
        order = context.call_tool("get_order", {"order_id": order_id})
        context.final_answer(
            f"Order {order_id} status: {order['status']}",
            {"order_id": order_id, "order_status": order["status"]},
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="work/my-agent.trace.json")
    args = parser.parse_args()
    trace = record_mcp_run(
        ExampleAgent(),
        "lookup order 123",
        [sys.executable, "-m", "agent_regression.fixtures.mcp_stdio_server"],
        run_id="my-agent-123",
    )
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2) + "\\n",
        encoding="utf-8",
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    ".github/workflows/agent-regression.yml": '''name: agent-regression

on:
  pull_request:

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install Agent Regression Kit
        run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git"
      - name: Record candidate trace
        run: python scripts/record_agent.py --out work/my-agent.trace.json
      - name: Compare with reviewed baseline
        uses: ANTAO94/agent-regression-kit/.github/actions/agent-regression@main
        with:
          baseline: baselines/my-agent.trace.json
          candidate: work/my-agent.trace.json
          report: outputs/my-agent.junit.xml
      - name: Upload regression report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: agent-regression-report
          path: outputs/my-agent.junit.xml
''',
}


def initialize_project(root: Path, *, force: bool = False) -> Dict[str, List[str]]:
    """Create a first-use project layout without overwriting by default."""
    created: List[str] = []
    skipped: List[str] = []
    for relative, content in _FILES.items():
        destination = root / relative
        if destination.exists() and not force:
            skipped.append(relative)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        created.append(relative)
    return {"created": created, "skipped": skipped}
