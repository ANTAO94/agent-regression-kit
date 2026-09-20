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

## Async and parallel events

Use the async boundary when one Agent run awaits multiple tools concurrently:

```python
import asyncio
from agent_regression import AsyncCallableAgentAdapter, record_async_run


async def invoke(request, context):
    order, shipping = await asyncio.gather(
        context.call_tool("get_order", {"order_id": "123"}, parallel_group="lookup"),
        context.call_tool("get_shipping", {"order_id": "123"}, parallel_group="lookup"),
    )
    context.final_answer("done", {"order": order, "shipping": shipping})


trace = record_async_run(
    AsyncCallableAgentAdapter({"name": "async-agent"}, invoke),
    "lookup order 123",
    async_tools,
    run_id="async-order-123",
)
```

`record_async_run` is a synchronous convenience wrapper. Code that already
owns an event loop should `await async_record_run(...)` instead. A parallel
group must use one stable `parallel_group` identifier for all calls started in
that group. The recorder assigns deterministic call IDs, emits call events in
creation order, emits grouped results in that same order, and stores the group
shape in `metadata.execution`. `compare_traces` reports a changed group shape
as `execution_concurrency`.

`AsyncToolExecutor.call_async` is optional. If it is absent, the recorder
executes the existing synchronous `ToolExecutor.call` through `asyncio.to_thread`.
Prefer a native async executor for network clients and make shared mutable
state safe at the tool boundary.

## Adapter SDK and templates

`AdapterSpec` is the small integration SDK for projects that need a stable
identity in both sync and async adapters:

```python
from agent_regression import AdapterSpec

spec = AdapterSpec(
    name="my-agent",
    version="1.0.0",
    metadata={"framework": "spring-ai"},
)
sync_adapter = spec.build_sync(invoke_framework)
async_adapter = spec.build_async(invoke_async_framework)
```

The returned adapters still use the same `RunContext` or `AsyncRunContext`
contract. The SDK does not inspect framework internals, call an LLM, or infer
claims. Its job is to keep the identity and adapter construction consistent.

For a framework integration's first executable smoke test, use the diagnostic
helpers. They return JSON-serializable evidence instead of hiding the useful
failure behind a generic assertion:

```python
from agent_regression import FixtureTools, check_adapter_contract

report = check_adapter_contract(
    sync_adapter,
    {"order_id": "123"},
    FixtureTools({"get_order": {"status": "paid"}}),
    expected_tool_path=["get_order"],
    expected_claims={"order_status": "paid"},
)
assert report["ok"], report
```

The report identifies the identity, Trace validity, observed tool path, and
required claims. `check_async_adapter_contract` provides the same contract for
an async adapter. These helpers are integration diagnostics, not a semantic
judge; the framework callback must still emit the claims explicitly.

### Public compatibility contract

`PUBLIC_API_VERSION` identifies the documented Python import surface. In v4 it
is `"4"`; the v3 generation remains readable but is marked deprecated by the
compatibility checker. The supported names are the symbols in
`agent_regression.__all__`; additions are backward-compatible, while removals
or behavior changes require a deprecation entry and an API-version decision.
`public_api_manifest()` exposes this data to release checks. Trace, Session,
Contract and Report schema compatibility is independent and currently reports
`"0.1"` for each boundary.

For a new integration, generate the starter files and contract test:

```bash
agent-regression adapter-init \
  --directory my-agent-regression \
  --name my-agent \
  --mode both
```

`adapter.py` is the framework boundary, `tests/test_adapter_contract.py` is a
deterministic offline smoke test, and `README.md` explains what to replace.
Use `--mode sync`, `--mode async`, or `--mode both`. The template is a starting
point, not framework auto-discovery; keep framework-specific setup outside the
core recorder.

## v4 compatibility and migration

Use the read-only compatibility command before changing a baseline or
upgrading a CI runner:

```bash
agent-regression compatibility \
  --public-api-version 4 \
  --trace baselines/order-123.trace.json \
  --config .agent-regression/config.json \
  --report outputs/compare.json \
  --out outputs/compatibility.json
```

