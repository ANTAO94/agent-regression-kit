"""Public API for Agent Regression Kit."""

from .version import __version__

from .adapters import (
    AgentAdapter,
    AsyncAgentAdapter,
    AsyncCallableAgentAdapter,
    AsyncRunContext,
    AsyncScriptedAgentAdapter,
    CallableAgentAdapter,
    RunContext,
    ScriptedAgentAdapter,
    ScriptedSessionAdapter,
)
from .async_record import AsyncToolExecutor, async_record_run, record_async_run
from .batch import compare_trace_batch
from .batch_record import ScenarioBatchResult, ScenarioCase, ScenarioResult, record_scenario_batch
from .compare import ComparisonPolicy, compare_traces
from .coverage import (
    compare_trace_coverage,
    trace_business_branch,
    trace_outcome_path,
    trace_tool_path,
)
from .isolation import SnapshotBackend, StateIsolation
from .compat import run_compatibility_smoke
from .contracts import ContractPolicy
from .history import HistoryPoint, HistoryReport, build_history_report
from .mcp import (
    McpProtocolError,
    McpEventStream,
    McpToolExecutor,
    McpTimeoutError,
    McpTransportError,
    StdioMcpClient,
    StreamableHttpMcpClient,
    record_mcp_http_run,
    record_mcp_run,
)
from .model import AgentTrace, TraceValidationError
from .record import (
    FixtureTools,
    ToolExecutionResult,
    ToolExecutor,
    WorldStateProvider,
    isolated_record_run,
    isolated_record_session,
    record_run,
    record_session,
)
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy
from .replay import replay_trace
from .reports import (
    render_batch_junit,
    render_batch_markdown,
    render_coverage_junit,
    render_coverage_markdown,
    render_async_markdown,
    render_history_junit,
    render_history_markdown,
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
from .scenario import StatefulFixtureTools, WorldState
from .session import AgentSession, check_session_state_continuity, compare_sessions
from .stability import (
    StabilityPolicy,
    StabilityReport,
    StabilityRun,
    evaluate_stability,
    record_stability,
)
from .sdk import AdapterSpec
from .adapter_contract import check_adapter_contract, check_async_adapter_contract
from .public_api import (
    PUBLIC_API_VERSION,
    SUPPORTED_TRACE_SCHEMA_VERSIONS,
    public_api_manifest,
)
from .templates import initialize_adapter_template
from .rule_agent import (
    NORMAL,
    PARAMETER_REGRESSION,
    RESULT_MISREAD,
    RuleBasedOrderAgentAdapter,
)

__all__ = [
    "AgentAdapter",
    "AsyncAgentAdapter",
    "AsyncCallableAgentAdapter",
    "AsyncRunContext",
    "AsyncScriptedAgentAdapter",
    "AsyncToolExecutor",
    "async_record_run",
    "record_async_run",
    "CallableAgentAdapter",
    "AgentTrace",
    "AgentSession",
    "compare_trace_batch",
    "record_scenario_batch",
    "ScenarioBatchResult",
    "ScenarioCase",
    "ScenarioResult",
    "compare_trace_coverage",
    "ComparisonPolicy",
    "ContractPolicy",
    "DEFAULT_REDACTION_POLICY",
    "FixtureTools",
    "McpProtocolError",
    "McpEventStream",
    "McpToolExecutor",
    "McpTimeoutError",
    "McpTransportError",
    "NORMAL",
    "PARAMETER_REGRESSION",
    "RedactionPolicy",
    "RESULT_MISREAD",
    "RunContext",
    "RuleBasedOrderAgentAdapter",
    "ScriptedAgentAdapter",
    "ScriptedSessionAdapter",
    "StatefulFixtureTools",
    "StateIsolation",
    "SnapshotBackend",
    "StdioMcpClient",
    "StreamableHttpMcpClient",
    "TraceValidationError",
    "ToolExecutionResult",
    "ToolExecutor",
    "trace_tool_path",
    "trace_outcome_path",
    "trace_business_branch",
    "WorldStateProvider",
    "WorldState",
    "compare_traces",
    "compare_sessions",
    "check_session_state_continuity",
    "StabilityPolicy",
    "StabilityReport",
    "StabilityRun",
    "evaluate_stability",
    "record_stability",
    "AdapterSpec",
    "check_adapter_contract",
    "check_async_adapter_contract",
    "PUBLIC_API_VERSION",
    "SUPPORTED_TRACE_SCHEMA_VERSIONS",
    "public_api_manifest",
    "initialize_adapter_template",
    "HistoryPoint",
    "HistoryReport",
    "build_history_report",
    "build_report_index",
    "run_compatibility_smoke",
    "record_run",
    "record_session",
    "isolated_record_run",
    "isolated_record_session",
    "record_mcp_run",
    "record_mcp_http_run",
    "replay_trace",
    "render_junit",
    "render_markdown",
    "render_batch_junit",
    "render_batch_markdown",
    "render_async_markdown",
    "render_history_junit",
    "render_history_markdown",
    "render_scenario_batch_junit",
    "render_scenario_batch_markdown",
    "render_stability_junit",
    "render_stability_markdown",
    "render_coverage_junit",
    "render_coverage_markdown",
    "render_session_junit",
    "render_session_markdown",
    "render_report_index_markdown",
    "__version__",
]
