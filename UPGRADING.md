# Upgrading Agent Regression Kit

This file records migration actions for released versions. The core rule is:
**upgrade the comparison tool before changing a reviewed baseline**. A package
upgrade must not silently turn a candidate difference into a new baseline.

## v4.5.0 → v4.6.0

This feature release adds the optional `contract.path_rules.mode` field. Existing
path contracts keep the strict `exact` behavior when the field is omitted, so no
Trace or configuration migration is required.

Use `ordered_subsequence` when a required sequence must remain ordered but a
new read-only query may appear before, between or after the required steps. Use
`unordered_subset` only when the business contract explicitly says that the
required calls may occur in any order. The tolerant modes do not remove the
need for `must_not_call`, `max_steps`, assertions, relations or side-effect
checks. See the [path variation example](examples/path-variation/README.md)
and [v4.6 acceptance contract](docs/v4.6-acceptance.md).

```json
{
  "contract": {
    "path_rules": {
      "mode": "ordered_subsequence",
      "any_of": [["get_order", "get_payment_status"]]
    },
    "must_not_call": ["delete_order"],
    "max_steps": 3
  }
}
```

`mode` values are `exact` (default), `ordered_subsequence` and
`unordered_subset`. `path_rules.ordered` remains available only for legacy
exact matching; it cannot be combined with a tolerant mode.

## v4.4.1 → v4.5.0

This feature release adds the `contract.relations` field. It is additive and
does not change the Trace schema or existing Contract fields. Existing
configurations continue to work without migration.

Relations make cross-step business rules explicit. For example, a project can
require a later refund amount to be less than or equal to the paid amount
returned by an earlier lookup. See the [user manual](docs/user-manual.en.md)
and the [refund business case](examples/refund-business-case/README.md).

The release also adds a complete offline case with a reviewed baseline and
four negative behaviors. Run the case before adapting it to a real framework.

## v4.3.0 → v4.4.1

This release changes packaging and repository governance, not Trace or public
Python API semantics. Existing Agent integrations and baselines require no
migration.

Tagged releases now contain `SHA256SUMS` and an SPDX 2.3 release SBOM. The
release workflow also creates signed SLSA provenance and SBOM attestations.
Consumers can continue installing the wheel normally, or verify it first using
the commands in [`docs/supply-chain.md`](docs/supply-chain.md).

Official checkout, Python setup and artifact-upload Actions move to their
Node 24-based v7 releases. Self-hosted GitHub Actions runners must satisfy the
minimum runner version required by those Actions.

The `v4.4.0` tag did not produce a GitHub Release because the SBOM attestation
gate rejected a glob path before asset upload. Use `v4.4.1`, which passes the
exact generated SBOM filename between workflow steps.

## v4.2.0 → v4.3.0

This feature release adds `required_tool_sequence` to the dependency-free
DeepSeek runner and a reviewed two-tool refund baseline. Existing
`force_first_tool` integrations continue to work unchanged. Do not set both
options in one call; they are intentionally mutually exclusive.

No Trace schema or public API generation migration is required. To adopt the
new path, add every tool definition and handler, then replace
`force_first_tool` with the exact sequence:

```python
trace = record_deepseek_tool_run(
    ...,
    required_tool_sequence=("get_order", "check_refund_eligibility"),
)
```

Set `max_rounds` to at least the number of required tools plus one final-answer
round. Keep a Contract that checks the dependent arguments; forcing tool order
alone does not prove that values were propagated correctly.

## v3.1.x → v3.2.0

### What changed

- The package version is read from one source: `agent_regression.__version__`.
- MCP `clientInfo.version` now follows the package version automatically.
- `agent-regression ui` serves the local Trace Inspector and configuration
  center. It binds to loopback by default and is read-only.
- `agent-regression check` validates a comparison config and its referenced
  Trace inputs before `compare` or `batch-compare` runs.
- `check_adapter_contract` and `check_async_adapter_contract` provide
  structured integration diagnostics for framework adapters.
- `PUBLIC_API_VERSION` and `SUPPORTED_TRACE_SCHEMA_VERSIONS` make the public
  compatibility boundaries explicit.
