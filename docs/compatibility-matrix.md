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
| MCP stdio | protocol `2025-11-25`; newline and Content-Length framing | offline fixture + official Everything Server smoke | The client is synchronous at lifecycle level. |
| MCP Streamable HTTP | JSON/SSE responses, session GET SSE, headers, pagination, cancellation, reconnect | HTTP fixture + official Everything Server smoke | OAuth negotiation and every optional capability are not promised. |
| Framework callback | sync and async `CallableAgentAdapter` / `AdapterSpec` | 132 core tests | Framework lifecycle and model provider remain integration-owned. |
| Framework events | `FrameworkTraceRecorder` / `record_framework_run` lifecycle bridge | Core tests + LangChain Core optional workflow | Framework must emit tool-start/end and final-answer callbacks with stable call IDs. |
| LangChain Core | `RunnableLambda` reference example; `langchain-core>=0.3,<2` | separate Python 3.9/3.11/3.13 workflow | Optional; no model key or provider is required by the example. |
| Viewer | local read-only Trace/Diff, Report Index, and configuration pages | HTML script/link check + wheel smoke | Python CLI remains the comparison source of truth. |
| CI | GitHub composite Actions and package workflows | workflow structure checks + GitHub execution | External official-server workflow is scheduled and manually runnable. |

## Compatibility policy

- Additive public symbols are allowed without changing `PUBLIC_API_VERSION`.
- Removing a documented symbol or changing its meaning requires a deprecation
  note in `CHANGELOG.md`, an upgrade entry, and a deliberate API-version
  decision.
- A Trace schema change must introduce an explicit schema version and a reader
  compatibility test; it must not silently reinterpret old fields.
- Optional framework integrations must remain outside the default dependency
  set and must declare their own Python and dependency range.
