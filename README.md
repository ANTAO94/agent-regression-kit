# Agent Regression Kit

Agent Regression Kit is a small, framework-neutral regression-testing layer for AI Agents. It turns an Agent run into versioned, redacted JSON evidence, then compares a candidate run with a reviewed baseline. A changed prompt, model, tool schema, or adapter should produce a visible diff in CI instead of a silent behavior change.

Current release line: **v1.1 development preview**. It supports deterministic local runs plus MCP stdio and Streamable HTTP capture, offline replay, structural comparison, baseline management, JSON/JUnit reports, and CI exit codes.

```text
Agent / MCP Server
        │
        ▼
  record a Trace  ──────►  reviewed baseline
        │                         │
        └──── candidate Trace ────┘
                                  │
                                  ▼
                       compare + JSON/JUnit report
                                  │
                                  ▼
                         CI pass / regression
```

The project is not a general scorer platform, Agent framework, LLM judge, or
dashboard. The included order Agent and MCP server are deterministic fixtures
that make the integration boundary runnable without model or network access.

## Current validation

The following results were run locally on 2026-09-17:

| Check | Result |
| --- | --- |
| Python unit and integration suite | **48 passed, 0 failed** |
| Source compilation | Passed with `compileall` |
| Wheel build | `agent_regression_kit-1.1.0-py3-none-any.whl` built successfully |
| Official Everything Server over stdio | Passed; protocol `2025-11-25`, 13 tools, 7 resources, 4 prompts |
| Official Everything Server over Streamable HTTP | Passed; same discovery counts |
| Bidirectional MCP exercise | Passed; sampling, elicitation, task creation, polling, and final task result |

Reproduce the core result:

```text
$ PYTHONPATH=src python3 -m unittest discover -s tests -q
----------------------------------------------------------------------
Ran 48 tests in 7.6s

OK
```

The official-server check is intentionally separate from the default offline
suite. Run it with the manual workflow in
[`.github/workflows/mcp-compatibility.yml`](.github/workflows/mcp-compatibility.yml)
or with the `mcp-smoke` command described below.

## AgentTrace v0.1

Every trace contains:

- `schema_version`, currently `0.1`;
- a stable `run_id` and an `agent` identity object;
- contiguous, one-based event `sequence` values;
- paired `tool_call` / `tool_result` events linked by `call_id`;
- exactly one terminal `final_answer`;
- optional run `metadata` and optional structured final-answer `claims`.

`claims` make result interpretation explicit enough for deterministic regression checks. The kit does not guess semantic facts from prose in v0.1.

The canonical machine-readable contract is `schema/agent-trace-v0.1.schema.json`. Runtime validation additionally enforces contiguous sequence values, valid call/result pairing, and exactly one terminal answer.

## Quick start

Python 3.9+ is the only runtime dependency.

```bash
python -m venv .venv
.venv/bin/pip install -e .

agent-regression record \
  --scenario examples/order-123/baseline.scenario.json \
  --out work/baseline.trace.json

agent-regression record \
  --scenario examples/order-123/candidate-regression.scenario.json \
  --out work/candidate.trace.json

agent-regression replay --trace work/baseline.trace.json
agent-regression validate --trace work/baseline.trace.json

agent-regression compare \
  --baseline work/baseline.trace.json \
  --candidate work/candidate.trace.json \
  --out work/diff.json
```

The last command exits `1` because the candidate changes the tool name, changes `order_id` from the string `"123"` to the number `123`, contradicts the recorded result in its structured claim, and changes the final answer. A match exits `0`; invalid input or trace data exits `2`.

To run the automated tests without installing the package:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The default suite is deterministic and offline. It covers trace validation,
record/replay/compare, redaction, JSON/JUnit reports, MCP stdio and HTTP
transports, pagination, cancellation, reconnect, resumable SSE, progress,
concurrent calls, server-initiated requests, task helpers, and failure paths.

## Public API

The same flow is available through `record_run`, `record_mcp_run`, `replay_trace`, and `compare_traces`. A real integration implements the small `AgentAdapter` protocol: expose an `identity`, execute one request, route tool calls through `RunContext.call_tool`, and finish through `RunContext.final_answer`.