It checks the public API generation and the independent Trace, Contract/config
and Report boundaries. A v3 public API declaration is accepted as deprecated
and carries `migration_required=true`; an unknown generation or schema fails.
The command never executes an Agent and never writes source documents.

Trace schema `0.1` is unchanged in v4, but an explicit migration entry point
is available for future schema changes:

```bash
agent-regression migrate trace \
  --trace baselines/order-123.trace.json \
  --out work/order-123.v4.trace.json \
  --report outputs/order-123.migration.json
```

The source is not overwritten. The output is validated and canonicalized, while
the migration report contains only status and schema versions, not Trace events.

## Framework event ingestion

When a framework already owns the Agent loop and tool execution, use
`FrameworkTraceRecorder` instead of wrapping the framework in a second tool
executor. The integration forwards lifecycle events and the kit owns only the
evidence boundary:

```python
from agent_regression import FrameworkTraceRecorder

recorder = FrameworkTraceRecorder(
    {"name": "my-agent", "version": "1.0.0"},
    run_id="order-123",
)
recorder.on_tool_start("get_order", {"order_id": "123"}, call_id="call-1")
result = framework_tool_result()
recorder.on_tool_end("call-1", result)
recorder.on_final_answer(
    "The order is paid.",
    claims={"order_status": "paid"},
)
trace = recorder.finish()
```

`on_tool_start` and `on_tool_end` may arrive out of completion order, but every
tool call must close before `finish()`. The recorder rejects duplicate or
unknown call IDs, requires one final answer, applies the selected redaction
policy, and returns a validated `AgentTrace`. `record_framework_run` is a
convenience wrapper for a callback runner that receives the recorder. The
framework and model provider remain integration-owned.

## DeepSeek live tool Agent

`record_deepseek_tool_run` provides one small, dependency-free OpenAI-compatible
DeepSeek loop for live provider regression evidence. It reads
`DEEPSEEK_API_KEY` when `api_key` is omitted, disables thinking, executes only
the supplied tool handlers, and never stores the credential in the Trace:

```python
from agent_regression import record_deepseek_tool_run

trace = record_deepseek_tool_run(
    "Look up order 123",
    run_id="deepseek-order-123",
    system_prompt="Call get_order, then return the result as JSON.",
    tools=tool_definitions,
    tool_handlers={"get_order": get_order_fixture},
    claims_extractor=parse_business_claims,
    force_first_tool="get_order",
    max_tokens=64,
)
```

For a deterministic dependency chain, replace `force_first_tool` with an exact
sequence. Each named tool is forced in order, while the model remains
responsible for generating arguments from prior tool results:

```python
trace = record_deepseek_tool_run(
    "Look up order 123 and check its refund eligibility",
    run_id="deepseek-refund-123",
    system_prompt="Use observed tool results; never invent order fields.",
    tools=tool_definitions,
    tool_handlers=tool_handlers,
    claims_extractor=parse_business_claims,
    required_tool_sequence=("get_order", "check_refund_eligibility"),
)
```

`force_first_tool` and `required_tool_sequence` are mutually exclusive. The
sequence plus the final answer must fit within `max_rounds`. An unexpected,
missing or out-of-order call raises `DeepSeekAPIError` before a Trace can pass.

The default model is `deepseek-flash`. `DeepSeekAPIError` separates provider,
transport and response-shape failures from local policy failures. No automatic
network retry is performed. Pass a `transport` callable for offline tests; a
custom transport marks the generated Trace as non-live. See
`docs/deepseek-live.md` for credential, cost and CI boundaries.

## Controlled cassette replay

`CassetteToolExecutor.from_trace(baseline)` converts a reviewed Trace into a
strict, in-memory tool cassette. `replay_agent_run` then lets Agent logic run
again while the cassette checks the next tool name and JSON arguments and
returns the recorded result. It raises `ReplayMismatchError` for changed
arguments, changed names, extra calls or unconsumed calls. This is safe for
testing Agent interpretation without touching live tools; it is not a test of
the current live tool implementation.

## Workspace manifest and baseline review

`build_workspace_manifest(directory)` fingerprints files under the conventional
`.agent-regression/`, `baselines/`, `work/` and `outputs/` roots. It returns a
JSON-serializable manifest containing relative paths, roles, byte sizes and
SHA-256 values. It deliberately does not embed Trace or report payloads.

