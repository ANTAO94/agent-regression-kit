# Limitations and security boundary

Agent Regression Kit v4.22 deliberately stays small. The local Viewer
is a read-only presentation layer, not a hosted management service.

- AgentTrace comparison is structural. `final_answer.claims` must be supplied by an adapter or scenario when deterministic result-interpretation checks are required. The kit does not infer facts from prose.
- Tool calls are aligned by event order, not by an optimal sequence-matching algorithm.
- The MCP client is synchronous at the lifecycle level, single-session, and pinned to the 2025-11-25 handshake. Stdio supports newline and Content-Length framing; Streamable HTTP supports JSON and SSE response bodies plus caller-supplied headers. HTTP GET SSE events can be read, resumed with `Last-Event-ID`, and recorded; server-initiated requests can be answered explicitly or through a caller callback. Resources, prompts, pagination, explicit cancellation, reconnect, progress filtering, bounded concurrent HTTP calls, task-augmented tool calls, and controlled sampling/elicitation request handling are supported. `async_record_run` adds parallel Agent tool events, but MCP client lifecycle concurrency, OAuth negotiation, every optional MCP capability, typed framework-specific routing, and protocol revisions beyond the implemented handshake remain outside the current supported boundary.
- The local MCP server is project-owned test infrastructure. It is not a conformance claim. Official Everything Server and conformance-suite checks remain optional external validation.
- `check` validates that configured Trace inputs are present and structurally valid; it does not prove that an Agent's business answer is correct. Use reviewed baselines, Contract assertions, claims, and scenario coverage for that boundary.
- `contract.relations` compares only structured values already present in the candidate Trace. It can enforce cross-step equality and numeric bounds, but it cannot infer hidden model reasoning or decide whether free-form prose is truthful.
- `config` and `check` reports redact the configured `secret_values` field; free-form values still require an explicit `RedactionPolicy(secret_values=...)` or CLI `--secret-value` at the recording boundary.
- The client applies a timeout and performs no automatic retries. This avoids repeating unknown side effects. A production adapter must make its own idempotency and retry decisions explicit.
- Default redaction recognizes common sensitive key names. Values embedded in free-form text require `--secret-value` or `RedactionPolicy(secret_values=...)`. Redaction reduces accidental leakage; it is not a data-loss-prevention system.
- An external MCP server runs as a local child process with the current user's permissions. Only run commands you trust. The bundled fixture performs no network or durable side effects.
- Baseline acceptance is explicit but unsigned. Review baseline changes in version control. `claims-only` final-answer comparison is also explicit: it ignores prose differences only when selected, and still compares recorded claims. Integrators must ensure those claims are present and meaningful. It is not semantic judging and does not infer claims from free-form text.
- Contract normalizers intentionally include only deterministic timestamp and list sorting rules. World-state comparison and isolation are snapshot-based: `StateIsolation` restores only the database, cache, or service-emulator state exposed by the supplied `SnapshotBackend`; hidden writes to another service still require project-specific cleanup. Session comparison requires one terminal answer per turn; streaming conversation state is represented as separate turns, not a hidden live transcript. Business branch coverage depends on structured claims; it cannot infer a reliable business state from free-form prose. Arbitrary regex rewriting, model-based judging, and framework-specific semantic policies remain outside the core.
- `path_rules.ignore_argument_paths` is an explicit, path-local noise filter. It removes a field only when the baseline path rule does not declare it; it does not make an explicitly asserted payment ID, order ID or tenant ID arbitrary. The separate `state_equivalence.ignore_argument_paths` still only groups declared outcome intents.
- Scenario path coverage measures ordered tool-call paths represented by recorded
  traces. It is not source-code coverage, model-quality scoring, or proof that
  every hidden branch inside a framework was reached.
- `record_scenario_batch` uses bounded threads in one Python process. It requires
  each case to create an independent Agent and tool executor; it does not make a
  thread-unsafe framework safe, isolate process-global environment variables, or
  roll back an external service unless a `SnapshotBackend` is supplied.
- Stability evaluation is evidence-based, not a statistical guarantee. It only
  observes the requested repeat count, and `claims-only` still requires the
  adapter to emit structured claims. Repeats do not discover all possible model
  paths, and the default thresholds are intentionally strict rather than a
  universal reliability standard.
- Async recording captures explicit groups supplied by the adapter; it does
  not infer hidden framework tasks or make an unsafe tool executor concurrent.
  If a synchronous executor is used, calls are moved to worker threads, so
  thread safety, ordering-sensitive side effects, cancellation, and retries
  remain the integration's responsibility. Completion timestamps are not
  stored as deterministic evidence.
- `AdapterSpec` and `adapter-init` standardize the observable callback boundary
  but do not provide framework auto-discovery, lifecycle management, dependency
  injection, or language-native Spring/Java wrappers. The generated template
  still requires the project to connect its own Agent and ToolExecutor.
