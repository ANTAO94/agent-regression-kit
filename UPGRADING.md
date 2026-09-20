# Upgrading Agent Regression Kit

This file records migration actions for released versions. The core rule is:
**upgrade the comparison tool before changing a reviewed baseline**. A package
upgrade must not silently turn a candidate difference into a new baseline.

## v4.27.0 → v4.28.0

v4.28 is additive for existing Trace, Contract and baseline files. No data
migration is required. Repeated-run stability reports now include Wilson 95%
intervals and a `sample_size` section. Existing callers keep the default
`min_runs=1`; projects that want a hard evidence minimum can add
`--min-runs 30` to the CLI or `min_runs=30` to `StabilityPolicy`.

The interval fields describe finite observed repeats. They do not change the
comparison decision, read benchmark labels or prove online model quality. Run
the existing stability check once after upgrading, review the new interval and
warning fields, then decide whether your project should opt into a stricter
minimum.

```bash
agent-regression stability \
  --baseline baselines/order-123.trace.json \
  --scenario examples/order-123/baseline.scenario.json \
  --repeats 30 \
  --min-runs 30 \
  --format markdown \
  --out work/stability-v428.md
```

## v4.27.0 → v4.28.0（中文）

v4.28 对已有 Trace、Contract 和 baseline 保持增量兼容，不需要数据迁移。重复运行稳定性报告
新增 Wilson 95% 区间和 `sample_size`。旧调用方仍使用默认 `min_runs=1`；如果希望设置最低
证据量，可以在 CLI 增加 `--min-runs 30`，或在 `StabilityPolicy` 中设置 `min_runs=30`。

区间描述的是已经执行的有限重复运行，不改变比较决策、不读取 benchmark 标签，也不证明在线模型
质量。升级后先执行一次 stability，检查新增区间和提醒字段，再决定是否在项目中启用更严格的最低
次数门禁。完整验收见[v4.28 验收记录](docs/v4.28-acceptance.md)。

## v4.17.0 → v4.18.0

v4.18 is additive for existing Trace, Contract and baseline files. No migration
is required. It adds `path_rules.ignore_argument_paths` for path-local
transport noise:

```json
{
  "contract": {
    "path_rules": {
      "any_of": [[{"tool": "get_order", "arguments": {"order_id": "123"}}]],
      "ignore_argument_paths": ["request_id"]
    }
  }
}
```

The field removes a path only when the baseline rule does not declare it. An
explicitly declared order ID, tenant ID or payment ID remains strict. This is
different from `state_equivalence.ignore_argument_paths`, which groups
declared outcome intents. Review every ignored field as part of the Contract;
do not use `*` as a convenience wildcard. v4.18 also adds the independent
τ²-bench airline importer and its checksum-bound validation workflow. See the
[v4.18 acceptance record](docs/v4.18-acceptance.md).

## v4.17.0 → v4.18.0（中文）

v4.18 对已有 Trace、Contract 和 baseline 保持增量兼容，不需要迁移。新增的
`path_rules.ignore_argument_paths` 用于路径契约中的传输层噪音字段。它只会忽略 baseline
没有声明的字段；baseline 明确写出的订单号、租户号或支付 ID 仍然严格检查。它与用于
outcome 意图分组的 `state_equivalence.ignore_argument_paths` 不是同一个字段。每个被忽略的
字段都必须经过业务评审，不要使用 `*` 作为方便的通配符。

v4.18 同时增加 τ²-bench airline 独立导入器、来源哈希和 CI 验证。详见
[v4.18 验收记录](docs/v4.18-acceptance.md) 和[航空复现说明](examples/tau2-airline/README.md)。

## v4.12.0 → v4.13.0

v4.13 keeps the AgentTrace schema and existing files compatible, but makes two
state-equivalence boundaries explicit: successful evidence for an expected
action, and the scope of unchanged world state.

For ordinary application regressions, use the strict policy (these are also the
defaults when `attempt_policy` is present):

```json
{
  "state_equivalence": {
    "mode": "outcome",
    "paths": ["world_state.final.orders.123.status"],
    "state_scope": "declared_and_unchanged_rest",
    "attempt_policy": {
      "require_success": true,
      "allow_failed_before_success": true,
      "max_failed_attempts": 1
    }
  }
}
```

This requires a successful matching event, permits at most one failed retry,
requires declared state evidence and checks the remaining world state for
unexpected changes. The new blocking categories are
`required_success_missing`, `retry_limit_exceeded`, `state_evidence_missing`
and `unexpected_state_change`.

Existing `allow_failed_expected` configurations remain readable and preserve
their v4.12 behavior. Run `agent-regression config --config ...` or
`agent-regression check --config ...` to receive a non-blocking
`legacy_allow_failed_expected` migration diagnostic. Do not mechanically turn
it on for a normal application: use an explicit non-strict `attempt_policy` only
when an external benchmark oracle defines the meaning of a failed expected
write. The τ² adapter is one such documented exception.

