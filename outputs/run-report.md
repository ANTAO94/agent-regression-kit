# Agent Regression Kit v2.6 verification

Verified on 2026-09-18 with Python 3.9.6.

## Results

- Runtime: Python 3.9.6.
- Unit and integration tests: 84 passed, 0 failed.
- Wheel build: `agent_regression_kit-2.6.0-py3-none-any.whl` succeeded.
- Scenario path coverage: observed and missing branch reports passed.
- Multi-turn session record/compare and outcome-aware path coverage passed.
- Session state continuity and claims-based business branch coverage passed.
- Snapshot/restore isolation: passed for in-memory fixtures, external state
  adapters, multi-turn sessions, and exceptional Agent exits.
- External state backend example: passed; the recorded mutation was visible in
  the Trace and the test store returned to its original state.
- Agent Contract Testing: passed assertions, nested ignore paths, normalizers, required/forbidden tools, step limits, allowed paths, isolated world state, and side-effect checks.
- Config preflight validation: passed for single-case and batch config shapes.
- Documentation QA: bilingual getting-started guides, Mermaid onboarding flow,
  and README navigation added.
- Batch config comparison: passed with project-relative directories and Markdown report output.
- GitHub Action policy forwarding: passed for final-answer mode and exact allow paths.
- Config-driven comparison: passed with scaffold-compatible `.agent-regression/config.json`.
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

The implementation contains AgentTrace v0.1, deterministic and MCP stdio/HTTP adapters, record/replay/validate/compare and baseline APIs/CLI, order-123 examples, strict and allow-list comparison, default redaction, JSON/JUnit output, offline CI, snapshot/restore isolation for internal and external test state, packaging, API/architecture/limitations documentation, MIT license, and CHANGELOG. It intentionally does not include a dashboard, general scorer platform, model calls, or framework-specific integrations.

## Remaining compatibility boundary

The bundled fixture is a deliberately narrow 2025-11-25 test server, not a full conformance implementation. The client supports the documented v2.6 stdio and Streamable HTTP subset, but OAuth negotiation, every optional MCP capability, the handshake-free 2026-07-28 protocol, and broad framework compatibility remain outside the current release line. Default tests stay offline. Contract assertions, state snapshots, session continuity, snapshot/restore isolation, path coverage, business branch coverage, and normalizers are deterministic; claims-only mode is explicit structural comparison, not semantic judging or an LLM-based evaluator. An external `SnapshotBackend` can only restore state it exposes; unrelated service writes still require project-specific cleanup.
