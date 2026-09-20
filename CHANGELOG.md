# Changelog

## Unreleased

## 4.6.0 - 2026-09-20

- Add explicit `path_rules.mode` values for exact paths, ordered subsequences and unordered subsets.
- Allow safe extra observational queries without weakening required tools, forbidden tools, step limits or business Contracts.
- Add a bilingual path-variation example, negative cases and a dedicated GitHub Actions evidence workflow.
- Add v4.6 acceptance, upgrade guidance and documentation for choosing strict versus tolerant path matching.

## 4.5.0 - 2026-09-20

- Add deterministic cross-step Contract relations for comparing values between Agent tool calls, tool results and business state.
- Add a complete offline refund business case with a reviewed baseline, reusable contract, four injected defects and a dedicated CI workflow.
- Add bilingual guidance for business contracts, relation operators, evidence boundaries and the first external-user acceptance path.

## 4.4.1 - 2026-09-20

- Pass the generated SPDX filename to `actions/attest` as an exact step output; the v4.4.0 tag failed closed before release creation because `sbom-path` does not expand globs.

## 4.4.0 - 2026-09-20

- Add SHA-256 release checksums and an SPDX 2.3 release SBOM generated without third-party runtime dependencies.
- Add signed SLSA provenance and SBOM attestations to tagged GitHub releases.
- Add bilingual vulnerability reporting, community conduct, issue templates and weekly dependency updates.
- Upgrade official GitHub Actions to their Node 24-based v7 releases and fix stale limitations-version documentation.

## 4.3.0 - 2026-09-20

- Surface real PydanticAI, OpenAI Agents, LangGraph, LangChain Core and hosted DeepSeek evidence prominently in the bilingual README.
- Distinguish deterministic real-framework runs from paid live-provider runs and document the verified negative regression boundary.
- Add deterministic DeepSeek multi-tool sequences while keeping model-generated arguments observable.
- Verify live cross-step order status and amount propagation with a reviewed baseline and strict Contract.
- Add a wrong-dependent-argument regression test and run both paid scenarios in the weekly credential-gated workflow.

## 4.2.0 - 2026-09-20

- Add a dependency-free `deepseek-flash` tool-Agent runner with strict Trace evidence.
- Add offline provider-shape tests and a credential-gated weekly live regression workflow.
- Document low-cost local and GitHub Secret setup without persisting provider credentials.

## 4.1.0 - 2026-09-20

- Rewrite the bilingual README around installation, policy configuration, Agent integration and CI.
- Add bilingual technical design and user manuals with explicit replay, SDK, contract and security boundaries.
- Add a runnable quickstart comparison policy and include the new manuals in wheel documentation assets.
- Correct conflicting MCP limitations and stale adapter-template test instructions.
- Harden v4 boundaries: review, compare and migration outputs cannot overwrite their source documents.
- Reject unknown contract/config fields and unsupported report types instead of silently accepting typos.
- Treat run-scoped tool call IDs as correlation metadata, validate duplicate IDs, and require boolean report status values.
- Add result adapters and offline real-runtime examples for PydanticAI, OpenAI Agents SDK and LangGraph.
- Add optional framework extras and a Python 3.11 compatibility job that validates all three generated traces.
- Prove cross-framework equivalence and require a real LangGraph parameter regression to fail in CI.

## 4.0.0 - 2026-09-19

- Promote the documented public Python API generation to v4 and expose explicit
  Trace, Session, Contract/config and Report compatibility boundaries.
- Add read-only `compatibility` checks with deprecation reporting for v3
  integrations and unsupported-schema failures.
- Add non-destructive `migrate trace` output and migration reports; AgentTrace
  schema `0.1` remains unchanged and is currently a validated no-op migration.
- Add the v4 acceptance contract and release-workflow checks for compatibility,
  migration, workspace manifests, Viewer assets and clean wheel installation.
- Complete bilingual API, technical-design, user-manual, compatibility and
  upgrade documentation for the v4 local/CI-first maturity boundary.

## 3.9.0 - 2026-09-19

- Add `workspace manifest` to fingerprint policy, baseline, candidate/run and
  report files using relative paths, sizes and SHA-256 without embedding data.
- Add read-only `baseline review` so teams can compare a candidate explicitly
  before deciding whether a baseline change is intentional.
- Add the local Workspace Viewer page with role filtering, path search, theme
  support and an explicit file-selection security boundary.
- Package the Workspace Viewer and link it from the Trace, configuration and
  report pages.

## 3.8.0 - 2026-09-19

- Add `FrameworkTraceRecorder` and `record_framework_run` for framework-owned
  tool-start, tool-end and final-answer callback lifecycles.
- Preserve explicit call_id correlation and out-of-order tool completion while
  validating that every tool call closes before the final answer.
- Add a real LangChain Core `RunnableLambda` event-ingestion example and run it
  in the optional framework compatibility matrix without provider credentials.

## 3.7.0 - 2026-09-19

- Align tool results by `call_id` by default to avoid false regressions when
  parallel result events arrive in a different order.
- Add `result_alignment=order` as an explicit legacy compatibility mode.
- Extend `path_rules.any_of` entries with exact result and `is_error` checks,
  making accepted paths constrain both the action and its observed outcome.
- Expose result alignment in project config, CLI and the reusable Action.

## 3.6.0 - 2026-09-18

