# Refund business case / 退款业务案例

This is the smallest complete business regression example in the repository.
It uses a deterministic Agent and an isolated in-memory tool fixture, so every
developer can reproduce the same evidence without an API key.

这是仓库中最小但完整的业务回归案例。它使用确定性的 Agent 和隔离的内存
工具 Fixture，不需要 API Key，任何开发者都能复现相同证据。

## What is tested / 检查什么

The Agent receives “refund order 123” and must:

1. look up order `123`;
2. check refund eligibility;
3. refund no more than the paid amount;
4. report a structured result;
5. change the order state exactly once。

Agent 收到“退款订单 123”后必须：

1. 查询订单 `123`；
2. 检查退款资格；
3. 退款金额不能超过实付金额；
4. 输出结构化业务结论；
5. 只改变一次订单状态。

The contract contains four kinds of checks:

- `assertions`: fixed business values such as `refund_status=refunded`;
- `must_call` and `path_rules`: required tools and their order;
- `tool_limits`: minimum/maximum calls per tool, preventing duplicate refunds and runaway loops;
- `side_effects`: the expected before/after state;
- `relations`: values carried between steps, such as “refund amount <= paid amount”。

契约包含五类检查：固定字段断言、必需工具和路径、工具调用次数、状态变化，以及
跨步骤的业务关系。`tool_limits` 能把“退款只能执行一次”写成明确的最小/最大次数；
`relations` 是本案例的重点之一：它能检查 Agent 是否把前一步工具结果正确传给后一步，
而不是只检查工具名称。

## Run it / 运行

From the repository root, after installing the package:

```bash
python examples/refund_business_case.py \
  --behavior normal \
  --out work/refund-business-case/candidate.trace.json

agent-regression compare \
  --config examples/refund-business-case/compare.config.json
```

The comparison should exit with `0` and write a Markdown report to
`work/refund-business-case/compare.md`。

在仓库根目录安装项目后执行上面的命令。正常用例应返回退出码 `0`，并生成
`work/refund-business-case/compare.md`。

## Inject known defects / 注入已知错误

Each behavior below represents a bug that a business Agent can introduce:

```bash
for behavior in wrong-order wrong-amount skip-eligibility duplicate-refund; do
  python examples/refund_business_case.py \
    --behavior "$behavior" \
    --out "work/refund-business-case/$behavior.trace.json" \
    --compare-to examples/refund-business-case/baseline.trace.json \
    --report "work/refund-business-case/$behavior.report.json" || true
done
```

| Behavior | Injected defect | Main gate that catches it |
| --- | --- | --- |
| `wrong-order` | looks up order `456` | relation, path, state and claims |
| `wrong-amount` | requests `880` when paid amount is `88` | amount relations and tool error |
| `skip-eligibility` | refunds without the eligibility check | required tool and path |
| `duplicate-refund` | calls the refund operation twice | `tool_count`, path and step limit |

The failure report includes the category, path, expected/observed values and a
human-readable rule message. A real framework adapter can reuse the same
`contract.json` after replacing the deterministic `RefundAgent`。

失败报告会给出类别、路径、预期/实际值和规则解释。接入真实框架时，可以保留
`contract.json`，只替换示例里的确定性 `RefundAgent`。

## Files / 文件

- `../../examples/refund_business_case.py`: Agent, tool fixture and runner / Agent、工具 Fixture 与运行脚本
- `contract.json`: reusable business contract / 可复用业务契约
- `compare.config.json`: CLI and CI configuration / CLI 与 CI 配置
- `baseline.trace.json`: reviewed normal baseline / 审核过的正常 baseline