- Viewer assets are included in wheel installations, and the release workflow
  verifies a clean installation.

### Recommended migration

```bash
python -m pip install --upgrade agent-regression-kit==3.2.0
agent-regression --version
agent-regression config validate --config .agent-regression/config.json --kind single
agent-regression check --config .agent-regression/config.json --kind single
agent-regression compare --config .agent-regression/config.json
```

For a batch suite, use `--kind batch`. Keep the existing baseline files and
review the generated diff before accepting any intentional behavior change.

### Compatibility expectations

- AgentTrace `0.1` remains the supported evidence schema; existing v3.1 traces
  are expected to remain readable.
- Existing `record`, `compare`, `batch-compare`, MCP, Contract, stability,
  coverage, session, and history commands keep their documented boundaries.
- The local Viewer does not execute Agents or rewrite baselines. It can be
  removed from a headless deployment without affecting the Python core.
- Optional framework dependencies are not installed by the core package.

### Rollback

If a project integration has not been validated yet, restore the package pin
to the previous version and keep the same baseline files:

```bash
python -m pip install --force-reinstall agent-regression-kit==3.1.0
```

Do not copy a candidate Trace over a baseline as a rollback mechanism.

## v3.2.0 → v3.2.1

This is a patch release. It adds migration/compatibility release material,
Python-version CI coverage, and hardens redaction for the `secret_values`
configuration field. No Trace schema migration is required.

## v3.2.1 → v3.2.2

This is a packaging-only patch release. The wheel now includes the bilingual
getting-started guide, upgrade guide, and compatibility matrix under
`share/agent-regression-kit/docs`. No runtime or Trace schema migration is
required.

## v3.3.0 → v3.3.1

This is a small CI and Viewer handoff patch. The configuration center now links
the generated policy to the Report Index review step, and the core GitHub
workflow appends `report-index.md` to `GITHUB_STEP_SUMMARY` in addition to
uploading the output directory. No Trace schema or configuration migration is
required.

```bash
python -m pip install --upgrade agent-regression-kit==3.3.1
agent-regression --version
```

## v3.3.1 → v3.4.0

This feature release adds the reusable `agent-report-index` GitHub Action. It
generates JSON and Markdown indexes for a shared `outputs/` directory, appends
the Markdown to GitHub Job Summary, and can fail when any recognized report is
failed. The coverage Action now also emits JSON, so compare and coverage
evidence can be reviewed together. No Trace schema migration is required.

```bash
python -m pip install --upgrade agent-regression-kit==3.4.0
agent-regression --version
```

## v3.4.0 → v3.4.1

This patch fixes the core GitHub workflow's release-quality matrix behavior.
It installs explicit build tooling for Python 3.13, isolates generated CI
reports under `work/ci-reports`, and avoids running the report-index Action when
package installation itself failed. No Trace or configuration migration is
required.

```bash
python -m pip install --upgrade agent-regression-kit==3.4.1
agent-regression --version
```

## v3.4.1 → v3.4.2

This patch fixes the tag-triggered release workflow so its source-tree test
suite can import the `src` layout before building and installing the wheel. No
runtime, Trace schema, or configuration migration is required.

```bash
python -m pip install --upgrade agent-regression-kit==3.4.2
agent-regression --version
```

## v3.4.2 → v3.4.3

This feature release completes the unified CI evidence handoff. The main
workflow writes compare, stability, coverage, and history JSON into the same
report directory, and the Report Index includes the history aggregate in the
Job Summary. No Trace schema or configuration migration is required.

```bash
python -m pip install --upgrade agent-regression-kit==3.4.3
agent-regression --version
```

## v3.4.3 → v3.5.0

This feature release hardens CI trust boundaries without changing the
AgentTrace `0.1` schema. Contracts can require structured claim paths, report
indexes can require named reports or globs, and the reusable comparison Action
can load a project `config` containing the contract. Existing
`baseline`/`candidate` Action inputs continue to work.

```bash
python -m pip install --upgrade agent-regression-kit==3.5.0
agent-regression --version
agent-regression config validate --config .agent-regression/config.json
agent-regression compare --config .agent-regression/config.json
agent-regression report-index --report-dir outputs \
  --required-report compare.json --fail-on-regression
```