- Add strict `CassetteToolExecutor` and `replay_agent_run` APIs for replaying
  an Agent against recorded tool results without calling live tools.
- Add structured mismatch diagnostics for changed tool names/arguments,
  extra calls, and Agents that stop before consuming the cassette.
- Add `replay-run` for a deterministic scripted acceptance path while keeping
  the existing `replay` command read-only and evidence-only.

## 3.5.0 - 2026-09-18

- Add `required_claims` contract checks so a candidate cannot pass by omitting
  a required structured business conclusion.
- Add required report/glob completeness gates to `report-index` and the
  reusable Report Index Action.
- Let the comparison Action consume a project `config` file, including its
  contract and comparison policy, while preserving the legacy path inputs.
- Make the core workflow exercise both policy loading and required report
  completeness with deterministic error-injection coverage.

## 3.4.3 - 2026-09-18

- Complete the unified CI evidence flow: compare, stability, coverage, and
  history reports now share `work/ci-reports/` and the Report Index Job
  Summary handoff in the main workflow.
- Make `agent_report_index` recognize history aggregate reports with safe
  summary metrics, and add coverage for this report type.

## 3.4.2 - 2026-09-18

- Fix the tag-triggered release workflow so its source-tree test suite receives
  the `src` import path before the clean-wheel verification.
- Add a CI regression test for the release workflow's source-test boundary.

## 3.4.1 - 2026-09-18

- Isolate the core GitHub workflow's generated reports under
  `work/ci-reports` so committed historical output fixtures cannot contaminate
  the current report index.
- Install explicit `pip`, `setuptools`, and `wheel` build tooling in the
  Python matrix and skip report indexing when package installation failed.

## 3.4.0 - 2026-09-18

- Add a reusable `agent-report-index` GitHub Action that writes JSON and
  Markdown indexes, appends the Markdown to Job Summary, and can gate a report
  directory with `--fail-on-regression`.
- Extend the coverage Action with a machine-readable JSON report so coverage
  evidence can share the same report directory as compare and history output.
- Update the generated project workflows and bilingual CI documentation with
  the unified report handoff.

## 3.3.1 - 2026-09-18

- Connect the configuration center to the Report Index handoff so users can
  follow the complete local flow from policy export to report review.
- Append the generated report index to the GitHub Actions Job Summary while
  retaining JSON, Markdown, and JUnit artifacts.

## 3.3.0 - 2026-09-18

- Add `report-index` to build a redacted, relative-path inventory of compare,
  batch, stability, and coverage JSON reports for CI handoff.
- Add the local Viewer Report Index page and package it with source and wheel
  distributions; it keeps navigation separate from the full Trace/Diff view.
- Extend the reusable GitHub Action with a machine-readable JSON report and
  publish JSON/Markdown report-index artifacts in the core workflow.

## 3.2.2 - 2026-09-18

- Include the bilingual getting-started guide, upgrade guide, and compatibility
  matrix in wheel documentation assets and verify them after clean install.

## 3.2.1 - 2026-09-18

- Add the v3.2 upgrade guide and an explicit Python/framework/MCP compatibility
  matrix for release review.
- Add Python 3.9/3.11/3.13 CI coverage and preflight comparison inputs across
  the core regression matrix.
- Harden output redaction for the `secret_values` configuration field so
  `config`/`check` reports do not echo configured secrets.

## 3.2.0 - 2026-09-18

- Add a loopback-only `agent-regression ui` command for the local Trace
  Inspector and configuration viewer.
- Package the static Viewer assets with source distributions and wheel data
  files, and add CLI/path-discovery tests for installed and checkout layouts.
- Centralize the package version and add a tag-triggered build-and-verify
  release workflow with clean-wheel installation checks.
- Add a side-effect-free `check` command that validates configured Trace
  inputs, batch file-set symmetry, and AgentTrace schema before comparison.
- Add a dependency-free framework callback example and make `agent-regression
  init` place the preflight step before the generated CI comparison.
- Add sync/async Adapter Contract Diagnostic helpers with structured identity,
  Trace, tool-path, and claims failure details.
- Add an explicit public API manifest and independent Trace schema compatibility
  boundary, with tests that protect all declared public exports.
- Add an optional LangChain Core callback example that runs without model
  credentials and is isolated from the default dependency-free test suite.
- Add a Python 3.9/3.11/3.13 framework-compatibility workflow and schedule the
  official MCP compatibility smoke workflow weekly.

## 3.1.0 - 2026-09-18

- Add `HistoryPoint`, `HistoryReport`, and `build_history_report` for offline
  aggregation of stability, compare, batch, and coverage reports.
- Add first/latest/min/max/delta trend metrics, current latest-status gating,
  skipped-file diagnostics, and Markdown/JUnit historical reports.
- Add the `history` CLI command and versioned example report fixtures for
  long-term regression review in CI or release checklists.
- Update package, CLI, MCP client identity, scaffold Action tag, and bilingual
  documentation to v3.1.0.

## 3.0.0 - 2026-09-18

- Add the `AdapterSpec` integration SDK for building sync and async adapters
  with one stable Agent identity and the existing context contracts.
- Add `adapter-init` templates for sync, async, or dual-mode framework
  integrations, including bilingual instructions and runnable offline contract
  tests.
- Add template and SDK tests, CLI generation checks, and package exports.
- Update package, CLI, MCP client identity, scaffold Action tag, and bilingual
  documentation to v3.0.0.

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
