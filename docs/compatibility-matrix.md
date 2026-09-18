# Compatibility Matrix

This matrix separates what the core package guarantees from optional or
external compatibility checks. “Supported” means covered by the repository's
tests or release workflow; it does not mean every framework behavior is
automatically captured.

| Surface | Supported boundary | Verification | Notes |
| --- | --- | --- | --- |
| Python | 3.9, 3.11, 3.13 | Core tests and framework workflow | The package uses no required third-party runtime dependency. |
| Package | source install and wheel install | Release workflow + clean venv | Viewer assets and MCP fixture are checked after install. |
| AgentTrace | schema `0.1` | runtime validation + compatibility tests | Product version and evidence schema are independent; tool results retain call_id association. |
| AgentSession | schema `0.1` | session tests | State continuity is explicit, not inferred. |
| Public Python API | v4 stable; v3 deprecated-readable | public API manifest + compatibility command | Documented imports are the names in `agent_regression.__all__`. |
| Contract/config | schema `0.1` | ContractPolicy validation + compatibility command | Existing configs use an implicit `0.1` boundary; unknown semantics are not silently accepted. |
| Reports | schema `0.1` with explicit `report_type` | renderer/index tests + compatibility command | Consumers should reject unsupported report schemas. |
| MCP stdio | protocol `2025-11-25`; newline and Content-Length framing | offline fixture + official Everything Server smoke | The client is synchronous at lifecycle level. |
| MCP Streamable HTTP | JSON/SSE responses, session GET SSE, headers, pagination, cancellation, reconnect | HTTP fixture + official Everything Server smoke | OAuth negotiation and every optional capability are not promised. |
| Framework callback | sync and async `CallableAgentAdapter` / `AdapterSpec` | 132 core tests | Framework lifecycle and model provider remain integration-owned. |
| Framework events | `FrameworkTraceRecorder` / `record_framework_run` lifecycle bridge | Core tests + LangChain Core optional workflow | Framework must emit tool-start/end and final-answer callbacks with stable call IDs. |
| LangChain Core | `RunnableLambda` reference example; `langchain-core>=0.3,<2` | separate Python 3.9/3.11/3.13 workflow | Optional; no model key or provider is required by the example. |
| Viewer | local read-only Trace/Diff, Report Index, configuration and Workspace review pages | HTML script/link check + wheel smoke | Python CLI remains the comparison source of truth; workspace files require explicit selection. |
| Workspace review | `workspace manifest` and `baseline review` | core tests + Viewer asset check | Manifest stores relative paths, sizes and SHA-256 only; review never mutates a baseline. |
| CI | GitHub composite Actions and package workflows | workflow structure checks + GitHub execution | External official-server workflow is scheduled and manually runnable. |
| Migration | Trace canonicalization and compatibility report | v4 release workflow + migration tests | Source files are never overwritten; Trace `0.1` is currently a validated no-op migration. |

## Compatibility policy

- Additive public symbols are allowed without changing `PUBLIC_API_VERSION`.
- Removing a documented symbol or changing its meaning requires a deprecation
  note in `CHANGELOG.md`, an upgrade entry, and a deliberate API-version
  decision.
- A Trace schema change must introduce an explicit schema version and a reader
  compatibility test; it must not silently reinterpret old fields.
- Optional framework integrations must remain outside the default dependency
  set and must declare their own Python and dependency range.
