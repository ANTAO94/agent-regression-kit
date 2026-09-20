# Changelog

## Unreleased

## 4.29.0 - 2026-09-21

- Add a provider-neutral `study` command and `evaluate_sampling_study` API for
  evaluating recorded repeated runs with explicit provider/model, input hash,
  tool-schema hash and sampling-parameter provenance.
- Reject secret-like provenance fields and path escapes, bind each manifest run
  ID to its Trace, and keep raw prompts/API keys outside the report boundary.
- Add a deterministic recorded-study example and a required core CI report;
  keep the evidence boundary explicit: observed samples are not a population
  reliability or online-model-quality claim.

## 4.28.0 - 2026-09-21

- Add Wilson 95% intervals and explicit finite-sample warnings to repeated-run
  stability reports.
- Add `StabilityPolicy.min_runs` and the `stability --min-runs` CLI gate so a
  project can reject under-sampled evidence without changing the default
  compatibility behavior.
- Run a 30-repeat sampling-boundary smoke in the core CI and keep the boundary
  explicit: this is uncertainty reporting over observed runs, not an online
  model-quality or population-reliability claim.

## 4.27.0 - 2026-09-21

- Add a four-suite AgentDojo matrix from the independent
  `claude-3-5-sonnet-20241022` pipeline, with explicit Contract provenance and
  expected outcomes.
- Add a Claude-model CI job that validates the pinned results, repeats the
  decision three times and uploads redacted Trace/report artifacts.
- Keep the boundary explicit: one pinned Claude pipeline expands model-family
  evidence but is not online sampling research or universal generalization.

## 4.26.0 - 2026-09-21

- Add a four-case `ignore_previous` AgentDojo attack-family matrix across
  workspace, banking, slack and travel, with explicit expected Contract
  outcomes and canonical Contract hashes.
- Add an attack-family CI job that validates the new cases, repeats the fixed
  decision three times and uploads the complete evidence artifact.
- Add bilingual v4.26 acceptance documentation and keep the boundary explicit:
  one pinned gpt-4o pipeline is attack-type coverage, not a security rate or
  universal cross-model generalization claim.

## 4.25.0 - 2026-09-21

- Add a repeatability validator for the pinned AgentDojo matrix that runs the
  decision pipeline three times and compares aggregate, per-case and Trace
  SHA-256 artifacts.
- Add an independent-source repeatability CI job and focused tests, while
  keeping the boundary explicit: deterministic exported-input reproducibility
  is not online model sampling-variance evidence.
- Add bilingual v4.25 acceptance documentation and retain the v4.24 Contract
  pre-registration and consumer evidence.

## 4.24.0 - 2026-09-21

- Add Contract pre-registration to the independent matrix validator through
  canonical-JSON SHA-256 bindings and a `frozen_before_oracle` manifest claim.
- Fail closed when a pre-registered Contract is missing or modified, and emit
  Contract provenance checks in per-case and aggregate reports.
- Add the v4.24 cross-model matrix manifest and CI validation, preserving the
  four positive controls and four expected attack blocks from v4.23.
- Add bilingual acceptance documentation and focused tamper-detection tests;
  keep external utility/security labels separate from Contract evaluation.

## 4.23.0 - 2026-09-21

- Add an eight-case AgentDojo cross-model attack matrix covering four
  gpt-4o direct-path baselines and four gpt-4o-mini `important_instructions`
  attack paths across workspace, banking, slack and travel.
- Allow a matrix case to declare `expected_contract_passed: false`, so an
  expected unsafe trajectory is accepted only when the reviewed Contract
  actually blocks it; a failed Contract is never silently treated as a pass.
- Add per-case pipeline metadata checks, cross-model CI evidence, expected vs
  observed block counts and a bilingual v4.23 acceptance record.
- Preserve the evidence boundary: AgentDojo utility/security labels remain an
  external oracle and the pinned exported runs are not a full rerun or a
  universal security/generalization claim.

## 4.22.0 - 2026-09-21

- Add a five-case AgentDojo independent-source matrix across workspace,
  banking, slack and travel suites, including direct and ignore-previous paths.
- Add per-case Contract, source metadata, result SHA-256, oracle-boundary checks,
  redacted Trace/report artifacts and an aggregate matrix gate.
- Run the matrix in CI without deriving Contracts from upstream utility/security
  labels; keep the matrix explicitly scoped to exported-run integration evidence.
- Add bilingual v4.22 acceptance documentation and focused matrix regression tests.

## 4.21.0 - 2026-09-21

- Add an AgentDojo bridge that converts exported runs to validated AgentTrace
  without copying upstream utility/security labels into evidence or Contracts.
- Support both string-function and object-function AgentDojo tool-call shapes,
  plus required/forbidden tool Contract checks and source SHA-256 binding.
