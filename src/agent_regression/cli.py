from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Dict

from .adapters import ScriptedAgentAdapter
from .compare import ComparisonPolicy, compare_traces
from .compat import run_compatibility_smoke
from .model import AgentTrace, TraceValidationError
from .mcp import (
    McpTransportError,
    StdioMcpClient,
    StreamableHttpMcpClient,
    record_mcp_http_run,
    record_mcp_run,
)
from .record import FixtureTools, record_run
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy
from .reports import render_junit
from .replay import replay_trace


VERSION = "1.1.0"


def _read_json(path: str) -> Dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_output(value: Dict[str, Any], out: str | None = None) -> None:
    safe_value = DEFAULT_REDACTION_POLICY.redact(value)
    rendered = json.dumps(safe_value, ensure_ascii=False, indent=2) + "\n"
    if out:
        output_path = Path(out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def _write_text(value: str, out: str | None = None) -> None:
    if out:
        output_path = Path(out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(value, encoding="utf-8")
    print(value, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-regression")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="record a deterministic scenario")
    record.add_argument("--scenario", required=True)
    record.add_argument("--out", required=True)
    record.add_argument(
        "--secret-value", action="append", default=[], help="literal secret value to redact; repeatable"
    )

    mcp_record = subparsers.add_parser(
        "mcp-record", help="record a scenario through an MCP stdio server"
    )
    mcp_record.add_argument("--scenario", required=True)
    mcp_record.add_argument("--out", required=True)
    mcp_record.add_argument(
        "--server-command",
        help="shell-style command string; defaults to the project-owned fixture",
    )
    mcp_record.add_argument("--timeout", type=float, default=5.0)
    mcp_record.add_argument(
        "--secret-value", action="append", default=[], help="literal secret value to redact; repeatable"
    )

    mcp_http_record = subparsers.add_parser(
        "mcp-http-record", help="record a scenario through an MCP Streamable HTTP server"
    )
    mcp_http_record.add_argument("--scenario", required=True)
    mcp_http_record.add_argument("--url", required=True)
    mcp_http_record.add_argument("--out", required=True)
    mcp_http_record.add_argument("--timeout", type=float, default=5.0)
    mcp_http_record.add_argument(
        "--secret-value", action="append", default=[], help="literal secret value to redact; repeatable"
    )

    smoke = subparsers.add_parser(
        "mcp-smoke", help="run non-mutating compatibility checks against an MCP server"
    )
    smoke_transport = smoke.add_mutually_exclusive_group(required=True)
    smoke_transport.add_argument(
        "--server-command", help="shell-style command for an MCP stdio server"
    )
    smoke_transport.add_argument("--url", help="MCP Streamable HTTP endpoint")
    smoke.add_argument(
        "--stdio-framing",
        choices=["newline", "content-length"],
        default="newline",
        help="stdio framing for --server-command (default: newline)",
    )
    smoke.add_argument("--timeout", type=float, default=5.0)
    smoke.add_argument("--out")

    replay = subparsers.add_parser("replay", help="validate and inspect recorded evidence")
    replay.add_argument("--trace", required=True)
    replay.add_argument("--out")

    validate = subparsers.add_parser("validate", help="validate an AgentTrace document")
    validate.add_argument("--trace", required=True)

    compare = subparsers.add_parser("compare", help="compare candidate evidence to a baseline")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--out")
    compare.add_argument("--format", choices=["json", "junit"], default="json")
    compare.add_argument(
        "--secret-value", action="append", default=[], help="literal secret value to redact; repeatable"
    )
    compare.add_argument(
        "--allow-category",
        action="append",
        default=[],
        help="difference category that should not fail the comparison; repeatable",
    )

    baseline = subparsers.add_parser("baseline", help="manage validated baseline traces")
    baseline_actions = baseline.add_subparsers(dest="baseline_action", required=True)
    accept = baseline_actions.add_parser("accept", help="validate and store a baseline trace")
    accept.add_argument("--trace", required=True)
    accept.add_argument("--out", required=True)
    show = baseline_actions.add_parser("show", help="validate and summarize a baseline trace")
    show.add_argument("--baseline", required=True)
    compare.add_argument(
        "--allow-path",
        action="append",
        default=[],
        help="exact difference path that should not fail the comparison; repeatable",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    redaction_policy = RedactionPolicy(
        secret_values=tuple(getattr(args, "secret_value", []))
    )
    try:
        if args.command in {"record", "mcp-record", "mcp-http-record"}:
            scenario = _read_json(args.scenario)
            adapter = ScriptedAgentAdapter(scenario["agent"], scenario["plan"])
            if args.command == "record":
                trace = record_run(
                    adapter,
                    scenario.get("input"),
                    FixtureTools(scenario.get("tools", {})),
                    run_id=scenario["run_id"],
                    metadata=scenario.get("metadata"),
                    redaction_policy=redaction_policy,
                )
            elif args.command == "mcp-record":
                command = (
                    shlex.split(args.server_command)
                    if args.server_command
                    else [sys.executable, "-m", "agent_regression.fixtures.mcp_stdio_server"]
                )
                trace = record_mcp_run(
                    adapter,
                    scenario.get("input"),
                    command,
                    run_id=scenario["run_id"],
                    metadata=scenario.get("metadata"),
                    timeout_seconds=args.timeout,
                    redaction_policy=redaction_policy,
                )
            else:
                trace = record_mcp_http_run(
                    adapter,
                    scenario.get("input"),
                    args.url,
                    run_id=scenario["run_id"],
                    metadata=scenario.get("metadata"),
                    timeout_seconds=args.timeout,
                    redaction_policy=redaction_policy,
                )
            _write_output(trace.to_dict(), args.out)
            return 0

        if args.command == "replay":
            report = replay_trace(AgentTrace.from_dict(_read_json(args.trace)))
            _write_output(report, args.out)
            return 0

        if args.command == "mcp-smoke":
            if args.url:
                client = StreamableHttpMcpClient(args.url, timeout_seconds=args.timeout)
            else:
                client = StdioMcpClient(
                    shlex.split(args.server_command),
                    timeout_seconds=args.timeout,
                    framing=args.stdio_framing,
                )
            with client:
                _write_output(run_compatibility_smoke(client), args.out)
            return 0

        if args.command == "validate":
            trace = AgentTrace.from_dict(_read_json(args.trace))
            _write_output(
                {
                    "ok": True,
                    "schema_version": trace.schema_version,
                    "run_id": trace.run_id,
                    "event_count": len(trace.events),
                }
            )
            return 0

        if args.command == "baseline":
            if args.baseline_action == "accept":
                trace = AgentTrace.from_dict(_read_json(args.trace))
                _write_output(trace.to_dict(), args.out)
                return 0
            trace = AgentTrace.from_dict(_read_json(args.baseline))
            report = replay_trace(trace)
            _write_output(
                {
                    "ok": True,
                    "run_id": trace.run_id,
                    "agent": trace.agent,
                    "event_count": len(trace.events),
                    "tool_call_count": len(report["calls"]),
                }
            )
            return 0

        baseline = AgentTrace.from_dict(_read_json(args.baseline))
        candidate = AgentTrace.from_dict(_read_json(args.candidate))
        report = compare_traces(
            baseline,
            candidate,
            ComparisonPolicy(
                allowed_categories=set(args.allow_category),
                allowed_paths=set(args.allow_path),
            ),
            redaction_policy,
        )
        if args.format == "junit":
            _write_text(render_junit(report), args.out)
        else:
            _write_output(report, args.out)
        return 0 if report["passed"] else 1
    except (KeyError, ValueError, TraceValidationError, McpTransportError) as exc:
        _write_output({"ok": False, "error": redaction_policy.redact(str(exc))})
        return 2


if __name__ == "__main__":
    sys.exit(main())
