# Path variation / 路径变化

This is the smallest example for allowing a legitimate extra query without
turning a business regression check into an unrestricted replay. The contract
requires `get_order` followed by `get_payment_status`, and v4.7 explicitly
allowlists `get_shipping` as the only permitted extra call between them.

这是“允许合法额外查询”的最小案例。契约要求先查询订单、再查询支付状态，允许
两者之间增加一个只读查询；v4.7 进一步显式列出 `get_shipping`，所以并没有把检查
变成“什么调用都可以”。

## What the modes mean / 模式含义

| Mode / 模式 | Meaning / 含义 |
| --- | --- |
| `exact` | Default. The complete path and order must match. / 默认，完整路径和顺序都必须匹配。 |
| `ordered_subsequence` | Required rules must appear in order; extra calls are allowed. / 必需规则按顺序出现，允许额外调用。 |
| `unordered_subset` | Required rules must all appear; order and extra calls do not matter. / 必需规则都出现即可，顺序和额外调用不作为路径条件。 |

In v4.7, add `path_rules.extra_calls` when you want a tolerant mode to remain
closed to unknown behavior. Omit the field to preserve the v4.6 compatibility
behavior where all unmatched extra calls are accepted; use `extra_calls: []` to
allow no extra calls. Each allowlist rule can constrain `tool`, `arguments`,
`result` and `is_error`. A rejected extra call produces an `extra_tool_call`
difference in addition to the path failure.

v4.7 中，如果希望放宽模式仍然拒绝未知行为，请配置 `path_rules.extra_calls`。
省略这个字段会保留 v4.6 的兼容行为：所有未匹配的额外调用都被接受；配置
`extra_calls: []` 则表示不允许任何额外调用。白名单规则可以约束 `tool`、
`arguments`、`result` 和 `is_error`。被拒绝的额外调用会在路径失败之外，再生成
`extra_tool_call` 差异，报告具体调用位置。

The tolerant modes are intentionally explicit. Keep `must_not_call` for
dangerous tools and `max_steps` for runaway loops. Add assertions, relations,
side-effect checks and meaningful claims when the extra calls could affect the
business result.

放宽模式必须显式配置。对于危险工具要保留 `must_not_call`，对于循环或异常膨胀要
设置 `max_steps`；如果额外调用可能影响业务结果，还要补充断言、relations、
副作用和有意义的 claims。

放宽模式必须显式配置。对于危险工具要保留 `must_not_call`，对于循环或异常膨胀要
设置 `max_steps`；如果额外调用可能影响业务结果，还要补充断言、relations、
副作用和有意义的 claims。

## Run / 运行

```bash
python -m pip install -e .
python examples/path_variation_case.py \
  --behavior normal \
  --out work/path-variation/candidate.trace.json
agent-regression compare \
  --config examples/path-variation/compare.config.json
```

The `extra-query` behavior also passes because `get_shipping` is an allowed
extra query. The `reordered` and `forbidden` behaviors must fail:

`extra-query` 也会通过，因为 `get_shipping` 是允许的额外查询；`reordered` 和
`forbidden` 必须失败：

```bash
for behavior in reordered forbidden; do
  set +e
  python examples/path_variation_case.py \
    --behavior "$behavior" \
    --out "work/path-variation/$behavior.trace.json" \
    --compare-to examples/path-variation/baseline.trace.json \
    --report "work/path-variation/$behavior.report.json"
  test "$?" -eq 1
  set -e
done
```

The dedicated [GitHub Actions workflow](../../.github/workflows/path-variation.yml)
runs the same positive and negative checks and uploads the reports as evidence.