This boundary keeps framework-specific hooks outside the trace, comparator, and report. See `docs/api.md` for the supported imports and `docs/architecture.md` for component and failure-flow diagrams.

### Rule-driven Agent example

`RuleBasedOrderAgentAdapter` is the smallest reference Agent that makes a real
decision from runtime data. It extracts an order ID from the request, chooses
`get_order`, calls the local MCP fixture, reads the returned status, and only
then creates its final text and structured claims. Its answer is not stored in
a scripted plan.

The example also includes two controlled defects: a parameter regression that
sends a numeric ID with the wrong type, and a result-misread variant that
incorrectly interprets `not_shipped` as `shipped`. Run the full record, replay,
and comparison flow offline:

```bash
python examples/rule_agent_mcp_example.py
python -m json.tool outputs/rule-agent-baseline.replay.json
python -m json.tool outputs/rule-agent-parameter-regression.diff.json
python -m json.tool outputs/rule-agent-result-misread.diff.json
```

This reference Agent is deterministic by design. It proves the integration
boundary without claiming to provide planning, model inference, memory, or a
general natural-language parser.

## Local MCP fixture and capture

The repository now includes a project-owned, deterministic MCP stdio fixture at `src/agent_regression/fixtures/mcp_stdio_server.py`. It is a narrow test double, not a complete MCP conformance server. It is pinned to the MCP `2025-11-25` lifecycle because this fixture intentionally exercises `initialize` followed by `notifications/initialized`; the newer `2026-07-28` revision removed that handshake.

The implemented protocol surface is:

- newline-delimited UTF-8 JSON-RPC 2.0 over a child process's stdin/stdout;
- `initialize` and `notifications/initialized`;
- `tools/list` and `tools/call`;
- one `get_order` tool with a normal result, an invalid-argument tool error, and a deterministic service-error input (`order_id: "500"`);
- JSON-RPC errors for unsupported methods and unknown tools.

Run the complete local capture example:

```bash
python examples/mcp_record_example.py
python -m json.tool outputs/mcp-order-123.trace.json >/dev/null
```

Or run the same fixture through the installed CLI and compare a candidate:

```bash
agent-regression mcp-record \
  --scenario examples/order-123/baseline.scenario.json \
  --out work/mcp-baseline.trace.json
agent-regression mcp-record \
  --scenario examples/order-123/candidate-regression.scenario.json \
  --out work/mcp-candidate.trace.json
agent-regression compare \
  --baseline work/mcp-baseline.trace.json \
  --candidate work/mcp-candidate.trace.json \
  --out outputs/mcp-order-123.diff.json
```

`record_mcp_run` starts the server, performs the handshake and tool discovery, records tool calls/results through the existing AgentTrace recorder, and stores a request/response transcript under `metadata.mcp`. `McpToolExecutor` prefers MCP `structuredContent`, falls back to `content`, and preserves `isError` in the trace.

### Streamable HTTP capture

The same recorder can connect to an MCP Streamable HTTP endpoint. It accepts
the immediate JSON response form and the server-sent-event response form,
preserves the `Mcp-Session-Id`, and stores the HTTP transcript in the same
`metadata.mcp` shape:

```bash
agent-regression mcp-http-record \
  --url http://127.0.0.1:8000/mcp \
  --scenario examples/order-123/baseline.scenario.json \
  --out work/http-baseline.trace.json
```

For a fully local smoke test, start the bundled HTTP fixture in another
terminal:

```bash
python -m agent_regression.fixtures.mcp_http_server --port 8765
agent-regression mcp-http-record \
  --url http://127.0.0.1:8765/mcp \
  --scenario examples/order-123/baseline.scenario.json \
  --out work/http-baseline.trace.json
```

