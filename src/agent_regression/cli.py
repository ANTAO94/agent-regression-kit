from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Dict

from .adapters import AsyncScriptedAgentAdapter, ScriptedAgentAdapter, ScriptedSessionAdapter
from .batch import compare_trace_batch
from .benchmark import decide_benchmark, prepare_benchmark, score_benchmark
from .cassette import ReplayMismatchError, replay_agent_run
from .batch_record import ScenarioCase, record_scenario_batch
from .async_record import record_async_run
from .compare import ComparisonPolicy, compare_traces
from .compat import run_compatibility_smoke
from .config import contract_diagnostics, load_batch_compare_config, load_compare_config
from .contracts import ContractPolicy
from .coverage import compare_trace_coverage
from .history import build_history_report
from .migration import (
    build_compatibility_report,
    build_trace_migration_report,
    migrate_trace,
)
from .model import AgentTrace, TraceValidationError
from .mcp import (
    McpTransportError,
    StdioMcpClient,
    StreamableHttpMcpClient,
    record_mcp_http_run,
    record_mcp_run,
)
from .preflight import check_batch_config, check_single_config
from .performance import evaluate_performance_gate, run_performance_benchmark
from .readiness import evaluate_readiness
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
    render_sampling_study_markdown,
    render_readiness_markdown,
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
from .study import evaluate_sampling_study
from .templates import initialize_adapter_template
from .ui import serve_viewer
from .version import __version__
from .workspace import build_workspace_manifest


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


