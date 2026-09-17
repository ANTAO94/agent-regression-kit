# Agent Regression Kit v1.6 verification

Verified on 2026-09-17 with Python 3.9.6.

## Results

- Runtime: Python 3.9.6.
- Unit and integration tests: 56 passed, 0 failed.
- Wheel build: `agent_regression_kit-1.6.0-py3-none-any.whl` succeeded.
- Claims-only final-answer comparison: passed; wording changes were ignored while changed claims remained blocking.
- Batch directory comparison with missing-case detection: passed.
- Authenticated HTTP request headers: passed.
- Markdown comparison report and GitHub job-summary rendering: passed.
- `agent-regression init` scaffolded a fresh project and its generated Agent example recorded a valid Trace.
- Source compilation with `compileall`: succeeded.
- Local MCP fixture capture: succeeded through real subprocess stdio and Streamable HTTP.
- Official Everything Server stdio discovery: passed with 13 tools, 7 resources, and 4 prompts.
- Official Everything Server Streamable HTTP discovery: passed with 13 tools, 7 resources, and 4 prompts.
- Official bidirectional exercise: passed sampling, elicitation, task creation, task polling, and final task result retrieval.
- Matching MCP candidate comparison: exit code 0.
- MCP regression candidate comparison: exit code 1 as intended.
- Regression JSON and JUnit failure reports: generated.
- Trace validation, baseline acceptance/show, replay, policy allow-list, redaction, startup failure, protocol error, tool error, timeout, pagination, cancellation, reconnect, SSE, and server-request paths: covered by tests.

## Scope

The implementation contains AgentTrace v0.1, deterministic and MCP stdio/HTTP adapters, record/replay/validate/compare and baseline APIs/CLI, order-123 examples, strict and allow-list comparison, default redaction, JSON/JUnit output, offline CI, packaging, API/architecture/limitations documentation, MIT license, and CHANGELOG. It intentionally does not include a dashboard, general scorer platform, model calls, or framework-specific integrations.

## Remaining compatibility boundary

The bundled fixture is a deliberately narrow 2025-11-25 test server, not a full conformance implementation. The client supports the documented v1.6 stdio and Streamable HTTP subset, but OAuth negotiation, every optional MCP capability, the handshake-free 2026-07-28 protocol, and broad framework compatibility remain outside the current release line. Default tests stay offline. Claims-only mode is explicit structural comparison, not semantic judging or an LLM-based evaluator.
