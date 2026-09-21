# Independent consumer pilot / 独立消费项目验证

v4.15 introduced an end-to-end consumer repository that is separate from the
core checkout. After the v4.36.1 release, that consumer was upgraded and
re-verified against the immutable v4.36.1 wheel. Earlier release details remain
below as historical evidence:

[ANTAO94/agent-regression-pilot](https://github.com/ANTAO94/agent-regression-pilot)

v4.15 增加了一个与核心仓库分离的端到端消费项目；v4.36.1 发布后，消费项目又升级到
v4.36.1 wheel 并重新验收；早期版本细节保留为历史证据：

[ANTAO94/agent-regression-pilot](https://github.com/ANTAO94/agent-regression-pilot)

## v4.36.1 acceptance / v4.36.1 验收

The current consumer commit is
[`71e136d`](https://github.com/ANTAO94/agent-regression-pilot/commit/71e136d2b01ee7400d5fbe86e67f6f7e1887264b),
and its [GitHub Actions run 35569732974](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35569732974)
passed. The consumer downloads only this tagged Release asset and verifies its
hash during installation:

```text
https://github.com/ANTAO94/agent-regression-kit/releases/download/v4.36.1/agent_regression_kit-4.36.1-py3-none-any.whl
sha256: d6cab3a5f92f3157aba3e48d098797a36c07347a001ab73c55bd47371726c069
```

The workflow verifies `__version__ == 4.36.1`, records the consumer-owned
two-tool Agent, passes the normal Contract comparison, and requires exit code
`1` for wrong-resource, skipped-tool and result-misread regressions. It also
rebuilds the consumer-owned sampling study, verifies its report checksum, and
confirms that readiness remains `ready=false` while independent-user evidence
is pending. This proves public release compatibility for this Agent; it does
not convert the producer-side LangGraph pilot into independent adoption of
that feature.

消费项目只按 URL 和 SHA-256 安装正式发布的 v4.36.1 wheel，断言版本正确，并重新运行
由消费方维护的两工具 Agent、Contract、三类负向回归、sampling study 和 readiness。
正常场景通过，错误资源、跳过工具和结果误读均以退出码 `1` 被阻断；独立用户证据仍为
pending，因此 readiness 保持 `ready=false`。这证明了该 Agent 的公开发布兼容性，但不把
主仓库里的 LangGraph 技术预演包装成外部采用证据。

## v4.35 acceptance / v4.35 验收

The current consumer commit is
[`93baf5c`](https://github.com/ANTAO94/agent-regression-pilot/commit/93baf5c53ffcfb59fd187e12e0bf104d70dff7a6),
and its [GitHub Actions run 35551245268](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35551245268)
passed. The consumer installs only this immutable asset:

```text
https://github.com/ANTAO94/agent-regression-kit/releases/download/v4.35.0/agent_regression_kit-4.35.0-py3-none-any.whl
sha256: 86cf6608847e269b8f5c11dbd0764c65bfc0880089492a8f64b2a7a3635b300b
```

The workflow verifies `__version__ == 4.35.0`, builds and runs an independent
sampling-study bundle, independently checks the final report SHA-256 sidecar,
and invokes `readiness` with a consumer-generated manifest. The readiness
command returns `1` and reports `ready=false` because
`independent-user-study` is intentionally pending. The workflow also runs the
normal two-tool order Agent and requires exit code `1` for these injected
regressions: wrong resource, skipped `get_balance`, and a misread final result.

v4.35 消费验收使用不可变 wheel，断言版本为 `4.35.0`，由消费项目独立生成 sampling-study bundle，并重新计算最终
报告 SHA-256 sidecar；同时调用 readiness，明确验证 `independent-user-study` 为 pending、`ready=false`、退出码为 `1`。
正常两工具订单 Agent 通过，wrong resource、跳过 `get_balance`、错误解读最终结果三类注入均被退出码 `1` 阻断。

## Historical v4.34 consumer boundary / 历史 v4.34 消费边界

The pilot installed exactly this immutable Release asset for the historical
v4.34 evidence:

```text
https://github.com/ANTAO94/agent-regression-kit/releases/download/v4.34.0/agent_regression_kit-4.34.0-py3-none-any.whl
sha256: 5091bcd45c48eae7dc02179c7a3f01eb1d274d8c249bec66c8c1ca415a677b45
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

The consumer workflow ran on the v4.34 upgrade commit `7ef1cb6` and passed
(GitHub Actions run [`35548951626`](https://github.com/ANTAO94/agent-regression-pilot/actions/runs/35548951626)):

| Case / 用例 | Expected / 预期 | Observed / 实测 |
| --- | --- | --- |
| normal | exit 0 | pass |
| wrong resource (`999` instead of `123`) | exit 1 | blocked; required tool, argument, result and relation evidence |
| skipped `get_balance` | exit 1 | blocked; required tool, missing result association and claims evidence |
| report `shipped` for a `not_shipped` result | exit 1 | blocked; Contract assertion and result-interpretation evidence |

CI run: [Consumer Agent regression workflow](https://github.com/ANTAO94/agent-regression-pilot/actions/workflows/regression.yml)

The v4.34 consumer imports the public `sha256_file` helper from the released
wheel, hashes its reviewed baseline and asserts `__version__ == 4.34.0` before
exercising the Agent boundary. It also builds an independent sampling-study
bundle, verifies the required `input`, `tool_schema`, `adapter`,
`provider_output` and `dataset` evidence roles, and binds six controlled fields
to matching provenance values with the published `study` CLI. This confirms
that the v4.34 run-identity and report-sidecar boundaries are available through
the published artifact, not only from the core checkout.

v4.34 消费项目从发布 wheel 导入公开的 `sha256_file`，对审核过的 baseline 计算哈希，并在
运行 Agent 边界前断言 `__version__ == 4.34.0`；同时由独立消费方创建 sampling-study bundle，
通过发布的 `study` CLI 校验 `input`、`tool_schema`、`adapter`、`provider_output`、`dataset` 五类
必需 evidence role，并把六个描述字段绑定到对应 provenance 值。这证明 v4.34 运行身份和报告交接边界确实
随发布包可用，而不是只在核心仓库源码路径中可用；报告 sidecar 也由消费方独立重算校验。

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
commit `47a6300`). The current v4.34 post-release verification uses the v4.34.0
wheel at `7ef1cb6` (metadata recorded in the same consumer commit) and CI run
`35548951626`. The previous v4.33 post-release verification uses the v4.33.0
wheel at `d0d320b` (metadata recorded in the same consumer commit) and CI run
`35547832896`. The previous v4.32 post-release verification uses the v4.32.0
wheel at `ec4ae11` (metadata recorded in the same consumer commit) and CI run
`35546793151`. The previous v4.31 post-release verification uses the v4.31.0
wheel at `c16f763` (metadata recorded in the same consumer commit) and CI run
`35545604117`. The previous v4.30 post-release verification uses the v4.30.0
wheel at `d378564` (metadata recorded in the same consumer commit) and CI run
`35544440919`. The previous v4.29 post-release verification uses the v4.29.0
wheel at `1c7a151` (metadata recorded in follow-up commit `9660c8b`).

消费仓库的 v4.34 CI（run `35548951626`）已验证正常场景返回 0，三类注入均返回 1，验证公开
`sha256_file` API，并用消费方独立生成的 study bundle 验证五个 evidence role 和六条 provenance
binding，并独立验证最终报告的 SHA-256 sidecar。报告会保留在 workflow artifact 中，baseline 由人工审核后提交，CI 不会自动覆盖 baseline。
v4.33 的消费验收仍保留在 run `35547832896`，v4.32 仍保留在 run `35546793151`，v4.31 仍保留在 run `35545604117`，v4.30 仍保留在
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