v4.13 is additive for traces and baselines. Review any newly added state paths,
retry limits and negative cases in the same pull request as the Contract.
See the [v4.13 acceptance record](docs/v4.13-acceptance.md).

## v4.12.0 → v4.13.0（中文）

v4.13 保持 AgentTrace schema 和既有文件兼容，但把两个状态等价边界显式化：预期动作必须有
成功证据，以及未声明 world state 是否必须保持不变。

普通业务回归建议使用上面的严格策略。它要求成功匹配事件，最多允许一次失败重试，要求声明
状态证据存在，并检查其余状态是否发生意外变化。新增阻断类别为
`required_success_missing`、`retry_limit_exceeded`、`state_evidence_missing` 和
`unexpected_state_change`。

已有 `allow_failed_expected` 配置仍可读取并保持 v4.12 语义。执行
`agent-regression config --config ...` 或 `agent-regression check --config ...` 会获得非阻断的
`legacy_allow_failed_expected` 迁移诊断。普通业务不要机械地保留这个旧字段；只有外部 benchmark
oracle 明确定义“失败写入也算成功”时，才显式使用非严格 `attempt_policy`。τ² 适配器就是一个
已在验收文档中说明的例外。

v4.13 对 Trace 和 baseline 是增量兼容的，但新增状态路径、重试上限和负向用例应与 Contract
一起评审。详见 [v4.13 验收记录](docs/v4.13-acceptance.md)。

## v4.11.0 → v4.12.0

v4.12 is additive. Existing Trace, Contract and comparison policies keep their
behavior when `state_equivalence` is absent; no Trace or baseline migration is
required. The new field is useful when a business outcome can be reached through
documented alternative actions, such as trying another payment method, while
the action arguments that identify the business object must remain exact.

```json
{
  "contract": {
    "path_rules": {
      "mode": "unordered_subset",
      "any_of": [[
        {"tool": "charge_order", "arguments": {"order_id": "123", "payment_method_id": "card-a"}},
        {"tool": "charge_order", "arguments": {"order_id": "123", "payment_method_id": "card-b"}}
      ]]
    },
    "state_equivalence": {
      "mode": "outcome",
      "paths": ["world_state.final.orders.123.status"],
      "ignore_argument_paths": ["payment_method_id"],
      "allow_failed_expected": true,
      "idempotent_tools": ["modify_pending_order_address"]
    }
  }
}
```

`ignore_argument_paths` is used only to group rules that describe one intent;
it does not make an arbitrary candidate argument valid. Candidate tool names
and non-ignored arguments still have to match one of the documented rules.
`allow_failed_expected` and `idempotent_tools` are opt-in, and `tool_aliases`
must be declared explicitly. Start with `hybrid` or `exact` when the business
does not have a reviewed equivalence relation. See
[`docs/state-equivalence.md`](docs/state-equivalence.md) and the
[v4.12 acceptance contract](docs/v4.12-acceptance.md).

v4.12 是增量版本。未配置 `state_equivalence` 的旧 Trace、Contract 和比较策略保持原有
行为，不需要迁移。新字段用于表达“动作路径可能不同但业务结果等价”的场景；被忽略的
参数只用于把已声明的规则归并为同一个意图，不会让任意参数自动通过。失败尝试、幂等
重复和工具别名都必须显式配置，并建议先用 `hybrid` 或 `exact`。

详见[状态等价契约说明](docs/state-equivalence.md)和
[v4.12 验收说明](docs/v4.12-acceptance.md)。

## v4.10.0 → v4.11.0

v4.11 is additive. Existing Trace, Contract, config and baseline files require
no migration. The release adds optional public helpers for consuming published
τ²-bench retail results:

```python
from agent_regression import (
    build_tau2_retail_contract,
    evaluate_tau2_retail_results,
    trace_from_tau2_simulation,
)
```

`trace_from_tau2_simulation` does not copy the upstream reward into Trace
metadata or claims. `evaluate_tau2_retail_results` makes the Contract decision
first and reads reward only to label the resulting confusion matrix. Pin the
upstream tag and checksum when reproducing the published metrics. See the
[independent validation guide](docs/tau2-independent-validation.md).

v4.11 是增量版本，旧 Trace、Contract、配置和 baseline 不需要迁移。新增 API 用于
导入 τ²-bench 零售轨迹、根据任务定义生成契约，并在契约判断完成后用上游 reward
计算误报与漏报。reward 不会进入 Trace 或 claims。复现实测时必须固定上游 tag 和
SHA-256，完整方法见[独立项目验证说明](docs/tau2-independent-validation.md)。

## v4.9.0 → v4.10.0

This feature release adds optional `contract.argument_rules`. Existing
contracts that omit the field keep their behavior and do not require a Trace
or baseline migration. Add a rule when a condition should apply to every call
of a named tool rather than to one fixed `tool_calls[index]` path.