No Trace schema migration is required. Review existing contracts that use
`claims-only`; add `contract.required_claims` for fields that must not be
silently omitted. In the Report Index Action, use comma-separated
`required-reports` values when missing artifacts should fail the job.

## v3.5.0 → v3.6.0

This feature release adds controlled tool replay. `replay` keeps its previous
read-only meaning. Use `CassetteToolExecutor.from_trace()` or
`replay_agent_run()` when an Agent should execute against recorded tool
results without network or business side effects. The strict cassette reports
changed arguments, changed tool names, extra calls and unconsumed calls.

```bash
python -m pip install --upgrade agent-regression-kit==3.6.0
agent-regression replay --trace baselines/order-123.trace.json
agent-regression replay-run \
  --baseline baselines/order-123.trace.json \
  --scenario examples/order-123/candidate-ok.scenario.json \
  --out work/replay-candidate.trace.json
```

No Trace schema migration is required. A cassette does not prove that a live
tool still behaves the same; use normal recording against an isolated test
environment when validating tool implementations.

## v3.6.0 → v3.7.0

This release makes tool-result comparison correlation-aware. Results are
matched by their recorded `call_id` by default, which prevents a different
completion order from being reported as a different business result. Existing
order-based behavior remains available with `result_alignment: "order"` or
`--result-alignment order`.

Path rules can now include exact `result` and `is_error` fields:

```json
{
  "contract": {
    "path_rules": {
      "any_of": [[
        {"tool": "get_order", "result": {"status": "paid"}, "is_error": false}
      ]]
    }
  }
}
```

No Trace schema migration is required. If a downstream consumer depends on
the old positional result diff paths, set `result_alignment` to `order` during
the migration and remove it after the consumer is updated.

## v3.7.0 → v3.8.0

This release adds a framework event-ingestion boundary. Use
`FrameworkTraceRecorder` when a framework already owns tool execution and
emits lifecycle callbacks; use `record_framework_run` to wrap a callback
runner. The recorder validates call closure, final-answer ordering, explicit
claims and redaction without requiring a model provider.

```bash
python -m pip install --upgrade agent-regression-kit==3.8.0
python examples/langchain_core_event_example.py
agent-regression validate --trace work/langchain-core-events.trace.json
```

The LangChain dependency remains optional. Existing `CallableAgentAdapter`,
`AdapterSpec`, MCP and scripted adapters are unchanged; this is an additive
integration surface and does not require a Trace schema migration.

## v3.8.0 → v3.9.0

This release adds a local workspace review layer. Generate a manifest without
embedding evidence content, review a candidate without mutating its baseline,
and open the manifest in the local Viewer:

```bash
python -m pip install --upgrade agent-regression-kit==3.9.0
agent-regression workspace manifest \
  --directory . --out work/workspace-manifest.json
agent-regression baseline review \
  --baseline baselines/order-123.trace.json \
  --candidate work/order-123.trace.json \
  --format markdown --out outputs/baseline-review.md
agent-regression ui
```

The manifest contains relative paths, byte sizes and SHA-256 fingerprints only.
The Viewer requires an explicit file selection and never accepts a baseline or
executes an Agent. No Trace schema migration is required.

## v3.9.0 → v4.0.0

This is the stable compatibility release. The documented public Python API
generation is now `4`; v3 remains readable as a deprecated generation so an
integration can check and migrate deliberately. AgentTrace, AgentSession,
Contract/config and Report schemas remain independently versioned at `0.1`.

Run the compatibility check before changing a baseline:

```bash
python -m pip install --upgrade agent-regression-kit==4.0.0
agent-regression --version
agent-regression compatibility \
  --public-api-version 4 \
  --trace baselines/order-123.trace.json \
  --config .agent-regression/config.json \
  --report outputs/compare.json \
  --out outputs/compatibility.json
```

If the check passes, use the explicit Trace migration entry point when you
want a canonical v4 output. It never overwrites the source:

```bash
agent-regression migrate trace \
  --trace baselines/order-123.trace.json \
  --out work/order-123.v4.trace.json \
  --report outputs/order-123.migration.json
agent-regression validate --trace work/order-123.v4.trace.json
```

