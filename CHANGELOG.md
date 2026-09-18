# Changelog

## Unreleased

## 2.9.0 - 2026-09-18

- Add `AsyncAgentAdapter`, `AsyncCallableAgentAdapter`, and explicit async
  recording APIs for Agents that call tools concurrently.
- Record stable async event order with `call_id`, parallel-group metadata, and
  comparable execution-concurrency evidence while preserving AgentTrace v0.1.
- Add `async-record`, async Markdown reporting, an offline async example, and
  tests for delayed completion, awaitable execution, and group regressions.
- Update package, CLI, MCP client identity, scaffold Action tag, and bilingual
  documentation to v2.9.0.

## 2.8.0 - 2026-09-18

- Add repeated-run stability evaluation with pass-rate, claims-match-rate,
  tool-error-rate, and tool-path-variant thresholds.
- Add `StabilityPolicy`, `StabilityReport`, `evaluate_stability`, and
  `record_stability` APIs built on state isolation and parallel scenario runs.
- Add the `stability` CLI command with JSON, Markdown, and JUnit output plus
  explicit claims-only and allow-list comparison controls.
- Add stability examples, six tests, and bilingual documentation for
  non-deterministic Agent behavior.
- Update package, CLI, MCP client identity, scaffold Action tag, and reports
  to v2.8.0.

## 2.7.0 - 2026-09-18

- Add `CallableAgentAdapter` to wrap framework-owned `invoke`/`run` callbacks
  without repeating the AgentAdapter boilerplate.
- Add `ScenarioCase`, `ScenarioResult`, `ScenarioBatchResult`, and
  `record_scenario_batch` for bounded parallel recording with fresh per-case
  factories, state isolation, failure collection, and deterministic ordering.
- Add the `batch-record` CLI command for recursively recording JSON scenarios
  into a Trace directory and CI-friendly batch summary.
- Add parallel recording and framework bridge examples plus five tests.
- Update package, CLI, MCP client identity, scaffold Action tag, and bilingual
  documentation to v2.7.0.

## 2.6.0 - 2026-09-18

- Add the `SnapshotBackend` protocol and `StateIsolation` context manager for
  deterministic snapshot/restore boundaries around mutable test state.
- Add `isolated_record_run` and `isolated_record_session`, restoring state after
  successful or failed Agent execution while preserving state between turns.
- Extend `WorldState` and `StatefulFixtureTools` with explicit restore support
  and a convenient isolation context.
- Add an offline external-state backend example, five isolation tests, and
  bilingual API, architecture, usage, and limitation documentation.
- Update package, CLI, MCP client identity, scaffold Action tag, and validation
  records to v2.6.0.

## 2.5.0 - 2026-09-18

- Add multi-turn world-state continuity checks with explicit
  `session_state_discontinuity` failures.
- Add business-branch coverage from structured claims with expected branch
  gates and report summaries.
- Extend coverage JSON, Markdown, JUnit, CLI, and API outputs for business
  result branches.
- Add tests and documentation for state continuity and claims-based coverage.

## 2.4.0 - 2026-09-18

- Add validated multi-turn `AgentSession` evidence and session comparison.
- Add `session-record` and `session-compare` CLI commands plus Markdown/JUnit
  session reports.
- Add `ScriptedSessionAdapter` and shared-state `record_session` support.
- Add outcome-aware path coverage with `--include-outcomes`, distinguishing
  `tool[ok]` from `tool[error]` branches.
- Add a two-turn order-session fixture and bilingual documentation.

## 2.3.0 - 2026-09-18

- Add `coverage` reporting for observed and missing ordered Agent tool paths.
- Add JSON, Markdown, and JUnit coverage output with a non-zero exit code for
  missing expected branches.
- Add a reusable GitHub Action for scenario-path coverage gates.
- Add API and bilingual documentation for scenario-suite coverage.

## 2.2.0 - 2026-09-18

- Add state-isolated `WorldState` and `StatefulFixtureTools` for deterministic
  business scenarios with mutable external state.
- Capture initial and final world snapshots in recorded traces when the tool
  executor exposes `snapshot()`.
- Add field-level `state_change` reporting, side-effect contracts, and
  `path_rules.any_of` for multiple valid Agent tool paths.
- Add scenario tests covering state isolation, mutations, allowed alternatives,
  and dangerous-path rejection.

## 2.1.0 - 2026-09-18

- Add `ContractPolicy` for deterministic Agent behavior contracts.
- Add field assertions with `equals`, `contains`, and `exists` operators.
- Add nested `ignore_paths` with `[*]` support and timestamp/list normalizers.
- Add required/forbidden tool rules and maximum tool-call step limits.
- Preserve all contract violations in comparison reports and config-driven CI flows.

