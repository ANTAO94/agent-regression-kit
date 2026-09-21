# 真实 Agent 框架集成 / Real Agent framework integrations

## 中文说明

Agent Regression Kit 可以把 PydanticAI、OpenAI Agents SDK 和 LangGraph 的
一次真实运行转换成统一且经过校验的 `AgentTrace`。框架仍然负责模型调用、
Agent 循环和工具执行；本项目只提取回归测试真正需要的证据：用户输入、工具名、
调用参数、工具结果、最终回答和业务事实（claims）。核心包不会强制安装任何 Agent
框架。

### 安装

这些框架的当前版本要求 Python 3.10 或更高版本：

```bash
pip install 'agent-regression-kit[frameworks]'
```

也可以只安装一个集成：`[pydantic-ai]`、`[openai-agents]` 或 `[langgraph]`。

### 接入已经完成的运行

```python
from agent_regression import trace_from_pydantic_ai_result

result = agent.run_sync("查询订单 123")
trace = trace_from_pydantic_ai_result(
    result,
    "查询订单 123",
    run_id="order-123",
    identity={"name": "order-agent", "version": "1.0.0"},
    claims_extractor=lambda output: {"order_status": "paid"},
)
```

OpenAI Agents SDK 使用 `trace_from_openai_agents_result(result, ...)`；LangGraph
使用 `trace_from_langgraph_result(state, ...)`，其中 `state` 包含 `messages`。
如果工具是在普通 Python 节点里执行、最终 `messages` 没有工具生命周期，则收集
`graph.astream_events(..., version="v2")` 的事件，使用
`trace_from_langgraph_events(events, final_output, ...)`；它会记录
`on_tool_start`、`on_tool_end` 和 `on_tool_error`。

转换器会读取框架产生的调用 ID、工具名、参数、工具结果和最终输出。
`claims_extractor` 由业务方提供，因为只有业务方知道哪些事实必须保持稳定。例如，
“订单已经付款”和“订单状态为 paid”文字不同，但可以产生相同的
`{"order_status": "paid"}`，从而避免把措辞变化误判成业务回归。

```python
events = [event async for event in graph.astream_events(state, version="v2")]
trace = trace_from_langgraph_events(
    events,
    final_output,
    request,
    run_id="research-123",
    claims_extractor=lambda output: {
        "confidence": output["confidence"],
        "findings_count": len(output["findings"]),
    },
)
```

如果 event stream 的 `on_tool_start.data.input` 是空对象或缺失，而工具在普通
Python 节点中实际收到了参数，应在真实工具边界记录参数，再通过显式 resolver
交给适配器。不要从工具结果或最终答案反推参数：

```python
observed_inputs = []

def run_search(query):
    observed_inputs.append(query)
    return real_search_tool.invoke(query)

def resolve_tool_input(_event, ordinal):
    return observed_inputs[ordinal - 1]

trace = trace_from_langgraph_events(
    events,
    final_output,
    request,
    run_id="research-123",
    tool_input_resolver=resolve_tool_input,
    claims_extractor=extract_claims_from_actual_output,
)
```

`ordinal` 从 1 开始，只按 `on_tool_start` 计数。resolver 返回的值会按同一套
规则转换：对象保留为工具参数，字符串等标量会变成
`{"input": "..."}`。如果没有可靠的运行时采集，就保留空对象并把“参数未暴露”
作为接入限制记录下来；适配器不会猜测业务参数。

### 离线运行三个真实示例

```bash
python examples/pydantic_ai_agent_example.py
python examples/openai_agents_agent_example.py
python examples/langgraph_agent_example.py

agent-regression validate --trace work/pydantic-ai.trace.json
agent-regression validate --trace work/openai-agents.trace.json
agent-regression validate --trace work/langgraph.trace.json
```

示例使用真实框架运行时、确定性的本地模型和固定工具，不需要模型 API Key。
三个 Trace 都描述同一个“查询订单 123”场景，因此还能直接跨框架比较：

```bash
agent-regression compare \
  --baseline work/pydantic-ai.trace.json \
  --candidate work/openai-agents.trace.json
```

这可以验证迁移 Agent 框架后，工具调用和业务结果是否保持一致。PR 中应运行确定性
测试；真实供应商模型更适合定时运行，并使用 `StabilityPolicy` 判断多次采样的稳定性，
而不是要求自然语言逐字相同。

还可以运行项目内置的参数回归反例。用户请求仍是订单 123，但 Agent 错误地调用
订单 456；`compare` 应返回退出码 1：

```bash
AGENT_TOOL_ORDER_ID=456 \
AGENT_TRACE_OUT=work/langgraph-parameter-regression.trace.json \
python examples/langgraph_agent_example.py

agent-regression compare \
  --baseline work/pydantic-ai.trace.json \
  --candidate work/langgraph-parameter-regression.trace.json
```

---

## English

Agent Regression Kit converts completed runs from PydanticAI, OpenAI Agents SDK
and LangGraph into the same validated `AgentTrace`. The core package retains
zero mandatory framework dependencies.

## Install

Current framework releases require Python 3.10 or newer.

```bash
pip install 'agent-regression-kit[frameworks]'
```

Install one integration only with `[pydantic-ai]`, `[openai-agents]` or
`[langgraph]`.

## Convert a completed run

```python
from agent_regression import trace_from_pydantic_ai_result

result = agent.run_sync("Look up order 123")
trace = trace_from_pydantic_ai_result(
    result,
    "Look up order 123",
    run_id="order-123",
    identity={"name": "order-agent", "version": "1.0.0"},
    claims_extractor=lambda output: {"order_status": "paid"},
)
```

Use `trace_from_openai_agents_result(result, ...)` for an OpenAI Agents SDK
`RunResult`, and `trace_from_langgraph_result(state, ...)` for a LangGraph state
containing `messages`. When a graph hides tool execution inside a Python node,
collect the LangGraph v2 lifecycle dictionaries and use
`trace_from_langgraph_events(events, final_output, ...)` instead.

The adapter reads framework-owned call IDs, tool names, arguments, tool outputs
and final output. `claims_extractor` remains application-owned because only the
application knows which business facts must be regression-tested.

If `on_tool_start.data.input` is empty because a tool is called inside an ordinary
Python node, capture the value at the actual tool boundary and pass an explicit
`tool_input_resolver(event, ordinal)`. The resolver is called for each tool start;
objects remain objects and scalar inputs become `{"input": value}`. Do not infer
arguments from tool output or final prose.

## Runnable offline examples

```bash
python examples/pydantic_ai_agent_example.py
python examples/openai_agents_agent_example.py
python examples/langgraph_agent_example.py
```

All examples use the real framework runtime with a deterministic local model
and fixture tool. They require no model API key and write validated traces under
`work/`. The framework compatibility workflow executes them on related pull
requests.

The workflow also runs a negative LangGraph case: the request still names order
123 while the Agent calls the tool with order 456. The comparison must exit with
status 1, proving that the real-runtime integration blocks a parameter regression
instead of merely accepting and replaying traces.

Keep deterministic framework checks in pull requests. Run real provider models
on a separate schedule and apply `StabilityPolicy` instead of requiring
byte-identical natural-language output.
