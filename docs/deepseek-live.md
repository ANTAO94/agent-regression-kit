# DeepSeek live provider check / DeepSeek 真实供应商检查

## 中文

这个检查使用 DeepSeek 当前价格最低的 `deepseek-flash`，运行一次真正的工具型
Agent 闭环：模型先选择 `get_order`，本地 Fixture 返回审核过的订单状态，模型再
输出结构化业务结论。生成的 Trace 会与 `baselines/order-123.trace.json` 比较。

它与离线框架测试的职责不同：离线测试证明接入代码稳定、可复现；真实供应商检查
证明当前远端模型仍能遵守工具参数和业务契约。远端模型的自然语言可能变化，因此
比较使用 `claims-only`，但工具名、参数、结果和 claims 仍然严格检查。

### 本地运行

```bash
export DEEPSEEK_API_KEY='在终端中设置，不要写入仓库'
python examples/deepseek_live_agent_example.py
agent-regression validate --trace work/deepseek-live.trace.json
agent-regression compare --config examples/deepseek-live/compare.config.json
```

默认使用 `deepseek-flash`、关闭思考模式，并把每次输出限制为 64 tokens。一次检查
通常包含两次短请求：工具选择和最终答案。不要把 API Key 写进 `.env`、Trace、
测试 Fixture、命令输出或 Git 历史。

GitHub 仓库中将密钥配置为 Actions Secret `DEEPSEEK_API_KEY`，然后手动运行
`DeepSeek live provider` 工作流。工作流也会在每周日 UTC 02:17 自动执行；周末
不在官方列出的工作日峰值计费窗口内。供应商可能调整模型和价格，运行前应复核
官方定价页面。

## English

This check uses the lowest-priced current DeepSeek model, `deepseek-flash`, to
run a real tool-Agent loop. The model selects `get_order`, a local reviewed
fixture returns the order state, and the model emits structured business
claims. The resulting Trace is compared with `baselines/order-123.trace.json`.

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
```

The example defaults to `deepseek-flash`, disables thinking, and caps each
response at 64 tokens. A normal check makes two short paid requests. Configure
the GitHub Actions secret `DEEPSEEK_API_KEY` and run the `DeepSeek live
provider` workflow manually, or let its weekly Sunday schedule run off the
documented weekday peak-price windows.

Pricing and model names are external state. Verify the official
[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) and
[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/) documentation
before changing the schedule or model.