The HTTP client is intentionally synchronous in v1.1. In addition to
request/response capture, `open_event_stream()` provides a bounded iterator for
the session's GET SSE stream; server notifications and requests are recorded in
the same transcript. A server-initiated request can be answered explicitly
with `client.respond(...)` or `stream.respond(...)`. Pagination helpers,
explicit cancellation, reconnect, resumable SSE streams, automatic request
dispatch callbacks, progress filtering, and bounded concurrent calls are
supported. The generic AgentTrace recorder remains sequential in v1.1.
For task-capable tools, pass task metadata such as
`task={"ttl": 60000, "pollInterval": 100}` to `call_tool`; poll the returned
task with `get_task` and fetch its final value with `get_task_result`. When an
HTTP POST response is an SSE stream, the client can dispatch in-band sampling
or elicitation requests through the configured callback before returning the
final tool response.

### Optional compatibility smoke test

`mcp-smoke` performs a non-mutating initialize and capability-discovery check.
It is suitable for a manual compatibility job or a scheduled workflow, but it
is intentionally not part of the default offline test suite:

```bash
agent-regression mcp-smoke \
  --server-command 'npx -y @modelcontextprotocol/server-everything'
```

The official Everything Server is a reference/test server that exercises tools,
resources, prompts, and additional MCP features. Its Streamable HTTP mode can
be checked by starting that server separately and passing its `/mcp` endpoint
with `--url`. The smoke command only discovers advertised primitives; it does
not invoke tools or mutate resources. The stdio client supports both newline
JSON-RPC and Content-Length framing for servers that require the latter.

For a local compatibility check after installing the package:

```bash
agent-regression mcp-smoke \
  --server-command 'npx -y @modelcontextprotocol/server-everything stdio' \
  --stdio-framing newline \
  --timeout 60 \
  --out outputs/official-everything-stdio.json
```

The command writes a machine-readable report with the negotiated protocol,
server identity, advertised capabilities, and discovery counts. It does not
claim full MCP conformance; the deeper sampling, elicitation, and task flow
is covered by the integration exercise used for the validation table above.

This fixture follows the official [MCP 2025-11-25 lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle), [schema reference](https://modelcontextprotocol.io/specification/2025-11-25/schema), and [stdio framing rules](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports). External compatibility validation is optional and is intentionally outside the default test suite.

## Comparison, baselines, and CI

Default comparison is strict: any detected difference fails. Reports categorize `tool_name`, `tool_arguments`, `tool_result`, `tool_error_state`, `result_interpretation`, `final_answer`, and `event_count`. Exact categories or paths can be allowed without hiding them:

```bash
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/candidate.trace.json \
  --allow-path final_answer.text
```

Baseline changes are explicit:

```bash
agent-regression baseline accept \
  --trace work/reviewed.trace.json \
  --out baselines/order-123.trace.json
agent-regression baseline show --baseline baselines/order-123.trace.json
```

Generate a JUnit report while preserving the comparison exit code:

```bash
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/candidate.trace.json \
  --format junit \
  --out outputs/junit.xml
```

`.github/workflows/regression.yml` is an offline CI example. The reusable
local action at `.github/actions/agent-regression` compares a candidate trace,
writes a JUnit report, and preserves the blocking exit code. Exit code `0`
means pass, `1` means a blocking regression, and `2` means invalid input or an
operational error.

## Security and reproducibility

Common secret-bearing keys are recursively replaced with `[REDACTED]` before evidence is stored. Use repeatable `--secret-value` flags for secrets embedded in free-form text. Raw arguments still reach the selected tool executor, so only run trusted external MCP commands.

The MCP executor records timeout, attempt, retry count, and request ID on each tool result. It never retries automatically because the side effects of an arbitrary tool are unknown. The bundled fixture is isolated in a child process, performs no network access, and has deterministic results.

See `docs/limitations.md` for the complete trust boundary and intentionally unsupported protocol features. LLM judges, dashboards, latency/cost gates, and general release aggregation remain out of scope.

## Development

```bash
python -m unittest discover -s tests -v
python -m pip wheel --no-build-isolation .
```

The default suite is offline. Official MCP Everything Server checks are
optional compatibility validation and are not default dependencies. The next
natural extension points are authentication, more framework adapters, richer
non-deterministic scoring, and long-term trend reporting.
