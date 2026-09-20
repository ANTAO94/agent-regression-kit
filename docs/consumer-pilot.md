# Independent consumer pilot / 独立消费项目验证

v4.15 introduced an end-to-end consumer repository that is separate from the
core checkout. After the v4.17 release, that consumer was upgraded and
re-verified against the immutable v4.17 wheel:

[ANTAO94/agent-regression-pilot](https://github.com/ANTAO94/agent-regression-pilot)

v4.15 增加了一个与核心仓库分离的端到端消费项目；v4.17 发布后，消费项目又升级到
v4.17 wheel 并重新验收：

[ANTAO94/agent-regression-pilot](https://github.com/ANTAO94/agent-regression-pilot)

## Consumer boundary / 消费边界

The pilot installs exactly this immutable Release asset:

```text
https://github.com/ANTAO94/agent-regression-kit/releases/download/v4.17.0/agent_regression_kit-4.17.0-py3-none-any.whl
sha256: a3239d03d89cadf05c3bc8e92722b2605b7bacb0432cf130f555da659668d3d4
```

The pilot does not import the producer checkout, add the producer `src/`
directory to `PYTHONPATH`, or copy the comparison implementation. Its own Agent
and two test tools live in the consumer repository. It uses only public
`CallableAgentAdapter`, `record_run`, `ToolExecutionResult` and the installed
`agent-regression` CLI.

消费项目只安装上面的不可变 Release wheel，不引用主项目 checkout，不把主项目 `src/` 加入
`PYTHONPATH`，也不复制比较器实现。Agent 和两个工具由消费仓库自己维护，只使用公开 API 和
已安装的 CLI。

## Scenario and Contract / 场景与契约

The Agent performs two dependent actions:

1. `get_order(order_id="123")` returns `customer_id="customer-1"` and
   `status="not_shipped"`;
2. `get_balance(customer_id="customer-1")` verifies the related balance;
3. the final answer emits `order_status` and `balance_verified` claims.

The consumer Contract requires both calls, checks the dependent customer ID,
requires the structured claims, forbids `refund_order` and limits the run to
two tool calls.

Agent 的真实消费流程是两步依赖：先查订单，再使用订单返回的 customer ID 查余额，最后输出
结构化 claims。Contract 同时检查两次调用、跨步骤参数关系、业务结论、禁止工具和步数上限。

## Injected regressions / 注入回归

The consumer workflow ran on the v4.17 upgrade commit `2119787` and passed
(GitHub Actions run [`35525513139`](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35525513139)):

| Case / 用例 | Expected / 预期 | Observed / 实测 |
| --- | --- | --- |
| normal | exit 0 | pass |
| wrong resource (`999` instead of `123`) | exit 1 | blocked; required tool, argument, result and relation evidence |
| skipped `get_balance` | exit 1 | blocked; required tool, missing result association and claims evidence |
| report `shipped` for a `not_shipped` result | exit 1 | blocked; Contract assertion and result-interpretation evidence |

CI run: [Consumer Agent regression workflow](https://github.com/ANTAO94/agent-regression-pilot/actions/workflows/regression.yml)

The original v4.15 acceptance snapshot used the v4.14.0 wheel at commit
`d231df3`; the v4.16 release snapshot used the v4.15.0 wheel at commit
`8ebc38f`; the v4.16 post-release verification used the v4.16.0 wheel at
`69028e5`; the current v4.17 post-release verification uses the v4.17.0 wheel
at `2119787`.

消费仓库的 CI（run `35525513139`）已验证正常场景返回 0，三类注入均返回 1。报告会保留在
workflow artifact 中，baseline 由人工审核后提交，CI 不会自动覆盖 baseline。

## Reproduce / 复现

```bash
git clone https://github.com/ANTAO94/agent-regression-pilot.git
cd agent-regression-pilot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-ci.txt

PYTHONPATH=. python scripts/record_agent.py --variant normal --out work/candidate.trace.json
agent-regression check --config contracts/order-status.json
agent-regression compare --config contracts/order-status.json
```

The pilot is deliberately deterministic and local. It proves the released
integration boundary and error-detection contract; it does not prove automatic
instrumentation for arbitrary Agent frameworks, online-provider quality or
production reliability.

该项目是确定性的本地消费案例，证明的是“发布包可以被独立项目安装并用于阻断可复现错误”，
不是所有 Agent 框架自动兼容、在线模型质量或生产可靠性的证明。