- History aggregation is file-based and order is defined by sorted relative
  paths. It does not deduplicate releases, infer timestamps, persist a
  database, or statistically estimate model reliability. The gate follows the
  latest recognized point; earlier failures are reported but do not by
  themselves make a later passing history command fail.
- The local Viewer reads user-selected JSON files in the browser. It does not
  recompute the Python comparison policy, execute Agents, edit baselines, or
  provide authentication, multi-user access, durable report storage, or
  network isolation beyond the CLI's loopback default.
- `contract.state_equivalence` is an explicit rule system, not semantic
  inference. `ignore_argument_paths` only groups rules already declared by the
  project; it does not allow arbitrary values. v4.13's strict
  `attempt_policy` requires successful evidence by default; failed retries must
  be explicitly allowed and bounded. The legacy `allow_failed_expected` field
  remains readable for compatibility but produces migration diagnostics.
  `tool_aliases` and `idempotent_tools` are opt-in and should be paired with
  negative cases. A declared `paths` value must be present in both baseline and
  candidate or the comparison fails closed. `state_scope=declared_only` does
  not inspect undeclared world-state fields; use
  `declared_and_unchanged_rest` or `full` when that boundary matters.
- The τ²-bench integration validates a checksum-pinned published half-duplex
  retail result file. It does not run the upstream simulator in core CI, cover
  voice or every domain, imply upstream adoption, or prove performance on a
  different model/version. v4.13's zero false alarms are measured on that one
  dataset and do not justify ignoring identifiers, tenants, amounts or resources
  in another project.
- The v4.14 benchmark manifest proves input provenance and separates decision
  from label scoring; it cannot make an openly published dataset genuinely
  unseen. `prepare` and `decide` still read the hashed label file metadata, but
  they do not parse label meaning. A real held-out claim requires that the
  Contract bundle be frozen before labels are accessed and that the process be
  independently reviewable.
- `performance run` measures deterministic Trace validation/comparison only.
  Its throughput and RSS values depend on Python, operating system and
  hardware; it is not a model-quality, tool-latency or production-capacity
  SLA. `performance gate` is meaningful only against a like-for-like baseline.
- `agent-regression init` provides a reproducible clean-room onboarding proxy,
  not a substitute for an uninvolved human usability study. The scaffold's
  baseline is generated from the bundled fixture and must still be reviewed
  before a real project commits it.
- The independent consumer pilot proves one released-wheel integration and its
  three injected regressions. It does not prove automatic compatibility with
  every Agent framework or programming language.
- The v4.17 prospective τ² result is bound to a separate published model file
  and adds a model-level evaluation signal. It shares the task family and
  oracle with calibration, so it is not unseen-domain generalization.
- The v4.18 airline validation adds a second task domain and reports 120
  eligible scenarios, but that slice is below the roadmap's 300-scenario final
  maturity threshold. Its prospective o4-mini false-alarm observation is
  10.42%, so the workflow records an explicit 12% model/domain threshold
  rather than presenting it as the general 5% target. An uninvolved human
  usability study is still required.
- The v4.19 telecom validation adds a third task domain with an explicit
  assistant/user actor boundary. It evaluates 364 assistant-write scenarios
  and excludes 92 user-only scenarios; user-owned results are environment
  evidence, not Agent actions. The environment parser covers only a bounded
  set of telecom assertions and does not reconstruct every hidden simulator
  state. Its prospective o4-mini observation is 98.63% failure recall, 6.21%
  false-alarm rate and 1.37% missed-failure rate under explicit 98%/10%/2%
  thresholds; this is not a universal quality guarantee or unseen-task
  generalization evidence.
- The v4.20 telecom holdout is a task-disjoint proxy, not an independent
  benchmark source. `split_tau2_payload_by_task` selects the 28 holdout tasks
  from 114 task IDs using a SHA-256 bucket rule and records set digests before
  evaluation; it does not read reward labels for selection. The published
  holdout has 100 eligible scenarios and yields 47/53/0/0, while prospective
  o4-mini yields 50/46/4/0 with a 7.41% false-alarm rate. Calibration and
  holdout still share the same public τ²-bench task family, so this evidence
  does not establish independent-source or universal unseen-domain
  generalization.
- The v4.21 AgentDojo bridge imports one checksum-pinned exported run and
  supports the observed string-function and object-function tool-call shapes.
  It checks a project-owned Contract while keeping AgentDojo's `utility` and
  `security` values as external oracle fields. It does not run AgentDojo's
  environment, recreate its model pipeline, validate every suite/attack, or
  establish a security rate; one `utility=true/security=false` sample is only
  an independent-source integration smoke.
- The v4.22 AgentDojo matrix expands that bridge to five exported runs across
  four suites and two attack-path labels. It proves cross-suite intake,
  per-case Contract and hash binding, and oracle/Trace separation; it still
  does not rerun the upstream environment, cover every model or attack, or
  establish security/generalization metrics. The per-case Contracts are
  manually reviewed path checks.
