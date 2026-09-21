# P1 LangGraph 项目接入验证

日期：2026-09-21。对应规划：[`product-iteration-plan.zh-CN.md`](product-iteration-plan.zh-CN.md)。

## 结论

已对独立公开项目
[`Brescou/langgraph-agent-stack`](https://github.com/Brescou/langgraph-agent-stack)
做技术预演，固定上游 commit：
`a8a2dac566d46c48619ba94c69dfffb1b370520d8`。

结果：候选项目自带的 mock eval 在本机通过；真实 `ResearchAgent` LangGraph
event stream 能被 Agent Regression Kit 转换为有效 Trace；把最终业务结果中的
`confidence` 从实际值改成 `0.10` 后，compare 返回退出码 `1` 并指出
`final_answer.claims`（报告中的 candidate 值包含 `confidence: 0.10`）。这是 P1 的技术接入证据，不是上游项目采用声明，
也不是在线模型质量结论。

## 可复现结果

| 检查 | 命令/入口 | 结果 |
| --- | --- | --- |
| 上游环境 | `uv sync`，Python 3.13.15 | 完成 |
| 上游 mock eval | `LLM_PROVIDER=mock SEARCH_PROVIDER=mock uv run python -m evals --all --json --thresholds` | 3 个数据集、8 个案例、8/8 通过、退出码 0 |
| 上游真实 API smoke | `TestClient` 调用 `POST /run`，mock provider | HTTP 200，返回结构化研究结果 |
| 事件流采集 | `capture_trace.py` | 真实 `on_tool_start/end` 与最终结果进入 Trace |
| 正常比较 | `compare.config.json` | 退出码 0 |
| 结果回归注入 | `--mutate-confidence 0.10` | 退出码 1，定位 `final_answer.claims`，报告同时给出 baseline/candidate claims |

上游 mock eval 的所有案例成本为 `$0.00`。候选项目的测试和评测是它自己的质量
证据；本项目只负责接入其运行证据、比较和回归门禁。

## 本轮实现

新增 `trace_from_langgraph_events(...)`，处理 LangGraph/LangChain v2 event stream：

- `on_tool_start` → `tool_call`；
- `on_tool_end` → 成功 `tool_result`；
- `on_tool_error` → 带 `is_error=true` 的 `tool_result`；
- 工具输入缺失时保留 `{}`，不猜测业务参数；
- 最终输出和 claims 仍由调用方提供，claims 必须从实际输出提取；
- 对未闭合的工具生命周期、未知 `run_id` 和无效事件返回明确错误。

这修复了 P1 预演暴露的具体缺口：真实项目的工具调用可能在普通 Python 节点内
发生，最终消息 state 没有这些调用，不能只依赖最终 state 转换器。

## 仍未完成

1. 该项目只有技术预演，不等于维护者采用。
2. 本次案例是确定性 mock 运行，尚未覆盖真实 provider 的重复运行和语义质量。
3. 尚未获得业务审核的 10–20 个案例；当前 8 个上游 mock eval case 不能替代业务
   baseline。
4. 尚未完成 P3 的 3 名独立使用者、3 个项目和持续两个周期的试点。

下一步进入 P1/P2 交界：把 event-stream 适配器加入框架兼容 CI，补一组工具参数、
工具结果错误和允许路径变化的真实项目契约样例，再根据实际失败样本改进规则，而
不是继续扩展与接入无关的评测矩阵。
