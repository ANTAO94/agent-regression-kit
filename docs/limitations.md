# Limitations and security boundary

Agent Regression Kit v3.2 deliberately stays small. The local Viewer
is a read-only presentation layer, not a hosted management service.

- AgentTrace comparison is structural. `final_answer.claims` must be supplied by an adapter or scenario when deterministic result-interpretation checks are required. The kit does not infer facts from prose.
- Tool calls are aligned by event order, not by an optimal sequence-matching algorithm.
- The MCP client is synchronous at the lifecycle level, single-session, and pinned to the 2025-11-25 handshake. Stdio supports newline and Content-Length framing; Streamable HTTP supports JSON and SSE response bodies. HTTP GET SSE events can be read, resumed with `Last-Event-ID`, and recorded; server-initiated requests can be answered explicitly or through a caller callback. Resources, prompts, pagination, explicit cancellation, reconnect, progress filtering, and bounded concurrent HTTP calls are supported, but the generic AgentTrace recorder remains sequential. Sampling, elicitation, tasks, typed server-request routing, and the handshake-free 2026-07-28 protocol remain unsupported.
- The MCP client is synchronous at the lifecycle level, single-session, and pinned to the 2025-11-25 handshake. Stdio supports newline and Content-Length framing; Streamable HTTP supports JSON and SSE response bodies plus caller-supplied headers. HTTP GET SSE events can be read, resumed with `Last-Event-ID`, and recorded; server-initiated requests can be answered explicitly or through a caller callback. Resources, prompts, pagination, explicit cancellation, reconnect, progress filtering, bounded concurrent HTTP calls, task-augmented tool calls, and controlled sampling/elicitation request handling are supported. `async_record_run` adds parallel Agent tool events, but MCP client lifecycle concurrency, OAuth negotiation, every optional MCP capability, typed framework-specific routing, and the handshake-free 2026-07-28 protocol remain outside v2.9.
- The local MCP server is project-owned test infrastructure. It is not a conformance claim. Official Everything Server and conformance-suite checks remain optional external validation.
- `check` validates that configured Trace inputs are present and structurally valid; it does not prove that an Agent's business answer is correct. Use reviewed baselines, Contract assertions, claims, and scenario coverage for that boundary.
- The client applies a timeout and performs no automatic retries. This avoids repeating unknown side effects. A production adapter must make its own idempotency and retry decisions explicit.
- Default redaction recognizes common sensitive key names. Values embedded in free-form text require `--secret-value` or `RedactionPolicy(secret_values=...)`. Redaction reduces accidental leakage; it is not a data-loss-prevention system.
- An external MCP server runs as a local child process with the current user's permissions. Only run commands you trust. The bundled fixture performs no network or durable side effects.
- Baseline acceptance is explicit but unsigned. Review baseline changes in version control. `claims-only` final-answer comparison is also explicit: it ignores prose differences only when selected, and still requires structured claims to be present and equal. It is not semantic judging and does not infer claims from free-form text.
- Contract normalizers intentionally include only deterministic timestamp and list sorting rules in v2.8. World-state comparison and isolation are snapshot-based: `StateIsolation` restores only the database, cache, or service-emulator state exposed by the supplied `SnapshotBackend`; hidden writes to another service still require project-specific cleanup. Session comparison requires one terminal answer per turn; streaming conversation state is represented as separate turns, not a hidden live transcript. Business branch coverage depends on structured claims; it cannot infer a reliable business state from free-form prose. Arbitrary regex rewriting, model-based judging, and framework-specific semantic policies remain outside the core.
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
