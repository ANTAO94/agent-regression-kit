"""Record one deterministic local MCP run and write AgentTrace JSON."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_regression import ScriptedAgentAdapter, record_mcp_run  # noqa: E402


def main() -> int:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "outputs/mcp-order-123.trace.json"
    adapter = ScriptedAgentAdapter(
        {"name": "toy-mcp-agent", "version": "1.0.0"},
        [
            {"type": "tool_call", "tool": "get_order", "arguments": {"order_id": "123"}},
            {
                "type": "final_answer",
                "text": "订单 123 尚未发货。",
                "claims": {"order_status": "not_shipped"},
            },
        ],
    )
    trace = record_mcp_run(
        adapter,
        "查询订单 123",
        [sys.executable, str(ROOT / "src/agent_regression/fixtures/mcp_stdio_server.py")],
        run_id="mcp-order-123",
        metadata={"fixture": "project-owned-mcp-stdio"},
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