def _write_report_checksum(report_path: str | None, checksum_path: str | None) -> None:
    if not checksum_path:
        return
    if not report_path:
        raise ValueError("--checksum-out requires --out so the rendered report can be hashed")
    output_path = Path(report_path).expanduser().resolve()
    if not output_path.is_file():
        raise ValueError(f"report output does not exist: {report_path}")
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    sidecar = Path(checksum_path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(f"{digest}  {output_path.name}\n", encoding="utf-8")


def _write_json_file(value: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _reject_output_aliases(
    outputs: list[str | None], protected_inputs: list[str], operation: str
) -> None:
    """Prevent review/migration commands from overwriting their inputs."""
    resolved_inputs = {
        Path(path).expanduser().resolve() for path in protected_inputs if path
    }
    resolved_outputs = [
        Path(path).expanduser().resolve() for path in outputs if path
    ]
    if len(resolved_outputs) != len(set(resolved_outputs)):
        raise ValueError(f"{operation} outputs must be different paths")
    for output in resolved_outputs:
        if output in resolved_inputs:
            raise ValueError(
                f"{operation} output must differ from its input: {output}"
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

    replay_run = subparsers.add_parser(
        "replay-run",
        help="run a scripted Agent against a strict recorded tool cassette",
    )
    replay_run.add_argument("--baseline", required=True, help="Trace used as the tool cassette")
    replay_run.add_argument("--scenario", required=True, help="scripted Agent scenario JSON")
    replay_run.add_argument("--out", required=True)

    validate = subparsers.add_parser("validate", help="validate an AgentTrace document")
    validate.add_argument("--trace", required=True)

    compatibility = subparsers.add_parser(
        "compatibility",
        help="check v4 public API and Trace/Session/Contract/Report compatibility",
    )
    compatibility.add_argument(
        "--public-api-version",
        help="declared integration API generation (defaults to the current v4 generation)",
    )
    compatibility.add_argument("--trace", help="Trace JSON to check")
    compatibility.add_argument("--session", help="Session JSON to check")
    compatibility.add_argument("--config", help="comparison config/contract JSON to check")
    compatibility.add_argument("--report", help="report JSON to check")
    compatibility.add_argument("--out")

    migrate = subparsers.add_parser(
        "migrate", help="write an explicitly migrated document without overwriting the source"
    )
    migrate_actions = migrate.add_subparsers(dest="migrate_action", required=True)
    migrate_trace_parser = migrate_actions.add_parser(
        "trace", help="validate and canonicalize a Trace into the current schema"
    )
    migrate_trace_parser.add_argument("--trace", required=True)
    migrate_trace_parser.add_argument("--out", required=True)
    migrate_trace_parser.add_argument(
        "--report", help="optional migration report path; stdout always receives the report"
    )

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
        "--result-alignment",
        choices=["call_id", "order"],
        default=None,
        help="align tool results by call_id (default) or event order",
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
    review = baseline_actions.add_parser(
        "review", help="compare a candidate without changing the baseline"
    )
    review.add_argument("--baseline")
    review.add_argument("--candidate")
    review.add_argument("--config", help="project comparison config")
    review.add_argument("--out")
    review.add_argument("--format", choices=["json", "junit", "markdown"], default="json")
    review.add_argument("--secret-value", action="append", default=None)
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
    batch_compare.add_argument(
        "--result-alignment",
        choices=["call_id", "order"],
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
        "--min-runs",
        type=int,
        default=1,
        help="minimum completed repeats required for a passing stability gate",
    )
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

    study = subparsers.add_parser(
        "study", help="evaluate recorded provider/model sampling evidence"
    )
    study.add_argument("--manifest", required=True)
    study.add_argument("--out")
    study.add_argument(
        "--checksum-out",
        help="write a SHA-256 sidecar for the rendered report; requires --out",
    )
    study.add_argument("--format", choices=["json", "junit", "markdown"], default="json")
    study.add_argument(
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

    workspace = subparsers.add_parser(
        "workspace", help="build a safe manifest for local baselines, runs and reports"
    )
    workspace_actions = workspace.add_subparsers(dest="workspace_action", required=True)
    workspace_manifest = workspace_actions.add_parser(
        "manifest", help="fingerprint evidence files without embedding their contents"
    )
    workspace_manifest.add_argument("--directory", default=".")
    workspace_manifest.add_argument("--out")

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

    benchmark = subparsers.add_parser(
        "benchmark", help="prepare, decide and score a hash-bound benchmark"
    )
    benchmark_actions = benchmark.add_subparsers(
        dest="benchmark_action", required=True
    )
    benchmark_prepare = benchmark_actions.add_parser(
        "prepare", help="validate benchmark inputs without reading label meaning"
    )
    benchmark_prepare.add_argument("--manifest", required=True)
    benchmark_prepare.add_argument("--out")
    benchmark_decide = benchmark_actions.add_parser(
        "decide", help="make evidence-only decisions without loading labels"
    )
    benchmark_decide.add_argument("--manifest", required=True)
    benchmark_decide.add_argument("--out", required=True)
    benchmark_score = benchmark_actions.add_parser(
        "score", help="score frozen decisions against labels"
    )
    benchmark_score.add_argument("--manifest", required=True)
    benchmark_score.add_argument("--decisions", required=True)
    benchmark_score.add_argument("--out", required=True)

    performance = subparsers.add_parser(
        "performance", help="run or gate the deterministic framework performance baseline"
    )
    performance_actions = performance.add_subparsers(
        dest="performance_action", required=True
    )
    performance_run = performance_actions.add_parser(
        "run", help="run the small and medium local workloads"
    )
    performance_run.add_argument("--small-count", type=int, default=10_000)
    performance_run.add_argument("--medium-count", type=int, default=1_000)
    performance_run.add_argument("--medium-tool-calls", type=int, default=10)
    performance_run.add_argument("--out", required=True)
    performance_gate = performance_actions.add_parser(
        "gate", help="compare a current performance report with a stored baseline"
    )
    performance_gate.add_argument("--current", required=True)
    performance_gate.add_argument("--baseline", required=True)
    performance_gate.add_argument("--warn-ratio", type=float, default=0.20)
    performance_gate.add_argument("--block-ratio", type=float, default=0.40)
    performance_gate.add_argument("--out", required=True)

    readiness = subparsers.add_parser(
        "readiness", help="audit final-v4 maturity evidence and quantitative gates"
    )
    readiness.add_argument("--manifest", required=True)
    readiness.add_argument("--out")
    readiness.add_argument("--format", choices=["json", "markdown"], default="json")
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

        if args.command == "compatibility":
            report = build_compatibility_report(
                trace=_read_json(args.trace) if args.trace else None,
                session=_read_json(args.session) if args.session else None,
                config=_read_json(args.config) if args.config else None,
                report=_read_json(args.report) if args.report else None,
                public_api_version=args.public_api_version,
            )
            _write_output(report, args.out)
            return 0 if report["ok"] else 1

        if args.command == "migrate":
            if args.migrate_action != "trace":
                raise ValueError(f"unsupported migrate action: {args.migrate_action}")
            _reject_output_aliases(
                [args.out, args.report],
                [args.trace],
                "migrate trace",
            )
            source = _read_json(args.trace)
            migrated = migrate_trace(source)
            _write_json_file(migrated, Path(args.out))
            _write_output(build_trace_migration_report(source, migrated), args.report)
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
            _write_output(
                {
                    "ok": True,
                    "kind": args.kind,
                    "config": loaded,
                    "diagnostics": contract_diagnostics(loaded),
                }
            )
            return 0

        if args.command == "check":
            report = (
                check_single_config(args.config)
                if args.kind == "single"
                else check_batch_config(args.config)
            )
            _write_output(report)
            return 0

        if args.command == "benchmark":
            if args.benchmark_action == "prepare":
                report = prepare_benchmark(args.manifest)
                _write_output(report, args.out)
                return 0
            if args.benchmark_action == "decide":
                report = decide_benchmark(args.manifest)
                _write_output(report, args.out)
                return 0
            if args.benchmark_action == "score":
                report = score_benchmark(args.manifest, args.decisions)
                _write_output(report, args.out)
                return 0
            raise ValueError(f"unsupported benchmark action: {args.benchmark_action}")

        if args.command == "performance":
            if args.performance_action == "run":
                report = run_performance_benchmark(
                    small_count=args.small_count,
                    medium_count=args.medium_count,
                    medium_tool_calls=args.medium_tool_calls,
                )
                _write_output(report, args.out)
                return 0
            if args.performance_action == "gate":
                report = evaluate_performance_gate(
                    _read_json(args.current),
                    _read_json(args.baseline),
                    warn_ratio=args.warn_ratio,
                    block_ratio=args.block_ratio,
                )
                _write_output(report, args.out)
                return 0 if report["passed"] else 1
            raise ValueError(f"unsupported performance action: {args.performance_action}")

        if args.command == "readiness":
            report = evaluate_readiness(args.manifest)
            if args.format == "markdown":
                _write_text(render_readiness_markdown(report), args.out)
            else:
                _write_output(report, args.out)
            return 0 if report["ready"] else 1

        if args.command == "workspace":
            if args.workspace_action != "manifest":
                raise ValueError(f"unsupported workspace action: {args.workspace_action}")
            _write_output(build_workspace_manifest(args.directory), args.out)
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
                    min_runs=args.min_runs,
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

        if args.command == "study":
            if args.checksum_out and not args.out:
                raise ValueError(
                    "--checksum-out requires --out so the rendered report can be hashed"
                )
            report = evaluate_sampling_study(
                args.manifest,
                redaction_policy=redaction_policy,
            )
            report_value = report.to_dict()
            if args.format == "junit":
                _write_text(render_stability_junit(report_value), args.out)
            elif args.format == "markdown":
                _write_text(render_sampling_study_markdown(report_value), args.out)
            else:
                _write_output(report_value, args.out)
            _write_report_checksum(args.out, args.checksum_out)
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
            result_alignment = args.result_alignment or batch_config.get(
                "result_alignment", "call_id"
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
            default_policy = ComparisonPolicy(
                allowed_categories=allowed_categories,
                allowed_paths=allowed_paths,
                final_answer_mode=final_answer_mode,
                result_alignment=result_alignment,
                contract=contract,
            )
            case_policies = {
                name: ComparisonPolicy(
                    allowed_categories=allowed_categories,
                    allowed_paths=allowed_paths,
                    final_answer_mode=final_answer_mode,
                    result_alignment=result_alignment,
                    contract=ContractPolicy.from_dict(case_contract),
                )
                for name, case_contract in batch_config.get("case_contracts", {}).items()
            }
            output_path = args.out or batch_config.get("report")
            report = compare_trace_batch(
                baseline_dir,
                candidate_dir,
                policy=default_policy,
                case_policies=case_policies,
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

        if args.command == "replay-run":
            scenario = _read_json(args.scenario)
            trace = replay_agent_run(
                ScriptedAgentAdapter(scenario["agent"], scenario["plan"]),
                scenario.get("input"),
                AgentTrace.from_dict(_read_json(args.baseline)),
                run_id=scenario["run_id"],
                metadata=scenario.get("metadata"),
                redaction_policy=redaction_policy,
            )
            _write_output(trace.to_dict(), args.out)
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
                _reject_output_aliases([args.out], [args.trace], "baseline accept")
                trace = AgentTrace.from_dict(_read_json(args.trace))
                _write_output(trace.to_dict(), args.out)
                return 0
            if args.baseline_action == "review":
                review_config = load_compare_config(args.config) if args.config else {}
                if args.secret_value is None:
                    redaction_policy = RedactionPolicy(
                        secret_values=tuple(review_config.get("secret_values", []))
                    )
                baseline_path = args.baseline or review_config.get("baseline")
                candidate_path = args.candidate or review_config.get("candidate")
                if not baseline_path or not candidate_path:
                    raise ValueError(
                        "baseline review requires --baseline and --candidate, or --config with both"
                    )
                _reject_output_aliases(
                    [args.out],
                    [baseline_path, candidate_path],
                    "baseline review",
                )
                policy = ComparisonPolicy(
                    allowed_categories=set(review_config.get("allow_categories", [])),
                    allowed_paths=set(review_config.get("allow_paths", [])),
                    final_answer_mode=review_config.get("final_answer_mode", "exact"),
                    result_alignment=review_config.get("result_alignment", "call_id"),
                    contract=ContractPolicy.from_dict(review_config.get("contract")),
                )
                report = compare_traces(
                    AgentTrace.from_dict(_read_json(baseline_path)),
                    AgentTrace.from_dict(_read_json(candidate_path)),
                    policy,
                    redaction_policy,
                )
                if args.format == "junit":
                    _write_text(render_junit(report), args.out)
                elif args.format == "markdown":
                    _write_text(render_markdown(report), args.out)
                else:
                    _write_output(report, args.out)
                return 0 if report["passed"] else 1
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
        result_alignment = args.result_alignment or compare_config.get(
            "result_alignment", "call_id"
        )
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
        _reject_output_aliases(
            [output_path],
            [baseline_path, candidate_path],
            "compare",
        )
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
                result_alignment=result_alignment,
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
    except ReplayMismatchError as exc:
        _write_output({"ok": False, "error": redaction_policy.redact(str(exc)), "replay": exc.to_dict()})
        return 1
    except (KeyError, OSError, ValueError, TraceValidationError, McpTransportError) as exc:
        _write_output({"ok": False, "error": redaction_policy.redact(str(exc))})
        return 2


if __name__ == "__main__":
    sys.exit(main())
