from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Dict

from .adapters import AsyncScriptedAgentAdapter, ScriptedAgentAdapter, ScriptedSessionAdapter
from .batch import compare_trace_batch
from .batch_record import ScenarioCase, record_scenario_batch
from .async_record import record_async_run
from .compare import ComparisonPolicy, compare_traces
from .compat import run_compatibility_smoke
from .config import load_batch_compare_config, load_compare_config
from .contracts import ContractPolicy
from .coverage import compare_trace_coverage
from .history import build_history_report
from .model import AgentTrace, TraceValidationError
from .mcp import (
    McpTransportError,
    StdioMcpClient,
    StreamableHttpMcpClient,
    record_mcp_http_run,
    record_mcp_run,
)
from .preflight import check_batch_config, check_single_config
from .record import FixtureTools, record_run, record_session
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy
from .reports import (
    render_batch_junit,
    render_batch_markdown,
    render_async_markdown,
    render_history_junit,
    render_history_markdown,
    render_coverage_junit,
    render_coverage_markdown,
    render_junit,
    render_markdown,
    render_scenario_batch_junit,
    render_scenario_batch_markdown,
    render_stability_junit,
    render_stability_markdown,
    render_session_junit,
    render_session_markdown,
    render_report_index_markdown,
)
from .report_index import build_report_index
from .replay import replay_trace
from .scaffold import initialize_project
from .session import AgentSession, compare_sessions
from .stability import StabilityPolicy, record_stability
from .templates import initialize_adapter_template
from .ui import serve_viewer
from .version import __version__


VERSION = __version__


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


