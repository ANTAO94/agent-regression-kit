# Public Python API

The supported imports are exported from `agent_regression`.

## Framework bridge and parallel recording

- `CallableAgentAdapter(identity, runner)` wraps a framework-owned callable
  with the stable `AgentAdapter` boundary. The callable receives
  `(request, context)` and reports tools and the final answer through the
  context; the kit does not auto-detect or take over a framework.
- `ScenarioCase` describes one independent case with an adapter factory, tool
  executor factory, optional state backend factory, and an `isolate` flag.
- `record_scenario_batch(cases, max_workers=4, redaction_policy=None)` records
  cases concurrently, captures per-case failures, and returns results sorted by
  `case_id` regardless of completion order. Factories are required so workers
  do not accidentally share mutable Agent or tool state.
- `ScenarioResult` contains either a validated `trace` or a redacted `error`;
  `ScenarioBatchResult.to_dict()` is a compact CI-friendly summary.

Example framework bridge:

```python
from agent_regression import CallableAgentAdapter, record_run


def invoke_framework(request, context):
    result = context.call_tool("get_order", {"order_id": request["order_id"]})
    context.final_answer(
        f"status={result['status']}",
        {"order_status": result["status"]},
    )


adapter = CallableAgentAdapter(
    {"name": "my-framework-agent", "version": "1.0.0"},
    invoke_framework,
)
trace = record_run(adapter, {"order_id": "123"}, my_tools, run_id="order-123")
```

For parallel recording, each `ScenarioCase` should construct its own adapter
and tools. Set `isolate=True` when the tools or state backend implements
`snapshot()` and `restore(snapshot)`.

## Evidence

- `AgentTrace.from_dict(value)` parses and validates AgentTrace v0.1.
- `AgentTrace.to_dict()` returns JSON-serializable evidence.
- `TraceValidationError` reports schema or lifecycle violations.

## Recording

- `record_run(adapter, request, tools, *, run_id, metadata=None, redaction_policy=None, state_backend=None)` records any `AgentAdapter` with any `ToolExecutor`. When supplied, `state_backend.snapshot()` is used for the recorded initial/final world state instead of the tool executor.
- `record_session(adapter, requests, tools, *, session_id, metadata=None, turn_metadata=None, redaction_policy=None, state_backend=None)` records multiple turns with the same adapter and tool executor, preserving shared state between turns and observing the optional external state backend.
- `isolated_record_run(...)` and `isolated_record_session(...)` wrap the corresponding recorder in a `StateIsolation` context and restore the state backend after the run, including when the Agent raises an exception.
- `ScriptedAgentAdapter` is the deterministic reference adapter.
- `ScriptedSessionAdapter` provides one deterministic action plan per session turn.
- `FixtureTools` supplies fixed offline results.
- `ToolExecutionResult` lets an executor preserve explicit error state and execution metadata.
- `WorldState` provides a detached mutable state object for deterministic scenario fixtures.
- `StatefulFixtureTools(initial_state, handlers)` executes tools against one owned world and exposes `snapshot()`, `restore()`, `reset()`, `fresh()`, and `isolation()` for case isolation. A recorder automatically stores `metadata.world_state.initial` and `metadata.world_state.final` when an executor exposes `snapshot()`.
- `SnapshotBackend` is the small protocol for a database, cache, or service-emulator fixture: implement `snapshot()` and `restore(snapshot)`.
- `StateIsolation(backend)` captures a detached snapshot on entry and restores it on exit. Use it directly when a test needs to perform setup and assertions around the Agent run, or use the `isolated_record_*` helpers for the common record-and-restore flow.
- `RedactionPolicy` controls sensitive keys and literal value removal. Default key redaction is always active unless a caller explicitly supplies another policy.

An adapter must expose an `identity` mapping and implement `run(request, context)`. It must route calls through `context.call_tool` and finish exactly once with `context.final_answer`.

For an external mutable state source, keep the state adapter separate from the
tool executor and pass it explicitly:

```python
from agent_regression import isolated_record_run


class TestDatabaseState:
    def snapshot(self):
        return read_order_rows_as_json()

    def restore(self, snapshot):
        replace_order_rows_from_json(snapshot)


trace = isolated_record_run(
    MyOrderAgent(),
    "cancel order 123",
    my_tools,
    state_backend=TestDatabaseState(),
    run_id="order-123",
)
# The database fixture is restored here, even when the Agent fails.
```

The backend should be a test-safe boundary: use a transaction rollback,
temporary schema, emulator snapshot, or equivalent. The kit can only restore
what the backend exposes; hidden writes in another service still need their own
cleanup mechanism.

## Repeated-run stability

`StabilityPolicy` defines explicit thresholds for a repeated scenario:

```python
from agent_regression import StabilityPolicy, record_stability

report = record_stability(
    baseline,
    scenario_case,
    repeats=10,
    max_workers=4,
    policy=StabilityPolicy(
        min_pass_rate=0.95,
        min_claims_match_rate=1.0,
        max_tool_error_rate=0.05,
        max_path_variants=1,
    ),
)
assert report.passed
```

`record_stability` reuses the isolated `ScenarioCase` factory boundary from
the batch recorder. It creates a fresh Agent and tool executor for every
repeat, compares every trace to `baseline`, and captures an exception as a
failed repeat instead of hiding it. `evaluate_stability` performs the same
aggregation for traces that were already recorded.

`StabilityReport.to_dict()` contains `pass_rate`, `claims_match_rate`,
`tool_error_rate`, `path_variant_count`, the active policies, and one result
per repeat. The CLI equivalent is:

```bash
agent-regression stability \
  --baseline baselines/order-123.trace.json \
  --scenario examples/order-123/baseline.scenario.json \
  --repeats 10 --workers 4 --format markdown \
  --out outputs/stability.md
```

Use `--final-answer-mode claims-only` only when final prose is intentionally
allowed to vary. The stability evaluator remains structural and deterministic;
it does not call a model to judge semantic similarity.

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
- `trace_outcome_path(trace)` returns the ordered path with `[ok]` or `[error]` result annotations.
- `trace_business_branch(trace, branch_paths)` projects selected structured
  claims into one business-result branch.
- `compare_trace_coverage(trace_dir, expected_paths=...)` aggregates scenario
  traces, reports observed and missing paths, and sets `passed` to `false` when
  an expected path was not covered. Pass `include_outcomes=True` to distinguish
  successful and failed tool results; pass `branch_paths` and
  `expected_branches` to gate structured business outcomes.
- `AgentSession` validates a sequence of AgentTrace turns, and
  `compare_sessions(baseline, candidate, policy=None)` compares each matching
  turn while preserving turn-level differences.
- `check_session_state_continuity(session, policy=None)` reports when one
  turn's final world snapshot differs from the next turn's initial snapshot.
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
- `render_session_junit(report)` and `render_session_markdown(report)` render
  multi-turn comparison reports.
- `render_stability_junit(report)` and `render_stability_markdown(report)`
  render one testcase/table row per repeated run plus aggregate metrics.
- `render_markdown(report)` renders a compact human-readable comparison summary for CI job summaries.

Default comparison is strict and deterministic. No public API invokes an LLM judge.

## Compatibility

- `run_compatibility_smoke(client)` initializes a client and performs non-mutating discovery checks for advertised tools, resources, prompts, and tasks.
- The `mcp-smoke` CLI command accepts either a stdio server command or a Streamable HTTP URL. It is optional and is not part of the default offline test suite.
- `.github/workflows/mcp-compatibility.yml` runs the smoke check against the official Everything Server manually; it is intentionally separate from the deterministic offline workflow.
- `.github/actions/agent-regression` exposes `final-answer-mode`, comma-separated
  `allow-category`, and comma-separated `allow-path` inputs for CI policy control.