Trace schema `0.1` did not change in v4, so ordinary migration reports are
`status=no-op`. The command is still the supported seam for future schema
transforms. Review any `status=deprecated` API warning, run the full project
CI, and accept baseline changes only through the existing explicit review flow.
See `docs/v4-acceptance.md` for the complete release and security checklist.

## v4.0.0 → v4.1.0

v4.1 keeps public API generation 4 and the existing 0.1 evidence schemas. It
tightens validation so empty evidence sets, unknown nested policy fields,
unknown report types, malformed Trace events and reused call IDs fail closed.
If a previously accepted config now fails, correct the misspelled or unsupported
field rather than weakening the gate.

The release also adds optional adapters for completed PydanticAI, OpenAI Agents
SDK and LangGraph runs:

```bash
python -m pip install --upgrade 'agent-regression-kit[frameworks]==4.1.0'
python examples/pydantic_ai_agent_example.py
python examples/openai_agents_agent_example.py
python examples/langgraph_agent_example.py
```

The dependency-free core still supports Python 3.9. Framework extras require
Python 3.10 or newer due to upstream requirements. Existing Trace files and
reviewed baselines do not require migration. Run `compatibility`, the normal
comparison suite and any framework-specific integration checks before changing
a baseline. See `docs/v4.1-acceptance.md` for the positive and negative release
evidence.

## v4.1.0 → v4.2.0

v4.2 adds `record_deepseek_tool_run`, a dependency-free, credential-gated
DeepSeek tool-Agent loop. The core still supports Python 3.9 and installs no
provider SDK. Existing v4 traces, contracts, reports and baselines remain
compatible and require no migration.

Run the live example only with isolated test data:

```bash
python -m pip install --upgrade agent-regression-kit==4.2.0
export DEEPSEEK_API_KEY='set this in your shell or secret store'
python examples/deepseek_live_agent_example.py
agent-regression compare --config examples/deepseek-live/compare.config.json
```

The API key must never be committed or copied into a Trace. GitHub users should
store it as the encrypted repository secret `DEEPSEEK_API_KEY`. The scheduled
workflow uses `deepseek-flash`, disables thinking, caps output and runs weekly.
Rotate any credential that has been exposed in chat, logs or shell history.
See `docs/deepseek-live.md` and `docs/v4.2-acceptance.md` for the complete
operating and release boundaries.

## v3.2.2 → v3.3.0

This is a feature release for team CI handoff. It adds `report-index`, which
recognizes compare, batch, stability, and coverage JSON reports and emits a
safe relative-path inventory for the local Report Index Viewer. The reusable
GitHub Action also writes a machine-readable comparison JSON report, and the
core workflow uploads the JSON and Markdown index alongside JUnit output.

No AgentTrace schema migration is required. Existing baseline and candidate
files remain valid. After upgrading, add the optional index step to a workflow:

```bash
python -m pip install --upgrade agent-regression-kit==3.3.0
agent-regression --version
agent-regression report-index \
  --report-dir outputs \
  --out outputs/report-index.json
```

Use `--fail-on-regression` when the index itself should be a CI gate. The local
Viewer remains read-only and requires an explicit file selection for the index
and original reports.

## English release checklist

For each upgrade, record the package version, Trace schema version, test count,
wheel installation result, framework compatibility result, and MCP smoke
result in the pull request or release notes. The canonical machine-readable
boundaries are returned by `public_api_manifest()`.

## 中文说明

升级原则是：**先升级回归工具，再审核行为差异；不要因为工具升级就自动
覆盖 baseline。** 3.3.0 新增报告索引和 CI 机器可读报告，3.3.1 增加 Job
Summary 和配置中心交接，3.4.0 增加可复用的统一报告 Action，3.4.1 修复
Python matrix 和报告目录隔离，但不会改变
AgentTrace `0.1` 的含义，也不会自动读取或覆盖 baseline。

建议顺序：安装固定版本 → 检查 `--version` → `config validate` → `check` →
运行 compare → 审核报告。回滚时只恢复工具版本，不要把 candidate 复制成
baseline。