## 2.0.0 - 2026-09-17

- Add `config validate` for preflight validation of single-case and batch
  comparison configuration files.
- Establish the v2.0 configuration contract with normalized project-relative
  paths and explicit `single`/`batch` config shapes.
- Add complete bilingual getting-started guides, Mermaid onboarding diagrams,
  and clearer README navigation.
- Keep the v1.x Trace schema and comparison APIs compatible.

## 1.9.0 - 2026-09-17

- Add `batch-compare --config` for directory-based multi-case comparisons.
- Reuse project-relative reports, policies, formats, and redaction settings for
  both single-case and batch comparison commands.

## 1.8.0 - 2026-09-17

- Add GitHub Action inputs for `final-answer-mode` and comma-separated exact
  `allow-path` values.
- Keep the reusable Action behavior aligned with the local `compare` CLI.

## 1.7.0 - 2026-09-17

- Add `compare --config` for project-level JSON configuration.
- Make `agent-regression init`'s generated baseline, candidate, report, format,
  comparison policy, and redaction settings usable without repeating CLI flags.
- Keep explicit command-line values higher priority than config-file defaults.

## 1.6.0 - 2026-09-17

- Add `ComparisonPolicy.final_answer_mode` with `exact` and `claims-only` modes.
- Add CLI support for `--final-answer-mode` on `compare` and `batch-compare`.
- Keep structured claims, tool calls, arguments, and results strict while allowing
  model-generated final prose to vary explicitly in `claims-only` mode.

## 1.5.0 - 2026-09-17

- Add `batch-compare` for comparing matching Trace cases across baseline and candidate directories.
- Add aggregate JSON, Markdown, and JUnit batch reports with missing-case detection.

## 1.4.0 - 2026-09-17

- Add custom HTTP header support to the Streamable HTTP client and MCP HTTP recorder.
- Add repeatable CLI `--header 'Name: value'` options to `mcp-http-record` and `mcp-smoke`.
- Add authenticated-request coverage for the HTTP fixture.

## 1.3.0 - 2026-09-17

- Add Markdown comparison reports through `--format markdown` and `render_markdown`.
- Add GitHub Actions job-summary output to the reusable comparison action while preserving the original comparison exit code.

## 1.2.0 - 2026-09-17

- Add `agent-regression init` to scaffold a first-use integration project with a runnable Agent example, baseline guidance, configuration, and GitHub Actions workflow.
- Add safe repeatable scaffolding with skip-by-default behavior and an explicit `--force` overwrite option.
- Update the package and MCP client identity to version 1.2.0.

- Add MCP Streamable HTTP capture with session propagation and JSON/SSE response decoding.
- Add bounded GET SSE event-stream iteration for server notifications and requests.
- Add explicit JSON-RPC responses for server-initiated HTTP requests.
- Add MCP resources and prompts request helpers plus deterministic fixture coverage.
- Add bounded concurrent HTTP tool calls with thread-local request IDs and input-order results.
- Add pagination iterators, cancellation notifications, and client reconnect helpers for stdio and HTTP.
- Add resumable SSE streams with `Last-Event-ID`, progress filtering, and callback-driven server-request responses.
- Add optional `mcp-smoke` compatibility checks for advertised tools, resources, and prompts.
- Add stdio Content-Length framing support and a manual GitHub Actions workflow for the official Everything Server.
- Add client capability injection, controlled server-request handlers, and explicit MCP task query/cancel helpers.
- Extend compatibility smoke discovery to advertised task capabilities.
- Add task-augmented `tools/call` requests and incremental HTTP SSE response handling for in-band sampling/elicitation requests.
- Add `mcp-http-record` CLI command and HTTP end-to-end fixture tests.
- Add a reusable local GitHub Actions comparison action and update the CI example to use it.
- Add a rule-driven order Agent that chooses and calls the MCP fixture tool,
  then produces its answer and claims from the actual result.
- Add controlled parameter-regression and result-misread variants with
  end-to-end record, replay, and comparison coverage.

## 1.0.0 - 2026-09-17

- Added stable AgentTrace v0.1 recording, validation, replay, and structural comparison.
- Added strict comparison with category/path allow-lists and CI exit codes.
- Added deterministic scripted and fixture executors.
- Added project-owned MCP 2025-11-25 stdio fixture, client capture, normal/error/timeout paths, and stable request-ID evidence.
- Added default recursive redaction and configurable literal-secret removal.
- Added JSON and JUnit reports, baseline acceptance/show commands, and an offline GitHub Actions example.
- Added packaging, architecture/API/limitations documentation, examples, and offline automated tests.

Compatibility note: AgentTrace remains schema version `0.1`. Existing v0.1 traces and record/replay/compare commands remain supported; new comparison reports add policy and blocking-difference fields.