- Add an immutable AgentDojo independent-source CI smoke, report/Trace artifact,
  bilingual v4.21 acceptance record and focused regression tests.
- Keep the evidence boundary explicit: one pinned run is an integration smoke,
  not a full AgentDojo benchmark or universal security/generalization claim.

## 4.20.0 - 2026-09-21

- Add `split_tau2_payload_by_task`, a label-independent SHA-256 task-ID split
  helper that returns disjoint calibration and holdout payloads with task-set
  digests.
- Add a reproducible telecom task-disjoint holdout validator and checked-in
  split definition. The published holdout records 47/53/0/0 over 100 eligible
  simulations; the prospective o4-mini holdout records 50/46/4/0 with 100%
  failure recall and 7.41% false-alarm rate.
- Add holdout-specific CI jobs, sample Trace artifacts, bilingual reproduction
  guidance and an explicit boundary: this is a task-level holdout proxy from
  the same public task family, not universal unseen-domain generalization.
- Record 250 passing local tests and preserve the v4.19 independent consumer
  wheel evidence.

## 4.19.0 - 2026-09-21

- Add an actor-aware τ²-bench telecom adapter: assistant-owned tool calls are
  evaluated as Agent behavior, while simulator/user-owned tool calls remain
  environment evidence instead of being mistaken for Agent actions.
- Add telecom-specific environment assertions for service status, mobile data,
  speed, MMS, data refueling and overdue-bill evidence, with explicit
  termination-step diagnostics.
- Add checksum-bound published and prospective telecom validation manifests,
  reproducible commands, sample Trace export and four telecom CI jobs alongside
  the existing retail and airline evidence.
- Record v4.19's cross-domain calibration and prospective results honestly:
  364 eligible scenarios, 147/217/0/0 on the pinned published file; and
  136/216/9/3 on the prospective o4-mini file under an explicit relaxed
  observation threshold. These are scoped evidence, not universal guarantees.

## 4.18.0 - 2026-09-21

- Add `path_rules.ignore_argument_paths` for explicit transport-noise filtering:
  fields omitted from the baseline rule may vary, while explicitly declared
  business fields remain strict.
- Add a domain-specific τ²-bench airline importer, Contract builder and
  checksum-bound validation workflow alongside the retail evidence.
- Validate the pinned published airline result: 120 eligible write scenarios,
  69 oracle failures, 100% failure recall and 3.92% false-alarm rate.
- Add a prospective o4-mini airline report with an explicit 12% observation
  threshold because its measured false-alarm rate is 10.42%; do not interpret
  that threshold as the general maturity target.
- Add bilingual v4.18 acceptance, airline reproduction instructions and
  configuration guidance.

## 4.17.0 - 2026-09-21

- Bind the τ² result file to the source manifest SHA-256 before writing a
  validation report, preventing metrics from one model being described as
  another model's dataset.
- Add explicit `--min-failures` gating and report the observed result and
  manifest hashes as provenance.
- Add a prospective o4-mini retail evaluation manifest and CI job: 420
  eligible scenarios, 126 oracle failures, 100% failure recall and 2.04%
  false-alarm rate under the release gate.
- Keep the evaluation boundary honest: this is a model-held-out result file
  over the same task family, not a claim of unseen-domain generalization.

## 4.16.0 - 2026-09-21

- Make `agent-regression init` a runnable first-use project: it seeds a
  deterministic baseline and candidate, a strict Contract, bilingual starter
  instructions and intentional `wrong-resource`, `skip-tool` and
  `misread-result` variants.
- Pin generated GitHub Actions to the installed release tag instead of the
  moving `main` branch.
- Add preflight `guidance`/`next_actions` for missing Contracts, relaxed paths,
  missing state evidence and the next comparison command.
- Add report-level `next_actions` that turn blocking difference categories into
  concrete debugging steps.
- Add dependency-free `performance run` and `performance gate` commands,
  weekly/smoke CI and a v4.16 acceptance record.
- Upgrade the independent consumer pilot to the v4.15.0 Release wheel and
  verify the normal path plus three injected regressions in its own CI.

## 4.15.0 - 2026-09-21

- Add the independent consumer repository
  `ANTAO94/agent-regression-pilot`, which installs only the v4.14.0 Release
  wheel and uses the public API/CLI from a separate project.
- Verify three consumer-side injected regressions: wrong resource ID, skipped
  required tool and incorrect result interpretation; each blocks with exit code
  1 while the normal run passes with exit code 0.
- Record the consumer wheel URL, SHA-256, fixed commit and CI workflow in a
  bilingual acceptance document instead of copying consumer code into the core
  repository.
- Keep the external acceptance boundary explicit: this is one deterministic
  consumer project, not automatic compatibility with every Agent framework.

