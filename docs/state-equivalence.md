# State-equivalence contracts / 状态等价契约

This guide describes the v4.13 `contract.state_equivalence` feature. It is
intended for a regression suite where two Agents may take different, reviewed
actions but must leave the business state in the same acceptable outcome.

本文说明 v4.13 的 `contract.state_equivalence`。它适用于这样的回归场景：两个 Agent
可以采用不同但已经审核过的动作，只要最后留下的业务状态相同且没有越过安全边界，就
应该通过；它不是“忽略所有差异”的宽松回放。

## 1. The problem / 它解决什么问题

Traditional replay often treats the baseline action list as the only correct
answer:

```text
baseline: charge(card-a) → paid
candidate: charge(card-a) → declined → charge(card-b) → paid
```

The candidate has an extra failed attempt and a different routing choice, but
the order is paid. A strict action-by-action comparison reports a false alarm
even though the independently checked business outcome is acceptable. The
opposite mistake is more dangerous: accepting an arbitrary successful call
because it appears to be “equivalent”. v4.13 separates intent equivalence,
success evidence and the scope of unchanged state.

传统流量回放通常把 baseline 的动作列表当成唯一正确答案，例如：

```text
baseline：charge(card-a) → paid
candidate：charge(card-a) → declined → charge(card-b) → paid
```

candidate 多了一次失败尝试，并且换了支付方式；如果订单最终确实为 `paid`，严格的
动作逐条比较会产生误报。但如果为了降低误报而接受任意成功调用，又可能放过错误订单、
越权资源或错误状态。v4.13 把“意图是否等价”“动作是否成功”和“其余状态是否变化”分开检查。

## 2. Important terms / 关键名词

| Term | 中文解释 | In this project |
| --- | --- | --- |
| Trace | 一次 Agent 运行产生的结构化事件证据 | tool calls, tool results, final answer and optional state snapshots |
| Baseline | 经人工审核、可接受的参考运行 | Supplies the expected path and selected state values |
| Candidate | 当前代码、Prompt 或模型产生的新运行 | Must satisfy the Contract; it is never silently accepted as baseline |
| Intent | 一次业务意图，例如“修改订单地址” | Built from a configured tool rule after ignored routing fields are removed |
| Outcome | 业务最终结果，例如订单状态变成 `paid` | Declared with `state_equivalence.paths` and/or path-rule outcomes |
| Exact action | 工具名和未忽略参数必须精确匹配 | Prevents an unrelated order or resource from passing |
| Idempotent call | 重复执行结果不应改变业务结果的调用 | Must be explicitly listed in `idempotent_tools` |
| Tool alias | 明确声明的工具语义别名 | Only configured aliases are considered; aliases are not inferred |
| Attempt policy | 失败尝试与成功证据的规则 | Controls required success, allowed failed retries and the retry limit |
| State scope | 最终状态检查范围 | Declared paths only, declared paths plus unchanged remainder, or full state |

## 3. Configuration shape / 配置结构

`state_equivalence` is nested under the same `contract` object used by the
existing CLI, Python API and reusable GitHub Action. It is optional. Omitting it
preserves the pre-v4.12 behavior. v4.13 adds explicit `attempt_policy` and
`state_scope`; old `allow_failed_expected` remains readable and is reported by
`config`/`check` as a migration diagnostic.

`state_equivalence` 位于现有配置的 `contract` 对象下，CLI、Python API 和 GitHub Action
都使用同一份配置。字段是可选的；省略时保持 v4.12 之前的严格行为。v4.13 增加显式
`attempt_policy` 和 `state_scope`；旧的 `allow_failed_expected` 仍可兼容读取，但
`config`/`check` 会给出迁移诊断。

```json
{
  "comparison": {
    "final_answer_mode": "claims-only"
  },
  "contract": {
    "path_rules": {
      "mode": "unordered_subset",
      "any_of": [[
        {
          "tool": "charge_order",
          "arguments": {
            "order_id": "123",
            "payment_method_id": "card-a"
          }
        },
        {
          "tool": "charge_order",
          "arguments": {
            "order_id": "123",
            "payment_method_id": "card-b"
          }
        }
      ]],
      "extra_calls": []
    },
    "state_equivalence": {
      "mode": "outcome",
      "paths": [
        "world_state.final.orders.123.status"
      ],
      "ignore_argument_paths": [
        "payment_method_id"
      ],
      "state_scope": "declared_and_unchanged_rest",
      "attempt_policy": {
        "require_success": true,
        "allow_failed_before_success": true,
        "max_failed_attempts": 1
      },
      "idempotent_tools": [
        "modify_pending_order_address"
      ]
    }
  }
}
```

