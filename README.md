# Agent Regression Kit

[![CI](https://github.com/ANTAO94/agent-regression-kit/actions/workflows/regression.yml/badge.svg)](https://github.com/ANTAO94/agent-regression-kit/actions/workflows/regression.yml)
[![Release](https://img.shields.io/github/v/release/ANTAO94/agent-regression-kit)](https://github.com/ANTAO94/agent-regression-kit/releases)
[MIT](LICENSE)

**给 AI Agent 加回归测试：改了 Prompt、模型或代码后，检查它是否调用了错误工具、传错参数，或得出了错误的业务结论。**

[English](README.en.md) · [详细使用手册](docs/user-manual.zh-CN.md) · [后续迭代方案](docs/product-iteration-plan.zh-CN.md) · [P1 真实项目接入](docs/p1-langgraph-agent-stack-validation.md) · [技术方案](docs/technical-design.zh-CN.md)

Python ≥3.9 · 当前版本 v4.36.0 · 核心无必需第三方运行时依赖。

## 1. 它怎么帮你发现问题？

假设你的 Agent 负责查询订单：

| 同一个请求：查询订单 123 | 工具调用 | 最终业务结论 | 期望 |
| --- | --- | --- | --- |
| 修改前，经你审核正确 | `get_order(order_id="123")` | 未发货 | 保存为参考 |
| 修改后，正常运行 | 查询相同订单 | 未发货 | 通过 |
| 修改后，发生回归 | 查错订单、换错工具或传错参数 | 或把“未发货”说成“已发货” | 报告差异并阻断 |

你提供**一份审核过的运行记录、一份新运行记录，以及可选的检查规则**。框架负责比较、检查规则、输出报告，并用退出码告诉 CI 是否通过。

先记住四个名字：

| 名词 | 意思 | 示例文件 |
| --- | --- | --- |
| Trace（运行记录） | 实际工具调用、参数、结果和最终回答 | `*.trace.json` |
| Baseline（基线） | 经你审核正确的参考 Trace | `baselines/order-123.trace.json` |
| Candidate（候选记录） | 修改后重新运行 Agent 得到的 Trace | `work/candidate.trace.json` |
| Contract（检查规则） | 必须满足的条件，例如订单状态为“未发货” | 配置文件里的 `contract` |

框架不会自动知道业务正确答案；你需要审核 baseline，并定义重要的业务约束。

## 2. 先跑通：一个成功案例，一个失败案例

以下命令适用于 macOS/Linux Bash/Zsh，也可在 Windows WSL 执行。请在同一终端按顺序操作。安装需要联网；这组示例使用固定脚本和本地工具结果，**不需要 API Key，不会请求模型**。

### 安装

```bash
git clone --branch v4.36.0 https://github.com/ANTAO94/agent-regression-kit.git
cd agent-regression-kit
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
agent-regression --version
```

应看到 `agent-regression 4.36.0`。后续命令均在仓库根目录执行，并保持虚拟环境已激活。

### 录制正常版本并比较

仓库已附带示例 baseline，无需自己先生成：

```bash
agent-regression record \
  --scenario examples/order-123/candidate-ok.scenario.json \
  --out work/candidate.trace.json
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/candidate.trace.json \
  --out work/reports/compare.json
```

预期 JSON 中包含 `"passed": true`、`"blocking_difference_count": 0`，退出码为 **0**。报告在 `work/reports/compare.json`。

### 故意跑一个错误版本

```bash
agent-regression record \
  --scenario examples/order-123/candidate-regression.scenario.json \
  --out work/bad.trace.json
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/bad.trace.json \
  --out work/reports/regression.json
```

这个样例把工具换成 `lookup_order`、把订单号从字符串改成数字，并把“未发货”回答成“已发货”。

预期 `"passed": false`，退出码为 **1**。这是成功抓住了回归，不是安装失败。打开 `work/reports/regression.json`，查看 `differences`：

| 报告字段 | 怎么读 |
| --- | --- |
| `category` | 哪类差异，例如工具参数或业务结论变化 |
| `path` | 差异发生在哪个字段 |
| `baseline` / `candidate` | 原来是什么，现在是什么 |
| `allowed` | 策略是否明确允许这项差异 |

### 用页面查看

```bash
agent-regression ui
```

打开终端提示的本地地址，选择刚才生成的 Trace 或报告文件。配置页面可导出 JSON，保存后再交给 CLI 使用。页面不会替你运行 Agent、自动保存配置或接受 baseline。

## 3. 怎么配置检查项和噪音过滤？

**baseline 保存参考数据，config 保存检查规则。** 默认比较工具调用、参数、结果和最终回答；需要允许措辞变化、忽略动态字段或增加业务断言时，再加配置。

在项目根目录创建 `.agent-regression` 文件夹，把下面内容保存为 **`.agent-regression/config.json`**：

```json
{
  "baseline": "baselines/order-123.trace.json",
  "candidate": "work/candidate.trace.json",
  "report": "work/reports/compare.json",
  "final_answer_mode": "claims-only",
  "contract": {
    "required_claims": [
      "final_answer.claims.order_status"
    ],
    "assertions": [
      {
        "path": "final_answer.claims.order_status",
        "equals": "not_shipped"
      },
      {
        "path": "tool_results[*].is_error",
        "equals": false
      }
    ],
    "must_call": [
      {
        "tool": "get_order",
        "arguments": {
          "order_id": "123"
        }
      }
    ],
    "must_not_call": [
      "cancel_order",
      "refund"
    ],
    "ignore_paths": [
      "tool_results[*].result.request_id"
    ]
  }
}
```

使用第 2 节生成的正常候选记录运行：

```bash
agent-regression compare --config .agent-regression/config.json
```

这份配置要求：

- 必须提供 `order_status` 业务结论，且值为 `not_shipped`。
- 工具结果不能报错；必须用字符串订单号 `"123"` 调用 `get_order`。
- 不能调用取消订单或退款工具。
- 忽略返回结果中的动态 `request_id`；样例没有该字段，但真实接口经常有。
- `claims-only` 允许回答换一种说法，仍比较结构化结论、工具参数和结果。

**Claims 是从 Agent 实际输出中提取的业务事实**，例如 `{"order_status": "not_shipped"}`，由接入代码提供。不能直接填期望答案，否则会掩盖错误；没有可靠 claims 时，先保留默认的最终文字比较。

配置放在 `.agent-regression/` 时，文件路径相对于项目根目录；放在其他目录时，相对于配置文件所在目录。CLI 显式传入的路径相对于当前终端目录。

更多规则按需查阅：[配置手册](docs/user-manual.zh-CN.md) · [允许额外查询](examples/path-variation/README.md) · [最终状态和等价动作](docs/state-equivalence.md)。放宽比较时，要同时约束订单号、金额等重要字段和禁止的副作用。

### v4.13 的安全配置：失败尝试和未声明状态

如果一个写操作先失败、没有成功重试，不能只因为工具名和参数相同就让它通过。普通业务
回归可以使用严格默认值；如果业务确实允许一次失败后重试，必须把策略写出来：

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

这份策略要求：必须有成功动作；最多允许一次失败尝试；声明的订单状态必须存在且相同；其余
未忽略的 world state 变化也会被报告为 `unexpected_state_change`。如果你继续使用旧的
`allow_failed_expected`，`agent-regression check --config ...` 会给出迁移诊断，但不会偷偷改变
旧配置的语义。完整说明见 [v4.13 验收记录](docs/v4.13-acceptance.md) 和
[成熟度演进方案](docs/maturity-evolution-plan.zh-CN.md)。

## 4. 如何做可审计的外部评测？

如果你要把“框架发现了多少问题”作为公开数字，不能把标签直接塞进待测 Trace。v4.14 提供
三步流水线：

```bash
agent-regression benchmark prepare --manifest benchmark/manifest.json
agent-regression benchmark decide \
  --manifest benchmark/manifest.json \
  --out work/benchmark/decisions.json
agent-regression benchmark score \
  --manifest benchmark/manifest.json \
  --decisions work/benchmark/decisions.json \
  --out work/benchmark/score.json
```

`prepare` 校验不可变 revision、数据/拆分/Contract/证据/标签 SHA-256 和样本覆盖；`decide`
只读取 Trace 与规则，不读取标签语义；`score` 校验 decision digest 后才读取标签，输出
true pass、true block、false alarm、missed failure 和 Wilson 95% 区间。`unsupported` 会被
明确保留，不会从分母中静默删除。manifest 格式、输入 JSON 和限制见
[v4.14 验收记录](docs/v4.14-acceptance.md)。

## 5. 怎么接入自己的 Agent？

前面的 `record --scenario` 是脚本演示。接入真实项目时，需要**实际运行你的 Agent，并把工具调用、返回结果和最终输出记录成 Trace**。

| 你的情况 | 接入入口 |
| --- | --- |
| 使用 PydanticAI、OpenAI Agents SDK、LangGraph | [框架结果转换器](docs/framework-integrations.md)，可选依赖的 Python 要求见该文档 |
| 自己写的 Python Agent | [callback 示例](examples/framework_callback_example.py)，在工具执行边界记录 |
| 已有工具开始/结束回调 | [事件接入示例](examples/langchain_core_event_example.py) |
| 先验证 MCP 工具交互 | [MCP 示例](examples/mcp_record_example.py)，工具协议验证与完整 Agent 回归范围不同 |

先跑 callback 示例，理解记录流程：

```bash
python examples/framework_callback_example.py
agent-regression validate --trace work/framework-callback.trace.json
```

检查 `work/framework-callback.trace.json` 中的参数、工具结果和业务结论，确认正确后，**首次**保存基线：

```bash
agent-regression baseline accept \
  --trace work/framework-callback.trace.json \
  --out baselines/my-agent.trace.json
```

改动 Agent 后，重新录制并比较：

```bash
python examples/framework_callback_example.py
agent-regression compare \
  --baseline baselines/my-agent.trace.json \
  --candidate work/framework-callback.trace.json \
  --out work/reports/my-agent.json
```

在 [callback 示例](examples/framework_callback_example.py)中，需要替换的部分是：

| 代码位置 | 你要做什么 |
| --- | --- |
| `invoke_framework(request, context)` | 接入你自己的 Agent 执行逻辑 |
| `context.call_tool(...)` | 让工具执行经过记录边界；已有框架也可用事件回调 |
| `context.final_answer(text, claims)` | 记录实际答案及从中提取的业务结论 |
| `FixtureTools` | 当前使用固定返回值；真实场景按需提供工具执行器 |

样例按工具结果生成答案；你自己的模型 Agent 应记录模型实际回答，不能重新拼一个“正确答案”替代它。

**baseline accept 只校验并保存文件，不判断业务正确性。** 基线应人工审核并提交 Git。后续每次只生成 candidate 并比较，不要在 CI 中自动覆盖 baseline。接入后故意改错一次参数，确认门禁失败。

### 5.1 用一个独立 LangGraph 项目做技术预演

仓库提供一条可复现的[独立项目接入验证](docs/p1-langgraph-agent-stack-validation.md)，
候选项目是公开的 `Brescou/langgraph-agent-stack`，不改候选项目源码，使用它的
`LLM_PROVIDER=mock` 运行模式。它验证了一个实际接入问题：有些 LangGraph 在普通
Python 节点中执行工具，最终 `messages` 里没有工具调用；这时应从
`graph.astream_events(..., version="v2")` 收集生命周期，再调用
`trace_from_langgraph_events(...)`。

本次技术预演使用仓库内提交的固定官方资料快照，问题是 LangGraph 的
checkpointer、store、`thread_id` 和内存检查点是否跨进程保留。上游 mock eval 为
8/8 通过；真实 LangGraph event stream 经过工具边界采集后，3 个检索参数、资料
来源和最终事实断言都会进入 Trace。提交到仓库的 `baseline.trace.json` 是本项目
维护者针对固定资料审查后的参考记录，不是外部业务负责人审批的生产基线；CI 每次
只生成 candidate，不会和 candidate 一起重新生成 baseline。

正常运行、展示文案变化和证据 ID 顺序变化退出 0；错误搜索参数、跳过必要搜索、
把 checkpointer 误判成跨线程分别退出 1。这里的“误读”是固定资料上的确定性
运行时负向注入，证明契约能拦截事实变化，不代表上游项目真实存在该缺陷，也不代表
真实模型的事实性质量。完整命令、资料快照、断言和限制见[示例目录](examples/external-pilot/langgraph-agent-stack/README.md)。

## 6. 怎么放进 CI？

在你自己的项目中准备：

| 文件 | 谁来提供 |
| --- | --- |
| `scripts/record_agent.py` | 你编写的 Agent 运行和记录入口，每次生成新的 candidate |
| `baselines/order-123.trace.json` | 审核并提交 Git 的基线 |
| `.agent-regression/config.json` | 第 3 节策略，按自己的场景修改路径和断言 |

下面假定记录入口输出 `work/candidate.trace.json`。框架**不会自动生成 `scripts/record_agent.py`**，可从第 4 节示例改写；还需安装自己 Agent 所需的依赖。

保存为 `.github/workflows/agent-regression.yml`：

```yaml
name: Agent regression
on: [push, pull_request]

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.11"
      - name: Install regression kit
        run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git@v4.36.0"
      - name: Run your Agent and record its trace
        run: python scripts/record_agent.py
      - name: Compare with the reviewed baseline
        run: agent-regression compare --config .agent-regression/config.json
      - name: Upload report even after failure
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: agent-regression-report
          path: work/reports/
          if-no-files-found: error
```

退出码 **0 = 通过，1 = 回归，2 = 输入或配置错误**。非零退出码让 CI 失败，失败时仍上传报告。不要给比较命令加 `|| true` 或 `continue-on-error`。

先本地跑通，再开启 CI。模型密钥使用 GitHub Secrets，并在录制边界配置脱敏。JUnit、Markdown 和可复用 Action 的完整示例见[使用手册](docs/user-manual.zh-CN.md)。

## 7. 新项目和性能基线

### 7.1 新项目一条命令起步

如果你还没有接入代码，先在自己的 Agent 项目根目录执行：

```bash
agent-regression init
python scripts/record_agent.py --variant normal --out work/my-agent.trace.json
agent-regression check --config .agent-regression/config.json
agent-regression compare --config .agent-regression/config.json
```

模板会生成一个由本地 Fixture 产生的 starter baseline、候选 Trace、严格 Contract、双语说明和固定到当前
Release 的 GitHub Actions。starter baseline 只证明模板能运行，不代表你的业务已经审核通过；接入真实 Agent 后必须重新审查并显式接受 baseline。正常场景退出 0；用 `--variant wrong-resource`、
`skip-tool` 或 `misread-result` 会故意制造可解释的回归并退出 1。完整接入边界见生成在
你项目中的 `AGENT_REGRESSION.md` 和[使用手册](docs/user-manual.zh-CN.md)。

### 7.2 性能基线

框架提供不调用模型的确定性性能基线：

```bash
agent-regression performance run --out work/performance-baseline.json
# 首次建立同一环境的稳定参考后再提交 performance/reference.json
mkdir -p performance
cp work/performance-baseline.json performance/reference.json
agent-regression performance gate \
  --current work/performance-baseline.json \
  --baseline performance/reference.json \
  --out work/performance-gate.json
```

默认耗时回退超过 20% 报警，超过 40% 阻断；结果必须在相同 Python、操作系统和硬件条件下比较。
详见[性能基线说明](docs/performance.md)。

### 7.3 检查项目是否达到最终成熟度门槛

当你需要把测试结果交给 reviewer 或作为发布依据时，使用 `readiness` 审计，而不是只看测试数量：

```bash
agent-regression readiness \
  --manifest work/readiness.json \
  --format markdown \
  --out work/readiness.md
```

它会验证 benchmark/performance 报告的真实 JSON 字段、引用文件 SHA-256、300 个留出样本/50 个失败样本、
99% 失败召回、5% 误报、10,000 条 Trace/60 秒/512 MiB 峰值 RSS（必须低于该值）等门槛。真实首次用户研究和真正未见任务域属于
`external` 检查；没有独立证据时必须显示 `pending`，命令返回 1，不会被本地测试“自动证明”。完整清单格式见
[成熟度审计说明](docs/readiness-audit.md)。

## 8. 验证到了什么程度？

当前适合本地开发与团队 CI 试点。v4.36 发布记录 **293 项测试通过**，并验证构建、干净环境安装、
首用模板、性能 smoke、独立消费仓库升级、多个任务域的公开/前瞻评测，以及记录式 study 证据的
baseline/run/policy 完整性校验、evidence index 来源清单和 provenance 语义绑定。

| 验证类型 | 已有证据 | 能说明什么 |
| --- | --- | --- |
| 真实框架 + 确定性模型/工具 | PydanticAI、OpenAI Agents、LangGraph、LangChain Core 的[兼容 CI](https://github.com/ANTAO94/agent-regression-kit/actions/workflows/framework-compatibility.yml) | 框架运行和 Trace 接入可用，不等于在线模型质量验证 |
| 独立 LangGraph 项目技术预演 | [Brescou/langgraph-agent-stack 接入记录](docs/p1-langgraph-agent-stack-validation.md)：mock eval 8/8、真实参数采集、合法变化 0、三类运行时回归 1 | 证明独立项目可以从工具边界接入并阻断回归；不代表上游采用或在线模型质量 |
| 在线模型 | [DeepSeek 实测](docs/deepseek-live.md)：订单查询和两步工具依赖 | 已记录真实模型调用，工具顺序由测试策略约束 |
| 外部公开轨迹 | [τ²-bench 零售数据](docs/tau2-independent-validation.md)：420 个适用场景，267 正确放行、153 正确阻断、0 误报、0 漏报 | 当前规则在这份固定数据上的结果 |
| 独立消费仓库 | [agent-regression-pilot](docs/consumer-pilot.md)：正常退出 0，错资源/漏工具/结果误读均退出 1 | 发布 wheel、公开 API、Contract 和 CLI 在独立仓库中的接入边界 |
| 首用模板 | `agent-regression init`：自动生成 baseline/candidate/Contract/CI，并提供 3 个故意失败变体 | 新用户不需要先读核心源码就能跑通通过与阻断 |
| 性能基线 | [性能说明](docs/performance.md)：small/medium 固定生成器、环境记录和 20%/40% 门禁 | 发现框架自身明显回退，不代表模型或生产 SLA |
| Prospective 评测 | [τ² 独立验证](docs/tau2-independent-validation.md)：o4-mini 结果文件哈希绑定，420 个可判定样本、126 个失败样本 | 模型结果文件级留出证据，不代表未见任务域泛化 |
| 第二任务域 | [τ² airline 验证](docs/tau2-independent-validation.md)：120 个适用场景、69 个失败样本、100% 失败召回、3.92% 误报率 | 证明契约逻辑可跨到航空域；仍不是所有未见任务分布的泛化保证 |
| 第三任务域与 actor 边界 | [τ² telecom 验证](docs/tau2-independent-validation.md)：364 个 assistant-write 场景，公开结果 147/217/0/0；prospective o4-mini 失败召回 98.63%、误报 6.21% | 证明 user-owned 模拟器动作不会冒充 Agent 行为；环境断言仍是有限领域适配，不是通用状态还原 |
| 任务级留出代理 | [τ² telecom holdout](docs/v4.20-acceptance.md)：28 个互斥 holdout tasks、100 个可判定样本；公开 47/53/0/0，prospective 50/46/4/0 | 分区只读取 task ID，不读取 reward；仍来自同一公开任务族，不是独立来源泛化 |
| 独立来源矩阵 | [AgentDojo v4.22 验收](docs/v4.22-acceptance.md)：固定 commit/manifest SHA-256，5 条样本覆盖 workspace、banking、slack、travel，5/5 通过 | 证明跨 suite 的外部轨迹接入、逐样本 Contract 和 oracle 隔离；不是完整安全或泛化结论 |
| 跨模型攻击矩阵 | [AgentDojo v4.23 验收](docs/v4.23-acceptance.md)：固定 commit/manifest SHA-256，8 条样本覆盖两个模型 pipeline；4/4 正常路径通过、4/4 攻击路径按预期被 Contract 阻断 | 证明预期阻断结果可审计且不把外部安全标签当成规则；不是安全率或通用泛化结论 |
| Contract 预注册 | [AgentDojo v4.24 验收](docs/v4.24-acceptance.md)：8/8 Contract 使用 canonical JSON SHA-256 绑定，篡改规则 fail closed | 证明评测规则来源可追溯；不证明 Contract 完整或语义正确 |
| 决策重复性 | [AgentDojo v4.25 验收](docs/v4.25-acceptance.md)：同一固定矩阵重复 3 次，汇总报告、逐条报告和 Trace hash 全部稳定 | 证明固定输入下的决策产物可重复生成；不等于在线模型随机性或可靠性证明 |
| 独立攻击族 | [AgentDojo v4.26 验收](docs/v4.26-acceptance.md)：新增 ignore_previous 四条样本，覆盖四个 suite，2 条通过、2 条按预期阻断 | 证明不同攻击类型可进入同一审计 gate；仍不是安全率或通用泛化 |
| 模型族矩阵 | [AgentDojo v4.27 验收](docs/v4.27-acceptance.md)：Claude 3.5 Sonnet pipeline 的四 suite important_instructions 样本，3 条通过、1 条按预期阻断 | 补充独立模型族证据；仍不是在线方差研究或通用泛化 |
| 重复运行采样证据 | [v4.28 验收](docs/v4.28-acceptance.md)：稳定性报告输出 Wilson 95% 区间，CI 用 30 次重复和 `--min-runs 30` 验证样本门槛 | 量化有限重复运行的不确定性；仍不是在线模型质量或总体可靠性结论 |
| 记录式采样研究 | [v4.29 验收](docs/v4.29-acceptance.md)：`study` 读取脱敏 Trace、provider/model provenance、输入/工具 schema 哈希和逐次运行证据 | 让真实 Agent 的外部采样可审计接入；仍不负责供应商执行或总体可靠性结论 |
| 证据文件完整性 | [v4.30 验收](docs/v4.30-acceptance.md)：为 baseline、每个 run Trace 和规范化 comparison policy 绑定 SHA-256，并验证篡改返回状态 2 | 防止 study bundle 在生成后被静默修改；不证明隐藏输入正确或样本具有代表性 |
| 证据来源清单 | [v4.31 验收](docs/v4.31-acceptance.md)：声明 input/tool schema/adapter 等来源角色，校验路径、摘要和必需角色并输出 evidence index | 让 reviewer 能复核结论依赖了哪些文件；不证明来源文件语义正确或覆盖完整 |
| 证据语义绑定 | [v4.32 验收](docs/v4.32-acceptance.md)：将 evidence descriptor 的受控字段绑定到 provenance.input/tool schema/adapter，哈希通过但语义错配仍返回状态 2 | 防止“文件未被修改但绑定了错误来源对象”；不证明 provenance 声明本身真实 |
| 运行身份绑定 | [v4.33 验收](docs/v4.33-acceptance.md)：进一步绑定 provider、model、dataset revision，并要求对应证据角色存在 | 防止 study 把结果归因到错误的供应商、模型或数据版本；不证明外部声明本身真实 |
| 报告流转完整性 | [v4.34 验收](docs/v4.34-acceptance.md)：study 支持对最终 JSON/Markdown/JUnit 报告写出标准 SHA-256 sidecar | 防止报告上传或交接后被静默替换；不证明报告内容本身正确 |
| 最终成熟度审计 | [v4.35 验收](docs/v4.35-acceptance.md) 与 [审计说明](docs/readiness-audit.md)：结构化检查样本、指标、性能和外部证据状态 | 防止降低门槛或把 pending 外部证据误报成 READY；不替代真实用户研究 |

τ² 等价规则根据这份数据中的误报调整过，再在同一数据上复测；**它不是未见过数据上的泛化成绩**。当前流程导入公开轨迹，不运行上游模拟器，也不代表上游采用本框架。

框架只能检查已记录证据和已配置规则。真实数据库状态需要你提供快照；隐藏副作用、自然语言事实判断和外部权限执行不由 Trace 比较自动保证。详见[能力限制](docs/limitations.md)。

## 9. 常见问题与文档

当前版本的接入和发布证据：[v4.36 验收记录](docs/v4.36-acceptance.md)。

| 问题 | 先检查 |
| --- | --- |
| 找不到 `agent-regression` 命令 | 激活 `.venv`，在该环境执行 `python -m pip install .` |
| 找不到 Trace 或示例 | 是否在仓库根目录，是否先录制再比较 |
| 退出码 1 | 查看报告差异；第 2 节错误样例就应返回 1 |
| 退出码 2 | 检查终端错误、JSON 格式、路径和 Trace 校验 |
| 改措辞也失败 | 提供真实 claims 后用 `claims-only`，保留业务断言 |
| 合法新路径被阻断 | 审查安全性后，显式配置允许的路径和额外调用 |

[中文手册](docs/user-manual.zh-CN.md) · [English manual](docs/user-manual.en.md) · [技术方案](docs/technical-design.zh-CN.md) · [后续成熟度方案](docs/maturity-evolution-plan.zh-CN.md) · [成熟度审计](docs/readiness-audit.md) · [API](docs/api.md) · [性能基线](docs/performance.md) · [独立消费项目](docs/consumer-pilot.md) · [τ² 独立验证](docs/tau2-independent-validation.md) · [航空域复现](examples/tau2-airline/README.md) · [电信域复现](examples/tau2-telecom/README.md) · [电信 holdout 验收](docs/v4.20-acceptance.md) · [AgentDojo v4.27 验收](docs/v4.27-acceptance.md) · [AgentDojo v4.26 验收](docs/v4.26-acceptance.md) · [AgentDojo v4.25 验收](docs/v4.25-acceptance.md) · [AgentDojo v4.24 验收](docs/v4.24-acceptance.md) · [AgentDojo v4.23 验收](docs/v4.23-acceptance.md) · [AgentDojo v4.22 验收](docs/v4.22-acceptance.md) · [AgentDojo v4.21 验收](docs/v4.21-acceptance.md) · [退款案例](examples/refund-business-case/README.md) · [升级](UPGRADING.md) · [变更](CHANGELOG.md) · [v4.20 验收](docs/v4.20-acceptance.md) · [v4.19 验收](docs/v4.19-acceptance.md) · [v4.18 验收](docs/v4.18-acceptance.md) · [v4.17 验收](docs/v4.17-acceptance.md) · [v4.16 验收](docs/v4.16-acceptance.md) · [v4.15 验收](docs/v4.15-acceptance.md) · [v4.14 验收](docs/v4.14-acceptance.md) · [v4.13 验收](docs/v4.13-acceptance.md) · [v4.12 验收](docs/v4.12-acceptance.md) · [发布完整性](docs/supply-chain.md) · [贡献](CONTRIBUTING.md) · [安全](SECURITY.md)