## 4.14.0 - 2026-09-20

- Add a dependency-free benchmark manifest with immutable source/revision,
  split, evidence, Contract bundle, label and release provenance hashes.
- Add `benchmark prepare`, `benchmark decide` and `benchmark score` so
  evidence decisions are completed before labels are read for scoring.
- Reject moving source revisions, mismatched sample/Contract IDs, stale input
  hashes and modified decision payloads; keep unsupported samples explicit in
  score reports.
- Add confusion-matrix metrics with Wilson 95% intervals and bilingual
  benchmark-governance documentation.
- Keep the pinned τ²-bench result classified as calibration evidence; v4.14
  does not claim that same-dataset replay is a held-out generalization score.

## 4.13.0 - 2026-09-20

- Harden state-equivalence action matching with an explicit `attempt_policy`:
  a failed expected call cannot satisfy a required successful action, failed
  retries can be bounded, and missing success evidence is reported as
  `required_success_missing`.
- Add `state_scope` modes for declared outcomes, declared outcomes plus an
  unchanged remainder, and full world-state comparison; unexpected undeclared
  state changes are reported as `unexpected_state_change`.
- Report missing declared state evidence as `state_evidence_missing` instead of
  silently treating an absent outcome path as equivalent.
- Preserve v4.12 `allow_failed_expected` behavior as an explicit compatibility
  path while surfacing migration diagnostics from `config` and `check`.
- Add v4.13 configuration-center controls, bilingual acceptance evidence,
  migration guidance and negative contract tests.
- Re-run the pinned independent τ²-bench retail dataset: 420 eligible write
  scenarios, 267 true passes, 153 true blocks, 0 false alarms and 0 missed
  failures.

## 4.12.0 - 2026-09-20

- Add explicit `contract.state_equivalence` modes: `exact`, `outcome` and `hybrid`.
- Allow outcome contracts to group documented alternative intents, ignore selected
  routing/selection arguments, tolerate failed attempts when explicitly configured,
  and recognize configured idempotent repeats without weakening exact action matching.
- Compare declared final-state paths as business outcomes and avoid treating
  transport result noise as a regression in outcome mode.
- Re-run the pinned independent τ²-bench retail dataset: 420 eligible write
  scenarios, 267 true passes, 153 true blocks, 0 false alarms and 0 missed failures.
- Add bilingual state-equivalence guidance, v4.12 acceptance evidence and upgrade notes.

## 4.11.0 - 2026-09-20

- Add a dependency-free importer and deterministic Contract builder for published τ²-bench retail trajectories.
- Keep the upstream reward outside Trace, claims and Contract evaluation, then compute an honest external confusion matrix after each decision.
- Validate the pinned `v1.0.1` dataset: 420 write scenarios, 253 true passes, 153 true blocks, 14 false alarms and zero missed failures.
- Add SHA-256-pinned independent-project CI, exported sample traces, bilingual methodology, limitations and acceptance documentation.

## 4.10.0 - 2026-09-20

- Add scenario-level `contract.argument_rules` for deterministic tool-argument policies.
- Check every call of a named tool against literal values, Trace reference paths, `exists` and `absent` rules.
- Report violations with `tool_argument_policy`, the concrete call index and the observed/reference values.
- Add tenant/resource-boundary coverage to the refund business case, a bilingual v4.10 acceptance contract and configuration-center support.

## 4.9.0 - 2026-09-20

- Add scenario-level `contract.tool_allowlist` with explicit omission versus deny-all semantics.
- Support string rules, exact argument-scoped rules and `unauthorized_tool_call` diagnostics.
- Keep older contracts compatible when the allowlist is absent; add migration detection, refund-case coverage and bilingual acceptance documentation.

## 4.8.0 - 2026-09-20

- Add `contract.tool_limits` for per-tool minimum and maximum call counts.
- Support exact counts, argument-scoped counting and `tool_count` diagnostics.
- Strengthen the refund business case so duplicate refunds fail on count, path and step-limit evidence.
- Add bilingual v4.8 acceptance documentation and package/release checks.

## 4.7.0 - 2026-09-20

- Add optional `contract.path_rules.extra_calls` allowlists for tolerant path modes.
- Preserve v4.6 compatibility when `extra_calls` is omitted; support explicit `extra_calls: []` to reject all unmatched calls.
- Add `extra_tool_call` diagnostics with the observed call index and the configured allowlist.
- Add validation, bilingual acceptance documentation and a path-variation CI example for fail-closed extra-call checks.

## 4.6.1 - 2026-09-20

- Correct release-integrity instructions to verify wheel provenance and SPDX attestations with `gh attestation verify`.
- Remove the misleading tag-level `gh release verify` example, which does not verify the release assets produced by the workflow.

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
