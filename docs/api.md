# Public Python API

The supported imports are exported from `agent_regression`.

## Evidence

- `AgentTrace.from_dict(value)` parses and validates AgentTrace v0.1.
- `AgentTrace.to_dict()` returns JSON-serializable evidence.
- `TraceValidationError` reports schema or lifecycle violations.

## Recording

- `record_run(adapter, request, tools, *, run_id, metadata=None, redaction_policy=None)` records any `AgentAdapter` with any `ToolExecutor`.
- `ScriptedAgentAdapter` is the deterministic reference adapter.
- `FixtureTools` supplies fixed offline results.
- `ToolExecutionResult` lets an executor preserve explicit error state and execution metadata.
- `WorldState` provides a detached mutable state object for deterministic scenario fixtures.
- `StatefulFixtureTools(initial_state, handlers)` executes tools against one owned world and exposes `snapshot()`, `reset()`, and `fresh()` for case isolation. A recorder automatically stores `metadata.world_state.initial` and `metadata.world_state.final` when an executor exposes `snapshot()`.
- `RedactionPolicy` controls sensitive keys and literal value removal. Default key redaction is always active unless a caller explicitly supplies another policy.

An adapter must expose an `identity` mapping and implement `run(request, context)`. It must route calls through `context.call_tool` and finish exactly once with `context.final_answer`.

## MCP

- `StdioMcpClient` implements the documented MCP 2025-11-25 subset and accepts newline or Content-Length framing through its `framing` parameter.
- Both clients accept optional `client_capabilities` and `server_request_handler` callbacks for controlled sampling/elicitation-style server requests.
- `StreamableHttpMcpClient` implements synchronous MCP Streamable HTTP request/response capture with JSON and SSE responses, plus `open_event_stream()` for a session GET SSE stream. Custom HTTP headers can be supplied through `headers={...}` for authorization and gateway integration.
- `StreamableHttpMcpClient.call_tools_concurrently(...)` runs bounded concurrent tool calls and preserves input order in its returned results.
- `list_*_page(cursor=...)` and `iter_*()` expose MCP pagination for tools, resources, and prompts; `cancel(...)` sends a cancellation notification and `reconnect()` re-establishes the client lifecycle.
- `McpEventStream` incrementally reads the session's server-to-client SSE stream and records notifications or requests. It tracks `Last-Event-ID`, supports `iter_progress()`, and `respond()` sends an explicit JSON-RPC response; `open_event_stream(request_handler=...)` can automatically answer server requests through a caller-owned callback.
- Both MCP clients expose `list_resources`, `read_resource`, `list_prompts`, and `get_prompt` for the corresponding MCP protocol methods.
- Both MCP clients expose paginated task discovery and explicit `get_task`, `get_task_result`, and `cancel_task` helpers; task execution remains caller-controlled.
- `call_tool(name, arguments, task={...})` requests task-augmented execution when the server advertises it; callers can poll the returned task with the task helpers.
- `McpToolExecutor` normalizes MCP results for the recorder.
- `record_mcp_run` owns server startup, initialization, discovery, recording, and shutdown; its framing, client capabilities, and server-request callback are injectable for real integrations.
- `record_mcp_http_run` owns HTTP initialization, discovery, session propagation, custom headers, recording, and cleanup.
- `McpProtocolError`, `McpTransportError`, and `McpTimeoutError` distinguish failure boundaries.

The project-owned server under `agent_regression.fixtures` is a test fixture, not a supported production server.

## Comparison and reports

- `compare --config path/to/config.json` and `batch-compare --config ...` load
  project-level paths, report, format, policy, and redaction defaults. Explicit
  CLI flags override values from the config file.
- `config validate --config path/to/config.json [--kind single|batch]` performs
  the same validation and prints normalized project-relative paths without
  running an Agent or comparing traces.
- `compare_traces(baseline, candidate, policy=None)` returns a JSON-serializable report.
- `compare_trace_batch(baseline_dir, candidate_dir, policy=None)` compares matching nested `*.trace.json` cases and reports missing files.
- `trace_tool_path(trace)` returns the ordered tool-name path for one trace.
- `compare_trace_coverage(trace_dir, expected_paths=...)` aggregates scenario
  traces, reports observed and missing paths, and sets `passed` to `false` when
  an expected path was not covered.
- `ComparisonPolicy(allowed_categories=..., allowed_paths=..., final_answer_mode=..., contract=...)` changes which differences block while retaining all differences in the report. `final_answer_mode="exact"` compares final prose; `final_answer_mode="claims-only"` ignores only `final_answer.text` while continuing to require matching structured claims.
- `ContractPolicy` adds deterministic Agent behavior rules: `assertions` with
  `equals`/`contains`/`exists`, `ignore_paths`, `normalizers` (`timestamp` and
  `sort`), `must_call`, `must_not_call`, `path_rules.any_of`, `side_effects`,
  and `max_steps`. Put it under the
  config file's `contract` object and pass it through `ComparisonPolicy`.
- `replay_trace(trace)` validates and renders recorded evidence without executing tools.
- `render_junit(report)` renders one comparison as JUnit XML.
- `render_batch_junit(report)` and `render_batch_markdown(report)` render aggregate batch results.
- `render_coverage_junit(report)` and `render_coverage_markdown(report)` render
  scenario-path coverage reports for CI.
- `render_markdown(report)` renders a compact human-readable comparison summary for CI job summaries.

Default comparison is strict and deterministic. No public API invokes an LLM judge.

## Compatibility

- `run_compatibility_smoke(client)` initializes a client and performs non-mutating discovery checks for advertised tools, resources, prompts, and tasks.
- The `mcp-smoke` CLI command accepts either a stdio server command or a Streamable HTTP URL. It is optional and is not part of the default offline test suite.
- `.github/workflows/mcp-compatibility.yml` runs the smoke check against the official Everything Server manually; it is intentionally separate from the deterministic offline workflow.
- `.github/actions/agent-regression` exposes `final-answer-mode`, comma-separated
  `allow-category`, and comma-separated `allow-path` inputs for CI policy control.
