# LangGraph Agent Stack pilot

这是一个独立公开项目的技术预演，不代表该项目维护者采用或认可 Agent
Regression Kit。目标是验证：不修改业务图的情况下，能否从一个真实 LangGraph
运行时事件流生成统一 `AgentTrace`，并在最终业务结果变化时阻断比较。

候选项目固定到本次验证的 commit：
`a8a2dac566d46c48619ba94c69dfffb1b370520d`。

候选项目：
<https://github.com/Brescou/langgraph-agent-stack>

## 运行前提

- Python 3.12+；
- `uv`；
- 候选项目的依赖已安装；
- 不需要 LLM API Key，不访问真实搜索服务。

```bash
git clone https://github.com/Brescou/langgraph-agent-stack.git /tmp/langgraph-agent-stack
cd /tmp/langgraph-agent-stack
git checkout a8a2dac566d46c48619ba94c69dfffb1b370520d
uv sync
```

## 1. 运行候选项目自己的 mock eval

```bash
LLM_PROVIDER=mock SEARCH_PROVIDER=mock \
  uv run python -m evals --all --json --thresholds
```

本次验证结果：3 个数据集、8 个案例、8/8 通过，退出码 0；所有案例成本为
`$0.00`。候选项目的 `research_analysis` 数据集 2 个、`summariser` 3 个、
`talent_screening` 3 个。这里验证的是候选项目自己的结构化 mock eval，不是在线
模型质量。

## 2. 采集真实 LangGraph event stream

下面命令从候选项目的 `ResearchAgent` graph 捕获 `on_tool_start`、`on_tool_end`
和最终状态。`capture_trace.py` 在本项目内，候选项目不需要修改。

```bash
KIT=/path/to/agent-regression-kit
STACK=/tmp/langgraph-agent-stack

PYTHONPATH="$KIT/src" "$STACK/.venv/bin/python" \
  "$KIT/examples/external-pilot/langgraph-agent-stack/capture_trace.py" \
  --project-dir "$STACK" \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/baseline.trace.json"

# Run the Agent again to create a fresh candidate; do not copy the baseline.
PYTHONPATH="$KIT/src" "$STACK/.venv/bin/python" \
  "$KIT/examples/external-pilot/langgraph-agent-stack/capture_trace.py" \
  --project-dir "$STACK" \
  --run-id "langgraph-agent-stack-candidate" \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/candidate.trace.json"

PYTHONPATH="$KIT/src" python3 -m agent_regression compare \
  --config "$KIT/examples/external-pilot/langgraph-agent-stack/compare.config.json"
```

预期：正常候选退出码为 `0`，报告为 `passed: true`，并且 Trace 包含 3 个
`web_search` 工具调用。适配器通过工具边界采集实际传入的
`sub-query 1/2/3`；如果运行时事件只提供 `{}`，也不会从结果反推参数。
`claims` 来自候选项目实际输出的 `summary`、`findings`、`sources` 和
`confidence`，不是脚本预填的“永远通过”答案。

## 3. 验证合法变化不会误报

下面只改变最终展示文字和 run ID，结构化 claims 与工具行为不变。在
`claims-only` 模式下，比较应退出 `0`：

```bash
PYTHONPATH="$KIT/src" "$STACK/.venv/bin/python" \
  "$KIT/examples/external-pilot/langgraph-agent-stack/capture_trace.py" \
  --project-dir "$STACK" \
  --run-id "langgraph-agent-stack-wording" \
  --vary-presentation \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/candidate.trace.json"

PYTHONPATH="$KIT/src" python3 -m agent_regression compare \
  --config "$KIT/examples/external-pilot/langgraph-agent-stack/compare.config.json"
```

## 4. 在 Agent 执行过程中注入回归，确认会被阻断

下面三种用例发生在 Agent 运行过程中，不是生成 Trace 后直接改 JSON：

```bash
# 错误的搜索参数：在 web_search 的真实调用边界替换 query
PYTHONPATH="$KIT/src" "$STACK/.venv/bin/python" \
  "$KIT/examples/external-pilot/langgraph-agent-stack/capture_trace.py" \
  --project-dir "$STACK" \
  --mutate-search-query "unrelated topic" \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/candidate.trace.json"

# 跳过必要搜索：从 Agent 的工具集合移除 web_search
PYTHONPATH="$KIT/src" "$STACK/.venv/bin/python" \
  "$KIT/examples/external-pilot/langgraph-agent-stack/capture_trace.py" \
  --project-dir "$STACK" \
  --skip-search \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/candidate.trace.json"

# 误读最终结论：在 summariser 响应被 Agent 解释前修改 confidence
PYTHONPATH="$KIT/src" "$STACK/.venv/bin/python" \
  "$KIT/examples/external-pilot/langgraph-agent-stack/capture_trace.py" \
  --project-dir "$STACK" \
  --mutate-summary-confidence 0.10 \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/candidate.trace.json"
```

三种用例的 compare 预期退出码均为 `1`，分别应能看到工具参数、工具调用数量或
`final_answer.claims` 的阻断差异。它们是本项目的检测能力证明，不应被写成候选项目
的真实缺陷。

旧参数 `--mutate-confidence 0.10` 仍保留，用于单独验证比较器；它是在 Agent 运行
结束后修改结果，不能替代上面三种运行时注入。

## 5. 结果回归的旧示例（比较器专项）

```bash
PYTHONPATH="$KIT/src" "$STACK/.venv/bin/python" \
  "$KIT/examples/external-pilot/langgraph-agent-stack/capture_trace.py" \
  --project-dir "$STACK" \
  --mutate-confidence 0.10 \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/candidate.trace.json"

PYTHONPATH="$KIT/src" python3 -m agent_regression compare \
  --config "$KIT/examples/external-pilot/langgraph-agent-stack/compare.config.json"
```

预期退出码为 `1`，差异类别为 `result_interpretation`，路径为
`final_answer.claims`（其中的 `confidence` 从实际值变化为 `0.10`）。这只是检测能力证明，不应被写成候选项目的真实
缺陷；真实缺陷记录需要候选项目自己的版本变化或业务负责人确认。

## 已知边界

- `capture_trace.py` 是外部验证 harness，为了观察 event stream 和制造成对的
  确定性负向用例，会访问候选项目的私有 `_graph`/`_invoke_llm_with_retry`；这不是
  Agent Regression Kit 要求业务项目提供的稳定 API。稳定的框架接入边界只有
  `trace_from_langgraph_events(...)` 和业务方自己的工具边界采集。
- 该候选项目的 mock `web_search` 工具是普通 Python 节点内部调用，最终消息状态
  不包含工具调用。因此直接使用 `trace_from_langgraph_result` 会漏掉这部分生命周期；
  本预演使用新增的 `trace_from_langgraph_events` 从 LangGraph v2 事件流补齐它，
  并通过 `tool_input_resolver` 接入工具边界采集的真实参数。
- mock provider 的输出用于确定性接入和 CI，不证明真实模型事实性、搜索质量或业务
  正确性。
- 还没有候选项目维护者或独立业务团队的持续采用记录，因此它属于 P1 技术预演，
  不满足 P3 外部试点验收。
