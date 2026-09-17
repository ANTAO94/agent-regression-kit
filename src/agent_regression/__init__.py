"""Public API for Agent Regression Kit."""

__version__ = "2.1.0"

from .adapters import AgentAdapter, RunContext, ScriptedAgentAdapter
from .batch import compare_trace_batch
from .compare import ComparisonPolicy, compare_traces
from .compat import run_compatibility_smoke
from .contracts import ContractPolicy
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
from .record import FixtureTools, ToolExecutionResult, ToolExecutor, record_run
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy
from .replay import replay_trace
from .reports import render_batch_junit, render_batch_markdown, render_junit, render_markdown
from .rule_agent import (
    NORMAL,
    PARAMETER_REGRESSION,
    RESULT_MISREAD,
    RuleBasedOrderAgentAdapter,
)

__all__ = [
    "AgentAdapter",
    "AgentTrace",
    "compare_trace_batch",
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
    "StdioMcpClient",
    "StreamableHttpMcpClient",
    "TraceValidationError",
    "ToolExecutionResult",
    "ToolExecutor",
    "compare_traces",
    "run_compatibility_smoke",
    "record_run",
    "record_mcp_run",
    "record_mcp_http_run",
    "replay_trace",
    "render_junit",
    "render_markdown",
    "render_batch_junit",
    "render_batch_markdown",
    "__version__",
]
