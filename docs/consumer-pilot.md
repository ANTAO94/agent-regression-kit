# Independent consumer pilot / 独立消费项目验证

v4.15 introduced an end-to-end consumer repository that is separate from the
core checkout. After the v4.33 release, that consumer was upgraded and
re-verified against the immutable v4.33 wheel:

[ANTAO94/agent-regression-pilot](https://github.com/ANTAO94/agent-regression-pilot)

v4.15 增加了一个与核心仓库分离的端到端消费项目；v4.33 发布后，消费项目又升级到
v4.33 wheel 并重新验收：

[ANTAO94/agent-regression-pilot](https://github.com/ANTAO94/agent-regression-pilot)

## Consumer boundary / 消费边界

The pilot installs exactly this immutable Release asset for the current
v4.33 evidence:

```text
https://github.com/ANTAO94/agent-regression-kit/releases/download/v4.33.0/agent_regression_kit-4.33.0-py3-none-any.whl
sha256: 2206b0a37934406b3be119bc807750b5a8eac52c95ba806a62fd68fba25d6814
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

The consumer workflow ran on the v4.33 upgrade commit `d0d320b` and passed
(GitHub Actions run [`35547832896`](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35547832896)):

| Case / 用例 | Expected / 预期 | Observed / 实测 |
| --- | --- | --- |
| normal | exit 0 | pass |
| wrong resource (`999` instead of `123`) | exit 1 | blocked; required tool, argument, result and relation evidence |
| skipped `get_balance` | exit 1 | blocked; required tool, missing result association and claims evidence |
| report `shipped` for a `not_shipped` result | exit 1 | blocked; Contract assertion and result-interpretation evidence |

CI run: [Consumer Agent regression workflow](https://github.com/ANTAO94/agent-regression-pilot/actions/workflows/regression.yml)

The v4.33 consumer imports the public `sha256_file` helper from the released
wheel, hashes its reviewed baseline and asserts `__version__ == 4.33.0` before
exercising the Agent boundary. It also builds an independent sampling-study
bundle, verifies the required `input`, `tool_schema`, `adapter`,
`provider_output` and `dataset` evidence roles, and binds six controlled fields
to matching provenance values with the published `study` CLI. This confirms
that the v4.33 run-identity boundary is available through the published
artifact, not only from the core checkout.

v4.33 消费项目从发布 wheel 导入公开的 `sha256_file`，对审核过的 baseline 计算哈希，并在
运行 Agent 边界前断言 `__version__ == 4.33.0`；同时由独立消费方创建 sampling-study bundle，
通过发布的 `study` CLI 校验 `input`、`tool_schema`、`adapter`、`provider_output`、`dataset` 五类
必需 evidence role，并把六个描述字段绑定到对应 provenance 值。这证明 v4.33 运行身份绑定边界确实
随发布包可用，而不是只在核心仓库源码路径中可用。

The v4.29 evidence binding is recorded in consumer follow-up commit `9660c8b`
and its CI run is
[`35543057429`](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35543057429).
The previous v4.28 evidence binding remains useful history: its upgrade commit
was `491c33c`, its follow-up commit was `47a6300`, and its CI runs were
[`35541894413`](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35541894413)
and [`35541931223`](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35541931223).
The previous v4.27 evidence binding remains useful history: its upgrade commit
was `5dfab07`, its follow-up commit was `a2bb7fa`, and its CI runs were
[`35540425730`](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35540425730)
and [`35540456637`](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35540456637).
The previous v4.26 evidence remains useful history: its upgrade commit was
`56a1316`, its follow-up commit was `eb5ce5d`, and its CI runs were
[`35539092690`](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35539092690)
and [`35539134847`](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35539134847).
The previous release snapshots remain useful history: the original v4.15
acceptance snapshot used the v4.14.0 wheel at commit
`d231df3`; the v4.16 release snapshot used the v4.15.0 wheel at commit
`8ebc38f`; the v4.16 post-release verification used the v4.16.0 wheel at
`69028e5`; the v4.17 post-release verification used the v4.17.0 wheel at
`2119787`; the v4.18 post-release verification used the v4.18.0 wheel at
`15cea6c`; the v4.19 post-release verification used the v4.19.0 wheel at
`fa85679`; the v4.20 post-release verification used the v4.20.0 wheel at
`5404480`; the v4.21 post-release verification used the v4.21.0 wheel at
`ea50173`; the v4.22 post-release verification used the v4.22.0 wheel at
`922481d`; the v4.23 post-release verification used the v4.23.0 wheel at
`d438954` (metadata recorded in follow-up commit `cbcaa32`); the v4.24
post-release verification uses the v4.24.0 wheel at `be445f1` (metadata recorded
in follow-up commit `48f34ab`); the v4.25 post-release verification uses the
v4.25.0 wheel at `36d3852` (metadata recorded in follow-up commit `b32d6bc`).
The v4.27 post-release verification uses the v4.27.0 wheel at `5dfab07`
(metadata recorded in follow-up commit `a2bb7fa`). The v4.28 post-release
verification uses the v4.28.0 wheel at `491c33c` (metadata recorded in follow-up
commit `47a6300`). The current v4.33 post-release verification uses the v4.33.0
wheel at `d0d320b` (metadata recorded in the same consumer commit) and CI run
`35547832896`. The previous v4.32 post-release verification uses the v4.32.0
wheel at `ec4ae11` (metadata recorded in the same consumer commit) and CI run
`35546793151`. The previous v4.31 post-release verification uses the v4.31.0
wheel at `c16f763` (metadata recorded in the same consumer commit) and CI run
`35545604117`. The previous v4.30 post-release verification uses the v4.30.0
wheel at `d378564` (metadata recorded in the same consumer commit) and CI run
`35544440919`. The previous v4.29 post-release verification uses the v4.29.0
wheel at `1c7a151` (metadata recorded in follow-up commit `9660c8b`).

消费仓库的 v4.33 CI（run `35547832896`）已验证正常场景返回 0，三类注入均返回 1，验证公开
`sha256_file` API，并用消费方独立生成的 study bundle 验证五个 evidence role 和六条 provenance
binding。报告会保留在 workflow artifact 中，baseline 由人工审核后提交，CI 不会自动覆盖 baseline。
v4.32 的消费验收仍保留在 run `35546793151`，v4.31 仍保留在 run `35545604117`，v4.30 仍保留在
run `35544440919`。
v4.29 以前的消费 CI（run `35543025395`）也已验证正常场景返回 0，三类注入均返回 1。报告会保留在
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