### Field reference / 字段说明

| Field | Default | Meaning / 含义 |
| --- | --- | --- |
| `mode` | `exact` | `exact` keeps normal strict comparison; `outcome` groups documented alternative intent rules and checks declared outcomes; `hybrid` keeps each rule separate but allows explicitly configured equivalent tools. |
| `paths` | `[]` | Baseline/candidate JSON paths whose values must be equal. Usually points to `world_state.final`; missing paths fail closed. |
| `ignore_argument_paths` | `[]` | Relative argument paths removed only while grouping declared rules into one intent. It is not a wildcard allowlist for candidate arguments. |
| `tool_aliases` | `[]` | Lists of tool names with an explicitly reviewed semantic relationship. No aliases are inferred from spelling or result shape. |
| `allow_failed_expected` | `false` | Allows a candidate error event to satisfy a rule that did not require success. Use only when retry/fallback is a valid business behavior. An explicit `is_error: true` rule is always allowed to match an error. |
| `attempt_policy.require_success` | `true` | Requires at least one successful matching event for each expected intent. |
| `attempt_policy.allow_failed_before_success` | `false` | Allows failed matching attempts only as retries before a successful event. |
| `attempt_policy.max_failed_attempts` | `0` | Maximum failed matching attempts per intent; a positive value requires `allow_failed_before_success`. |
| `state_scope` | `declared_only` when `paths` exist, otherwise `full` | `declared_only` checks listed paths; `declared_and_unchanged_rest` also checks the remaining world state; `full` compares all world state. |
| `idempotent_tools` | `[]` | Allows an additional successful call when it exactly matches an already satisfied expected rule. It does not allow a different argument, a failed extra call, or an unlisted tool. |

## 4. Three modes / 三种模式

### `exact`

This is the compatibility default. `state_equivalence` does not alter the
existing path/result comparison. Use it when every call, argument and result is
part of the reviewed contract.

这是兼容默认值。它不改变已有路径和结果比较，适合每一次调用、参数和结果都必须与
baseline 一致的场景。

### `outcome`

This mode is for a declared set of equivalent alternatives. In each `any_of`
path, rules that become equal after `ignore_argument_paths` are grouped into one
intent. One candidate event must match one rule in the group exactly for its
tool name, remaining arguments, result constraints and error constraint.

`outcome` mode also avoids comparing raw tool-result payloads solely because a
transport request ID, provider wording or other unmodeled response field
changed. If business state matters, declare it in `paths`; if a tool result is
itself the business outcome, put a `result` constraint in the path rule.

该模式用于显式声明多个等价选择。在每一条 `any_of` 路径中，先按照
`ignore_argument_paths` 对规则分组；candidate 必须用工具名、未忽略参数、规则中声明的
`result` 和错误状态精确命中组内某一条规则。

`outcome` 不会因为传输层 request ID、供应商返回文字等未建模字段变化就阻断；真正重要的
业务状态应通过 `paths` 声明。如果工具返回值本身就是业务结果，就在路径规则里配置
`result`，不要只依赖“看起来像成功”。

### `hybrid`

This mode keeps each expected rule as a separate required intent, but allows
configured `tool_aliases` and selected failed attempts. Use it when the
business requires all declared steps, while a small number of tool names are
known to represent the same operation.

该模式仍然要求每条规则分别出现，但允许显式配置的工具别名和失败尝试。适合所有业务步骤
都必须执行、但底层工具名称存在受控兼容映射的场景。

## 5. Safety behavior / 安全边界

State equivalence is deliberately fail-closed:

1. Ignored arguments only group rules that you wrote. They do not turn an
   arbitrary candidate argument into a match.
2. A candidate must still match the exact tool name and every non-ignored
   argument of one declared rule. The object ID, tenant ID, amount and resource
   scope should normally remain non-ignored.
3. An alias is used only when the alias group is explicitly configured. The
   outcome grouping still requires the candidate to match one of the exact
   rules in that group; a successful undeclared alias does not create a new
   valid action.
4. Failed attempts are not automatically harmless. The v4.13 default requires
   a successful matching event. Set `allow_failed_before_success: true` only
   when the business path explicitly permits retry/fallback, set a finite
   `max_failed_attempts`, and keep `must_not_call`, `tool_allowlist`,
   `argument_rules` and `max_steps` in place. A failed-only path produces
   `required_success_missing`; an over-limit path produces
   `retry_limit_exceeded`.
5. Idempotent repeats must be listed and must match the same arguments. A
   failed repeat is not treated as an allowed extra.