```json
{
  "contract": {
    "argument_rules": [
      {
        "tool": "get_order",
        "path": "tenant_id",
        "operator": "equals_path",
        "right_path": "metadata.input.tenant_id"
      },
      {
        "tool": "refund_order",
        "path": "amount",
        "operator": "less_or_equal_path",
        "right_path": "tool_results[0].result.paid_amount"
      },
      {"tool": "refund_order", "path": "admin_override", "operator": "absent"}
    ]
  }
}
```

`argument_rules` checks every matching call. Literal operators use `value`,
Trace operators use `right_path`, and `exists`/`absent` check required or
forbidden paths. Violations produce `tool_argument_policy`; a missing tool does
not replace `must_call`. Keep `relations` for general claims/result/state
relationships. See the [v4.10 acceptance contract](docs/v4.10-acceptance.md).

本次版本增加可选的 `contract.argument_rules`。省略该字段的旧配置保持行为不变，
不需要迁移 Trace 或 baseline。当一条条件应该适用于某个工具的每一次调用，而不是
固定的 `tool_calls[index]` 时，使用这项能力。固定值用 `value`，Trace 字段用
`right_path`，`exists` / `absent` 检查必填和禁用参数，失败类别为
`tool_argument_policy`。工具没有被调用时不代替 `must_call`；通用 claims、结果和状态
关系继续使用 `relations`。

## v4.8.0 → v4.9.0

This feature release adds an optional scenario-level `contract.tool_allowlist`.
It defines the complete set of tools a candidate Agent may call and can match
exact arguments for a particular business object.

本次功能版本增加可选的场景级 `contract.tool_allowlist`，用于定义候选 Agent 在一个
业务场景中允许调用的完整工具集合，也可以进一步匹配具体参数。

```json
{
  "contract": {
    "tool_allowlist": [
      "get_order",
      {"tool": "refund_order", "arguments": {"order_id": "123", "amount": 88}}
    ]
  }
}
```

If the field is omitted, behavior is unchanged and no migration is required.
An explicit `[]` denies every tool call, so use it only for answer-only
scenarios. A rejected call produces `unauthorized_tool_call` at its
`tool_calls[index]` path. Keep `tool_limits`, `path_rules`, `relations` and
`side_effects` for their separate responsibilities.

省略字段时行为完全不变，不需要迁移。显式配置 `[]` 表示拒绝所有工具调用，只适合
只允许直接回答的场景。被拒绝的调用会在 `tool_calls[index]` 路径生成
`unauthorized_tool_call`。`tool_limits`、`path_rules`、`relations` 和 `side_effects`
仍应分别负责调用次数、路径、业务值关系和状态变化。

See the [v4.9 acceptance contract](docs/v4.9-acceptance.md) and the
[refund business case](examples/refund-business-case/README.md).

参见 [v4.9 验收说明](docs/v4.9-acceptance.md) 与
[退款业务案例](examples/refund-business-case/README.md)。

## v4.7.0 → v4.8.0

This feature release adds optional `contract.tool_limits` rules. Existing
Contracts continue to work unchanged when the field is absent. Use `min_calls`
for a lower bound, `max_calls` for an upper bound, or both for an exact count;
the optional `arguments` object scopes which calls are counted.

```json
{
  "contract": {
    "tool_limits": [
      {"tool": "get_order", "min_calls": 1, "max_calls": 1},
      {"tool": "refund_order", "max_calls": 1}
    ]
  }
}
```

Violations produce a `tool_count` difference with the configured rule and
observed count. The feature does not change Trace schema or public API version,
and it does not replace `must_not_call`, path rules or side-effect checks. See
the [v4.8 acceptance contract](docs/v4.8-acceptance.md) and the [refund
business case](examples/refund-business-case/README.md).

## v4.6.1 → v4.7.0

This feature release adds the optional `contract.path_rules.extra_calls`
allowlist for `ordered_subsequence` and `unordered_subset`. Existing tolerant
Contracts that omit the field keep v4.6 behavior, so no migration is required.
Add the field when a project wants to allow only named observational calls; use
`extra_calls: []` to reject every unmatched extra call. Each rule can constrain
the tool name, arguments, result and error state. Unknown calls produce an
`extra_tool_call` diagnostic in addition to the overall `behavior_path` failure.

```json
{
  "contract": {
    "path_rules": {
      "mode": "ordered_subsequence",
      "any_of": [["get_order", "get_payment_status"]],
      "extra_calls": [
        {"tool": "get_shipping", "is_error": false}
      ]
    }
  }
}
```

`extra_calls` cannot be combined with the default `exact` mode. See the
[v4.7 acceptance contract](docs/v4.7-acceptance.md) and the [path variation
example](examples/path-variation/README.md) before enabling it.

## v4.6.0 → v4.6.1

This patch release corrects the release-integrity verification commands. No
Trace, Contract, public API or configuration behavior changed. Existing
installations can upgrade without migration; consumers should use the updated
[`docs/supply-chain.md`](docs/supply-chain.md) commands when verifying both
the SLSA provenance and SPDX 2.3 SBOM attestations.

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