```bash
agent-regression workspace manifest \
  --directory . --out work/workspace-manifest.json
agent-regression baseline review \
  --baseline baselines/order-123.trace.json \
  --candidate work/order-123.trace.json \
  --config .agent-regression/compare.json \
  --format markdown --out outputs/baseline-review.md
```

`baseline review` compares without writing the baseline. It returns exit code
`0` for a passing review, `1` for a blocking difference, and `2` for invalid
inputs. Accepting a changed baseline remains an explicit `baseline accept`
operation and should be reviewed in Git.

## Historical trends

Use `build_history_report` to aggregate reports saved by earlier commands:

```python
from agent_regression import build_history_report

history = build_history_report("reports/agent-history")
print(history.latest.label)
print(history.metric_trends["pass_rate"])
assert history.passed  # follows the latest recognized point
```

Reports are loaded in sorted relative-path order. Stability reports contribute
pass, claims-match, tool-error, and path-variant metrics; compare reports
contribute differences; batch reports contribute aggregate pass rate; coverage
reports contribute coverage percentage. Unknown JSON files are listed in
`HistoryReport.skipped` rather than becoming fake trend points.

`HistoryReport.to_dict()` has `report_type="agent_history"`, all normalized
points, latest-status gating, historical regression count, and per-metric
first/latest/delta/min/max values. Use the CLI for CI-friendly renderers:

```bash
agent-regression history \
  --report-dir reports/agent-history \
  --format junit \
  --out outputs/history.junit.xml
```

## Report index

`build_report_index` is the batch handoff layer for a CI output directory. It
recognizes compare, batch, stability, coverage, and history JSON reports, but deliberately
does not embed their full `differences`, Trace events, or arbitrary metadata.
Each entry contains a safe relative path, report type, label, pass/fail status,
and normalized metrics:

```python
from agent_regression import build_report_index

index = build_report_index("outputs")
assert index["report_type"] == "agent_report_index"
print(index["failed_count"], index["entries"])
```

The CLI can produce JSON for the Viewer or Markdown for a job summary:

```bash
agent-regression report-index \
  --report-dir outputs \
  --out outputs/report-index.json

agent-regression report-index \
  --report-dir outputs \
  --format markdown \
  --out outputs/report-index.md \
  --fail-on-regression
```

By default this command is non-gating. `--fail-on-regression` returns exit code
`1` if any recognized report failed; invalid input still follows the normal
CLI error contract. `viewer/reports.html` reads the generated index locally and
does not automatically read neighboring files.

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
- `check --config path/to/config.json [--kind single|batch]` is the stronger
  preflight boundary: it reads every configured Trace, validates AgentTrace
  schema and lifecycle invariants, and for batch configs checks that baseline
  and candidate directories contain the same relative `*.trace.json` files.
  It still does not run an Agent, mutate a baseline, or compare behavior;
  invalid input returns exit code `2`.
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
  `sort`), `must_call`, `must_not_call`, `path_rules.any_of`,
  `path_rules.mode`, `path_rules.extra_calls`, `tool_limits`, `tool_allowlist`, `side_effects`,
  `relations`, and `max_steps`. Path mode `exact` is the default; `ordered_subsequence` allows
  extra calls while preserving required order, and `unordered_subset` allows
  extra calls and reordering. In tolerant modes, omit `extra_calls` for v4.6
  compatibility, configure an explicit list to allow only matching extras, or
  use an empty list to reject all unmatched calls. Rejected calls produce an
  `extra_tool_call` difference. `tool_limits` accepts `min_calls`, `max_calls`
  and optional exact `arguments` matching; violations produce `tool_count`.
  `tool_allowlist` is optional: omission preserves the unrestricted legacy
  behavior, an empty list denies every tool call, strings match tool names and
  object rules may require an exact `arguments` object. Every unmatched
  candidate call produces `unauthorized_tool_call` at `tool_calls[index]`.
  A relation compares a candidate JSON path with
  another candidate path or a fixed value using a finite operator set; missing
  evidence and false comparisons block. Put it under the
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