6. `paths` compare baseline and candidate evidence. A missing baseline or
   candidate path is a blocking `state_evidence_missing` difference. Use
   `declared_and_unchanged_rest` to block changes outside the declared paths;
   those differences are reported as `unexpected_state_change`.

状态等价严格遵循 fail-closed 原则：

1. 被忽略的参数只负责把你配置过的规则归并，不会把任意 candidate 参数变成合法值。
2. candidate 仍必须匹配某条声明规则的精确工具名和所有未忽略参数。订单号、租户号、金额、
   资源范围通常不能放进忽略列表。
3. 工具别名必须显式配置；outcome 分组最终仍要求命中组内某条精确规则，不会因为名称相似
   就自动放行一个未声明动作。
4. 失败尝试不是天然安全的。v4.13 默认要求成功事件；只有业务确实允许重试/降级时才配置
   `allow_failed_before_success: true` 并设置有限的 `max_failed_attempts`，同时保留
   `must_not_call`、`tool_allowlist`、`argument_rules` 和 `max_steps`。只有失败没有成功会生成
   `required_success_missing`，超过上限会生成 `retry_limit_exceeded`。
5. 幂等重复必须列入 `idempotent_tools`，并且参数完全相同；失败的重复调用不会被额外放行。
6. `paths` 会比较 baseline 和 candidate 的证据；任一侧缺失都会生成阻断性的
   `state_evidence_missing` 差异。使用 `declared_and_unchanged_rest` 可以阻断声明路径之外的
   状态变化，并生成 `unexpected_state_change`。

## 6. When to use which rule / 选择规则

| Situation / 场景 | Recommended rule / 推荐配置 |
| --- | --- |
| Every call must be identical | `mode: exact`, strict `path_rules` |
| Payment/provider routing can vary, order must stay exact | `mode: outcome` + ignore only `payment_method_id` |
| Retry after a known business error is valid | `attempt_policy` with success required, failed retries allowed and a finite limit |
| Repeating the same address update is harmless | `idempotent_tools` + exact arguments + `extra_calls: []` |
| Two reviewed APIs implement one operation | `tool_aliases` plus rules for both names; add a negative test for an undeclared alias |
| Final database status is the real oracle | `paths` under `world_state.final` plus side-effect/argument policies |
| You are unsure whether two actions are equivalent | Stay with `exact` and review the false alarm before relaxing the Contract |

Do not use `ignore_argument_paths: ["*"]` for convenience. That would collapse
different business objects into one intent and can hide a dangerous regression.

不要为了省事配置 `ignore_argument_paths: ["*"]`。这会把不同业务对象折叠成同一个意图，
可能掩盖危险回归。

## 7. CLI and Python usage / CLI 与 Python 用法

The same config is used locally and in CI:

```bash
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/order-123.trace.json \
  --config examples/quickstart/compare.config.json \
  --out work/reports/compare.json
```

The Python API uses the same dictionary shape:

```python
from agent_regression import ComparisonPolicy, ContractPolicy, compare_traces

policy = ComparisonPolicy(
    final_answer_mode="claims-only",
    contract=ContractPolicy.from_dict(config["contract"]),
)
report = compare_traces(baseline, candidate, policy)
if not report["passed"]:
    raise SystemExit(1)
```

Use `report["differences"]` to inspect `behavior_path`, `extra_tool_call`,
`state_equivalence`, `tool_argument_policy` and other structured categories.
The report keeps blocking and allowed differences separate; it does not modify
the baseline.

## 8. v4.13 independent evidence / v4.13 独立证据

The pinned τ²-bench retail dataset exposes the practical reason for this
feature. v4.11's strict action contract correctly blocked every one of 153
upstream failures but raised 14 false alarms on 267 upstream successes. The
false alarms included fallback payment attempts, idempotent address updates
and equivalent pending-order operations.

With explicit outcome grouping and the same fail-closed action matching, v4.12
measures 420 eligible write scenarios as:

| Classification | Count |
| --- | ---: |
| True pass | 267 |
| True block | 153 |
| False alarm | 0 |
| Missed failure | 0 |

The v4.13 implementation keeps the same matrix while making the benchmark's
non-strict success interpretation explicit in its adapter. The result is
evidence on one pinned public dataset, not a universal quality claim. Reproduce
it with the [independent validation guide](tau2-independent-validation.md)
and read the [v4.13 acceptance record](v4.13-acceptance.md) before using the
numbers in a project announcement.

该结果只代表一份固定的公开数据集，不是对所有模型或生产系统的普遍承诺。请按[独立验证
说明](tau2-independent-validation.md)复现，并结合 [v4.13 验收记录](v4.13-acceptance.md)
理解边界。
