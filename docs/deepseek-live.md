# DeepSeek live provider check / DeepSeek 真实供应商检查

## 中文

这个检查使用 `deepseek-flash` 运行两种真正的工具型 Agent 闭环：

1. 单工具：`get_order → final_answer`；
2. 多工具依赖链：`get_order → check_refund_eligibility → final_answer`。

第二个场景要求模型把第一步结果中的订单号、状态和金额正确传入第二个工具。工具
顺序由 `required_tool_sequence` 固定，因此它验证的是跨步骤数据传递，不宣称验证
模型的自主工具规划。两份 Trace 分别与 `baselines/order-123.trace.json` 和
`baselines/order-refund.trace.json` 比较。

它与离线框架测试的职责不同：离线测试证明接入代码稳定、可复现；真实供应商检查
证明当前远端模型仍能遵守工具参数和业务契约。远端模型的自然语言可能变化，因此
比较使用 `claims-only`，但工具名、参数、结果和 claims 仍然严格检查。

### 本地运行

```bash
export DEEPSEEK_API_KEY='在终端中设置，不要写入仓库'
python examples/deepseek_live_agent_example.py
agent-regression validate --trace work/deepseek-live.trace.json
agent-regression compare --config examples/deepseek-live/compare.config.json

python examples/deepseek_multi_tool_agent_example.py
agent-regression validate --trace work/deepseek-multi-tool.trace.json
agent-regression compare --config examples/deepseek-multi-tool/compare.config.json
```

默认使用 `deepseek-flash`、关闭思考模式；单工具和多工具场景分别需要两次和三次
短请求。不要把 API Key 写进 `.env`、Trace、
测试 Fixture、命令输出或 Git 历史。

GitHub 仓库中将密钥配置为 Actions Secret `DEEPSEEK_API_KEY`，然后手动运行
`DeepSeek live provider` 工作流。工作流也会在每周日 UTC 02:17 自动执行；周末
不在官方列出的工作日峰值计费窗口内。供应商可能调整模型和价格，运行前应复核
官方定价页面。

## English

This check runs two real `deepseek-flash` tool-Agent loops:

1. `get_order → final_answer`;
2. `get_order → check_refund_eligibility → final_answer`.

The second case requires the model to copy order ID, status and paid amount
from the first result into the second call. `required_tool_sequence` fixes tool
order, so this tests cross-step data propagation rather than claiming fully
autonomous tool planning. The traces are compared with the reviewed single-
and multi-tool baselines.

Offline framework tests prove deterministic integration behavior. This live
check proves that the current hosted model still respects tool arguments and
the business contract. Natural-language prose is compared in `claims-only`
mode; tool names, arguments, results and claims remain strict.

### Run locally

```bash
export DEEPSEEK_API_KEY='set this in your shell, never in the repository'
python examples/deepseek_live_agent_example.py
agent-regression validate --trace work/deepseek-live.trace.json
agent-regression compare --config examples/deepseek-live/compare.config.json

python examples/deepseek_multi_tool_agent_example.py
agent-regression validate --trace work/deepseek-multi-tool.trace.json
agent-regression compare --config examples/deepseek-multi-tool/compare.config.json
```

The examples default to `deepseek-flash` and disable thinking. The single- and
multi-tool checks make two and three short paid requests respectively. Configure
the GitHub Actions secret `DEEPSEEK_API_KEY` and run the `DeepSeek live
provider` workflow manually, or let its weekly Sunday schedule run off the
documented weekday peak-price windows.

Pricing and model names are external state. Verify the official
[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) and
[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/) documentation
before changing the schedule or model.
