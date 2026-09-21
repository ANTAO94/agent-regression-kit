# P1 LangGraph 项目接入验证

日期：2026-09-21。对应规划：[`product-iteration-plan.zh-CN.md`](product-iteration-plan.zh-CN.md)。

## 结论

已对独立公开项目
[`Brescou/langgraph-agent-stack`](https://github.com/Brescou/langgraph-agent-stack)
做技术预演，固定上游 commit：
`a8a2dac566d46c48619ba94c69dfffb1b370520d`。

结果：候选项目自带的 mock eval 在本机通过；真实 `ResearchAgent` LangGraph
event stream 能被 Agent Regression Kit 转换为有效 Trace；工具事件虽然只暴露空
输入，但外部工具边界采集到了实际传入的 `sub-query 1/2/3`。重新执行的
baseline/candidate 和合法措辞变化均通过；错误搜索参数、跳过必要搜索、运行中
误读总结均被 compare 以退出码 `1` 阻断。这是 P1 的技术接入证据，不是上游项目
采用声明，也不是在线模型质量结论。

## 可复现结果

| 检查 | 命令/入口 | 结果 |
| --- | --- | --- |
| 上游环境 | `uv sync`，Python 3.13.15 | 完成 |
| 上游 mock eval | `LLM_PROVIDER=mock SEARCH_PROVIDER=mock uv run python -m evals --all --json --thresholds` | 3 个数据集、8 个案例、8/8 通过、退出码 0 |
| 上游真实 API smoke | `TestClient` 调用 `POST /run`，mock provider | HTTP 200，返回结构化研究结果 |
| 事件流采集 | `capture_trace.py` + 工具边界 instrumentation | 真实 `on_tool_start/end`、`sub-query 1/2/3` 参数与最终结果进入 Trace |
| wheel 独立环境 | 当前构建 wheel 安装到候选项目 `.venv` | `agent_regression` 从 site-packages 导入，未使用核心仓库 `src/` |
| 正常重新执行 | `compare.config.json` | 退出码 0，`passed: true`，无阻断差异 |
| 合法变化 | `--vary-presentation` | 退出码 0；claims-only 忽略展示文字变化 |
| 错误搜索参数 | `--mutate-search-query "unrelated topic"` | 退出码 1；定位工具参数、工具结果和 Contract required tool |
| 跳过必要搜索 | `--skip-search` | 退出码 1；定位工具数量、结果关联、claims 和 required tool |
| 运行中结果误读 | `--mutate-summary-confidence 0.10` | 退出码 1；定位 `final_answer.claims` |
| 比较器专项 | `--mutate-confidence 0.10` | 退出码 1；只证明比较器识别 Trace 变化，不冒充运行时缺陷 |

上游 mock eval 的所有案例成本为 `$0.00`。候选项目的测试和评测是它自己的质量
证据；本项目只负责接入其运行证据、比较和回归门禁。

`capture_trace.py` 是本项目的外部验证 harness。为了观察候选 graph 并制造确定性
负向用例，它访问候选项目的私有 `_graph` 和 `_invoke_llm_with_retry`；这不应被理解
为业务项目的长期接入要求。长期接入只需要框架事件、真实工具边界采集和业务方的
claims/Contract。

## 本轮实现

新增 `trace_from_langgraph_events(...)`，处理 LangGraph/LangChain v2 event stream：

- `on_tool_start` → `tool_call`；
- `on_tool_end` → 成功 `tool_result`；
- `on_tool_error` → 带 `is_error=true` 的 `tool_result`；
- 工具输入缺失时默认保留 `{}`；若接入方在真实工具边界采集了参数，可通过
  `tool_input_resolver(event, ordinal)` 显式补入；
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

当前 P1 的技术预演和 wheel 边界已完成；下一步不是继续增加注入开关，而是获得
项目负责人审核的业务 baseline，并记录真实改动周期中的误报/漏报。只有出现实际
噪音和排障样本后，才进入 P2，针对动态字段、无害额外查询或允许路径变化做成对
规则。维护者采用、业务案例和 P3 外部试点仍未完成。