def _write_json_file(value: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_scripted_batch_case(path: Path, root: Path) -> ScenarioCase:
    scenario = _read_json(str(path))
    relative = path.relative_to(root)
    return ScenarioCase(
        case_id=str(relative),
        request=scenario.get("input"),
        run_id=scenario["run_id"],
        adapter_factory=lambda scenario=scenario: ScriptedAgentAdapter(
            scenario["agent"], scenario["plan"]
        ),
        tools_factory=lambda scenario=scenario: FixtureTools(scenario.get("tools", {})),
        metadata=scenario.get("metadata"),
    )


def _trace_path_for_scenario(path: Path, scenario_root: Path, trace_root: Path) -> Path:
    relative = path.relative_to(scenario_root)
    name = str(relative)
    suffix = ".scenario.json"
    if not name.endswith(suffix):
        raise ValueError(f"scenario file must end with {suffix}: {path}")
    trace_relative = Path(name[: -len(suffix)] + ".trace.json")
    return trace_root / trace_relative


def _parse_headers(values: list[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for value in values:
        name, separator, header_value = value.partition(":")
        if not separator or not name.strip():
            raise ValueError(f"header must use 'Name: value' syntax: {value!r}")
        headers[name.strip()] = header_value.strip()
    return headers


def _parse_branch_values(values: list[str], branch_paths: list[str]) -> list[Dict[str, Any]]:
    """Parse scalar branches or JSON objects for coverage gating."""
    if values and not branch_paths:
        raise ValueError("--expected-branch requires at least one --branch-path")
    parsed: list[Dict[str, Any]] = []
    for raw in values:
        if len(branch_paths) == 1 and not raw.lstrip().startswith("{"):
            key = branch_paths[0]
            value_text = raw
            if "=" in raw:
                possible_key, value_text = raw.split("=", 1)
                if possible_key.strip():
                    key = possible_key.strip()
            try:
                value: Any = json.loads(value_text)
            except json.JSONDecodeError:
                value = value_text
            parsed.append({key: value})
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "expected branch must be a scalar with one --branch-path or a JSON object"
            ) from exc
        if not isinstance(value, dict):
            raise ValueError("JSON expected branch must be an object")
        parsed.append(value)
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-regression")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser(
        "init", help="scaffold an Agent Regression Kit integration in a project"
    )
    init.add_argument(
        "--directory",
        default=".",
        help="project directory to scaffold (default: current directory)",
    )
    init.add_argument(
        "--force",
        action="store_true",
        help="overwrite files generated by a previous init",
    )

    ui = subparsers.add_parser(
        "ui", help="serve the local Trace Inspector and configuration viewer"
    )
    ui.add_argument(
        "--directory",
        help="viewer directory (default: bundled assets or ./viewer)",
    )
    ui.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind address (default: loopback only)",
    )
    ui.add_argument(
        "--port",
        type=int,
        default=8765,
        help="TCP port; use 0 for an ephemeral port (default: 8765)",
    )
    ui.add_argument(
        "--open-browser",
        action="store_true",
        help="open the viewer URL in the default browser",
    )

    adapter_init = subparsers.add_parser(
        "adapter-init", help="generate a sync or async framework adapter template"
    )
    adapter_init.add_argument(
        "--directory",
        default=".",
        help="directory in which to generate adapter.py and its contract test",
    )
    adapter_init.add_argument("--name", default="my-agent")
    adapter_init.add_argument(
        "--mode",
        choices=["sync", "async", "both"],
        default="sync",
        help="generated adapter style (default: sync)",
    )
    adapter_init.add_argument("--force", action="store_true")

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
        "--header",
        action="append",
        default=[],
        help="HTTP request header in 'Name: value' form; repeatable",
    )
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
    smoke.add_argument(
        "--header",
        action="append",
        default=[],
        help="HTTP request header in 'Name: value' form; repeatable",
    )
    smoke.add_argument("--out")

    replay = subparsers.add_parser("replay", help="validate and inspect recorded evidence")
    replay.add_argument("--trace", required=True)
    replay.add_argument("--out")

    validate = subparsers.add_parser("validate", help="validate an AgentTrace document")
    validate.add_argument("--trace", required=True)

    compare = subparsers.add_parser("compare", help="compare candidate evidence to a baseline")
    compare.add_argument("--baseline")
    compare.add_argument("--candidate")
    compare.add_argument("--config", help="JSON config with project-level compare defaults")
    compare.add_argument("--out")
    compare.add_argument("--format", choices=["json", "junit", "markdown"])
    compare.add_argument(
        "--final-answer-mode",
        choices=["exact", "claims-only"],
        default=None,
        help="compare final prose exactly or compare only structured claims",
    )
    compare.add_argument(
        "--secret-value", action="append", default=None, help="literal secret value to redact; repeatable"
    )
    compare.add_argument(
        "--allow-category",
        action="append",
        default=None,
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
        default=None,
        help="exact difference path that should not fail the comparison; repeatable",
    )

    batch_compare = subparsers.add_parser(
        "batch-compare", help="compare matching Trace files across two directories"
    )
    batch_compare.add_argument("--baseline-dir")
    batch_compare.add_argument("--candidate-dir")
    batch_compare.add_argument("--config", help="JSON config with project-level batch defaults")
    batch_compare.add_argument("--out")
    batch_compare.add_argument("--format", choices=["json", "junit", "markdown"])
    batch_compare.add_argument(
        "--final-answer-mode",
        choices=["exact", "claims-only"],
        default=None,
    )
    batch_compare.add_argument("--secret-value", action="append", default=None)
    batch_compare.add_argument("--allow-category", action="append", default=None)
    batch_compare.add_argument("--allow-path", action="append", default=None)

    coverage = subparsers.add_parser(
        "coverage", help="report observed and missing Agent tool paths"
    )
    coverage.add_argument("--trace-dir", required=True)
    coverage.add_argument(
        "--expected-path",
        action="append",
        default=[],
        help="expected tool path such as 'get_order -> cancel_order'; repeatable",
    )
    coverage.add_argument(
        "--include-outcomes",
        action="store_true",
        help="annotate each tool with [ok] or [error] in the path",
    )
    coverage.add_argument(
        "--branch-path",
        action="append",
        default=[],
        help="structured claim path used for business branch coverage; repeatable",
    )
    coverage.add_argument(
        "--expected-branch",
        action="append",
        default=[],
        help="expected branch value or JSON object; repeatable",
    )
    coverage.add_argument("--out")
    coverage.add_argument("--format", choices=["json", "junit", "markdown"], default="json")

    batch_record = subparsers.add_parser(
        "batch-record", help="record independent scenario files in parallel"
    )
    batch_record.add_argument("--scenario-dir", required=True)
    batch_record.add_argument("--out-dir", required=True)
    batch_record.add_argument("--workers", type=int, default=4)
    batch_record.add_argument("--report")
    batch_record.add_argument("--format", choices=["json", "junit", "markdown"], default="json")
    batch_record.add_argument(
        "--secret-value", action="append", default=[], help="literal secret value to redact; repeatable"
    )

    async_record = subparsers.add_parser(
        "async-record", help="record an async scenario with explicit parallel tool groups"
    )
    async_record.add_argument("--scenario", required=True)
    async_record.add_argument("--out", required=True)
    async_record.add_argument("--format", choices=["json", "markdown"], default="json")
    async_record.add_argument(
        "--secret-value", action="append", default=[], help="literal secret value to redact; repeatable"
    )

    history = subparsers.add_parser(
        "history", help="aggregate historical regression reports into a trend"
    )
    history.add_argument("--report-dir", required=True)
    history.add_argument("--pattern", default="*.json")
    history.add_argument("--out")
    history.add_argument("--format", choices=["json", "junit", "markdown"], default="json")
    history.add_argument(
        "--secret-value", action="append", default=[], help="literal secret value to redact; repeatable"
    )

    stability = subparsers.add_parser(
        "stability", help="repeat one scenario and evaluate Agent stability"
    )
    stability.add_argument("--baseline", required=True)
    stability.add_argument("--scenario", required=True)
    stability.add_argument("--repeats", type=int, default=5)
    stability.add_argument("--workers", type=int, default=4)
    stability.add_argument("--min-pass-rate", type=float, default=1.0)
    stability.add_argument("--min-claims-match-rate", type=float, default=1.0)
    stability.add_argument("--max-tool-error-rate", type=float, default=0.0)
    stability.add_argument("--max-path-variants", type=int, default=1)
    stability.add_argument(
        "--final-answer-mode",
        choices=["exact", "claims-only"],
        default="exact",
    )
    stability.add_argument("--allow-category", action="append", default=[])
    stability.add_argument("--allow-path", action="append", default=[])
    stability.add_argument("--out")
    stability.add_argument("--format", choices=["json", "junit", "markdown"], default="json")
    stability.add_argument(
        "--secret-value", action="append", default=[], help="literal secret value to redact; repeatable"
    )

    session_record = subparsers.add_parser(
        "session-record", help="record a deterministic multi-turn session"
    )
    session_record.add_argument("--scenario", required=True)
    session_record.add_argument("--out", required=True)
    session_record.add_argument("--secret-value", action="append", default=[])

    session_compare = subparsers.add_parser(
        "session-compare", help="compare two multi-turn Agent sessions"
    )
    session_compare.add_argument("--baseline", required=True)
    session_compare.add_argument("--candidate", required=True)
    session_compare.add_argument("--out")
    session_compare.add_argument("--format", choices=["json", "junit", "markdown"])
    session_compare.add_argument("--secret-value", action="append", default=[])

    config = subparsers.add_parser("config", help="validate project comparison configuration")
    config_actions = config.add_subparsers(dest="config_action", required=True)
    config_validate = config_actions.add_parser("validate", help="validate a JSON config file")
    config_validate.add_argument("--config", required=True)
    config_validate.add_argument(
        "--kind", choices=["single", "batch"], default="single",
        help="config shape to validate (default: single)",
    )

    report_index = subparsers.add_parser(
        "report-index", help="index local JSON regression reports for CI and the Viewer"
    )
    report_index.add_argument("--report-dir", required=True)
    report_index.add_argument("--pattern", default="*.json")
    report_index.add_argument("--out")
    report_index.add_argument("--format", choices=["json", "markdown"], default="json")
    report_index.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="return exit code 1 when any indexed report failed",
    )
    report_index.add_argument(
        "--required-report",
        action="append",
        default=[],
        help="required report path or glob relative to --report-dir; repeatable",
    )

    check = subparsers.add_parser(
        "check", help="preflight config and Trace inputs without comparing behavior"
    )
    check.add_argument(
        "--config",
        default=".agent-regression/config.json",
        help="JSON config path (default: .agent-regression/config.json)",
    )
    check.add_argument(
        "--kind", choices=["single", "batch"], default="single",
        help="config shape to check (default: single)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    redaction_policy = RedactionPolicy(
        secret_values=tuple(getattr(args, "secret_value", None) or [])
    )
    try:
        compare_config = (
            load_compare_config(args.config)
            if args.command == "compare" and args.config
            else {}
        )
        batch_config = (
            load_batch_compare_config(args.config)
            if args.command == "batch-compare" and args.config
            else {}
        )
        if args.command in {"compare", "batch-compare"} and args.secret_value is None:
            active_config = compare_config if args.command == "compare" else batch_config
            redaction_policy = RedactionPolicy(
                secret_values=tuple(active_config.get("secret_values", []))
            )
        if args.command == "ui":
            serve_viewer(
                args.directory,
                host=args.host,
                port=args.port,
                open_browser=args.open_browser,
            )
            return 0
        if args.command == "init":
            root = Path(args.directory).resolve()
            root.mkdir(parents=True, exist_ok=True)
            result = initialize_project(root, force=args.force)
            _write_output({"ok": True, "directory": str(root), **result})
            return 0

        if args.command == "adapter-init":
            root = Path(args.directory).resolve()
            root.mkdir(parents=True, exist_ok=True)
            result = initialize_adapter_template(
                root,
                name=args.name,
                mode=args.mode,
                force=args.force,
            )
            _write_output({"ok": True, "directory": str(root), **result})
            return 0

        if args.command == "config":
            loader = load_compare_config if args.kind == "single" else load_batch_compare_config
            loaded = loader(args.config)
            _write_output({"ok": True, "kind": args.kind, "config": loaded})
            return 0

        if args.command == "check":
            report = (
                check_single_config(args.config)
                if args.kind == "single"
                else check_batch_config(args.config)
            )
            _write_output(report)
            return 0

        if args.command == "coverage":
            report = compare_trace_coverage(
                args.trace_dir,
                expected_paths=args.expected_path,
                include_outcomes=args.include_outcomes,
                branch_paths=args.branch_path,
                expected_branches=_parse_branch_values(
                    args.expected_branch, args.branch_path
                ),
                redaction_policy=redaction_policy,
            )
            if args.format == "junit":
                _write_text(render_coverage_junit(report), args.out)
            elif args.format == "markdown":
                _write_text(render_coverage_markdown(report), args.out)
            else:
                _write_output(report, args.out)
            return 0 if report["passed"] else 1

        if args.command == "batch-record":
            scenario_root = Path(args.scenario_dir).resolve()
            if not scenario_root.is_dir():
                raise ValueError(f"scenario directory not found: {args.scenario_dir}")
            scenario_paths = sorted(scenario_root.rglob("*.scenario.json"))
            if not scenario_paths:
                raise ValueError(
                    f"scenario directory contains no *.scenario.json files: {args.scenario_dir}"
                )
            cases = [_load_scripted_batch_case(path, scenario_root) for path in scenario_paths]
            batch = record_scenario_batch(
                cases,
                max_workers=args.workers,
                redaction_policy=redaction_policy,
            )
            trace_root = Path(args.out_dir).resolve()
            report = batch.to_dict()
            report["scenario_dir"] = str(scenario_root)
            report["trace_dir"] = str(trace_root)
            report_cases = {case["case_id"]: case for case in report["cases"]}
            for result in batch.results:
                if result.trace is None:
                    continue
                source = scenario_root / result.case_id
                destination = _trace_path_for_scenario(source, scenario_root, trace_root)
                _write_json_file(result.trace.to_dict(), destination)
                report_cases[result.case_id]["trace"] = str(destination)
            if args.format == "junit":
                _write_text(render_scenario_batch_junit(report), args.report)
            elif args.format == "markdown":
                _write_text(render_scenario_batch_markdown(report), args.report)
            else:
                _write_output(report, args.report)
            return 0 if batch.passed else 1

        if args.command == "async-record":
            scenario = _read_json(args.scenario)
            parallel_plan = scenario.get("parallel_plan")
            final_answer = scenario.get("final_answer")
            if not isinstance(parallel_plan, list) or not parallel_plan:
                raise ValueError("async scenario parallel_plan must be a non-empty array")
            if not isinstance(final_answer, dict):
                raise ValueError("async scenario final_answer must be an object")
            trace = record_async_run(
                AsyncScriptedAgentAdapter(
                    scenario["agent"],
                    parallel_plan,
                    final_answer,
                ),
                scenario.get("input"),
                FixtureTools(scenario.get("tools", {})),
                run_id=scenario["run_id"],
                metadata=scenario.get("metadata"),
                redaction_policy=redaction_policy,
            )
            if args.format == "markdown":
                _write_text(render_async_markdown(trace.to_dict()), args.out)
            else:
                _write_output(trace.to_dict(), args.out)
            return 0

        if args.command == "history":
            report = build_history_report(
                args.report_dir,
                pattern=args.pattern,
                redaction_policy=redaction_policy,
            )
            report_value = report.to_dict()
            if args.format == "junit":
                _write_text(render_history_junit(report_value), args.out)
            elif args.format == "markdown":
                _write_text(render_history_markdown(report_value), args.out)
            else:
                _write_output(report_value, args.out)
            return 0 if report.passed else 1

        if args.command == "report-index":
            report = build_report_index(
                args.report_dir,
                pattern=args.pattern,
                required_reports=args.required_report,
            )
            if args.format == "markdown":
                _write_text(render_report_index_markdown(report), args.out)
            else:
                _write_output(report, args.out)
            if args.fail_on_regression and not report["passed"]:
                return 1
            return 0

        if args.command == "stability":
            baseline = AgentTrace.from_dict(_read_json(args.baseline))
            scenario_path = Path(args.scenario).resolve()
            scenario_root = scenario_path.parent
            case = _load_scripted_batch_case(scenario_path, scenario_root)
            report = record_stability(
                baseline,
                case,
                repeats=args.repeats,
                max_workers=args.workers,
                comparison_policy=ComparisonPolicy(
                    allowed_categories=set(args.allow_category),
                    allowed_paths=set(args.allow_path),
                    final_answer_mode=args.final_answer_mode,
                ),
                policy=StabilityPolicy(
                    min_pass_rate=args.min_pass_rate,
                    min_claims_match_rate=args.min_claims_match_rate,
                    max_tool_error_rate=args.max_tool_error_rate,
                    max_path_variants=args.max_path_variants,
                ),
                redaction_policy=redaction_policy,
            )
            report_value = report.to_dict()
            if args.format == "junit":
                _write_text(render_stability_junit(report_value), args.out)
            elif args.format == "markdown":
                _write_text(render_stability_markdown(report_value), args.out)
            else:
                _write_output(report_value, args.out)
            return 0 if report.passed else 1

        if args.command == "session-record":
            scenario = _read_json(args.scenario)
            turns = scenario.get("turns")
            if not isinstance(turns, list) or not turns:
                raise ValueError("session scenario turns must be a non-empty array")
            adapter = ScriptedSessionAdapter(
                scenario["agent"],
                [turn.get("plan", []) for turn in turns],
            )
            session = record_session(
                adapter,
                [turn.get("input") for turn in turns],
                FixtureTools(scenario.get("tools", {})),
                session_id=scenario["session_id"],
                metadata=scenario.get("metadata"),
                turn_metadata=[turn.get("metadata", {}) for turn in turns],
                redaction_policy=redaction_policy,
            )
            _write_output(session.to_dict(), args.out)
            return 0

        if args.command == "session-compare":
            report = compare_sessions(
                AgentSession.from_dict(_read_json(args.baseline)),
                AgentSession.from_dict(_read_json(args.candidate)),
                redaction_policy=redaction_policy,
            )
            if args.format == "junit":
                _write_text(render_session_junit(report), args.out)
            elif args.format == "markdown":
                _write_text(render_session_markdown(report), args.out)
            else:
                _write_output(report, args.out)
            return 0 if report["passed"] else 1

        if args.command == "batch-compare":
            baseline_dir = args.baseline_dir or batch_config.get("baseline_dir")
            candidate_dir = args.candidate_dir or batch_config.get("candidate_dir")
            if not baseline_dir or not candidate_dir:
                raise ValueError(
                    "batch-compare requires --baseline-dir and --candidate-dir, or --config with both"
                )
            output_format = args.format or batch_config.get("format", "json")
            final_answer_mode = args.final_answer_mode or batch_config.get(
                "final_answer_mode", "exact"
            )
            allowed_categories = (
                set(args.allow_category)
                if args.allow_category is not None
                else set(batch_config.get("allow_categories", []))
            )
            allowed_paths = (
                set(args.allow_path)
                if args.allow_path is not None
                else set(batch_config.get("allow_paths", []))
            )
            contract = ContractPolicy.from_dict(batch_config.get("contract"))
            output_path = args.out or batch_config.get("report")
            report = compare_trace_batch(
                baseline_dir,
                candidate_dir,
                policy=ComparisonPolicy(
                    allowed_categories=allowed_categories,
                    allowed_paths=allowed_paths,
                    final_answer_mode=final_answer_mode,
                    contract=contract,
                ),
                redaction_policy=redaction_policy,
            )
            if output_format == "junit":
                _write_text(render_batch_junit(report), output_path)
            elif output_format == "markdown":
                _write_text(render_batch_markdown(report), output_path)
            else:
                _write_output(report, output_path)
            return 0 if report["passed"] else 1

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
                    headers=_parse_headers(args.header),
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
                client = StreamableHttpMcpClient(
                    args.url,
                    timeout_seconds=args.timeout,
                    headers=_parse_headers(args.header),
                )
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

        baseline_path = args.baseline or compare_config.get("baseline")
        candidate_path = args.candidate or compare_config.get("candidate")
        if not baseline_path or not candidate_path:
            raise ValueError("compare requires --baseline and --candidate, or --config with both")
        output_format = args.format or compare_config.get("format", "json")
        final_answer_mode = args.final_answer_mode or compare_config.get("final_answer_mode", "exact")
        allowed_categories = (
            set(args.allow_category)
            if args.allow_category is not None
            else set(compare_config.get("allow_categories", []))
        )
        allowed_paths = (
            set(args.allow_path)
            if args.allow_path is not None
            else set(compare_config.get("allow_paths", []))
        )
        output_path = args.out or compare_config.get("report")
        contract = ContractPolicy.from_dict(compare_config.get("contract"))
        baseline = AgentTrace.from_dict(_read_json(baseline_path))
        candidate = AgentTrace.from_dict(_read_json(candidate_path))
        report = compare_traces(
            baseline,
            candidate,
            ComparisonPolicy(
                allowed_categories=allowed_categories,
                allowed_paths=allowed_paths,
                final_answer_mode=final_answer_mode,
                contract=contract,
            ),
            redaction_policy,
        )
        if output_format == "junit":
            _write_text(render_junit(report), output_path)
        elif output_format == "markdown":
            _write_text(render_markdown(report), output_path)
        else:
            _write_output(report, output_path)
        return 0 if report["passed"] else 1
    except (KeyError, OSError, ValueError, TraceValidationError, McpTransportError) as exc:
        _write_output({"ok": False, "error": redaction_policy.redact(str(exc))})
        return 2


if __name__ == "__main__":
    sys.exit(main())
