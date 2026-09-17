# Agent Regression Kit

[中文说明](#中文说明) | [English](#english)

## 中文说明

Agent Regression Kit 是一个面向 AI Agent 的、与框架无关的回归测试工具包。它把一次 Agent 运行记录成版本化、脱敏的 JSON Trace，再将候选版本与经过审核的基线进行结构化比较。

当你修改 Prompt、模型、工具 Schema 或 Agent Adapter 时，项目可以在 CI 中明确告诉你：工具名称、参数、工具结果、最终答案或交互流程是否发生了回归，而不是依赖人工观察。

### 核心流程

```text
Agent / MCP Server
        │
        ▼
  录制 Trace ───────► 审核后的 baseline
        │                      │
        └── candidate Trace ───┘
                               │
                               ▼
                    compare + JSON/JUnit 报告
                               │
                               ▼
                         CI 通过 / 阻断回归
```

### 当前能力

- AgentTrace v0.1：事件序列、工具调用/结果配对、最终答案和结构化 claims。
- MCP stdio 与 Streamable HTTP：JSON/SSE、会话、分页、取消、重连、进度和并发调用。
- 服务端请求处理：sampling、elicitation，以及 HTTP POST-SSE 流中的双向请求响应。
- 任务化工具调用：任务创建、状态轮询、结果获取和取消。
- 严格结构化对比：支持 JSON 报告、JUnit 报告和 CI exit code。
- 默认脱敏：避免 API Key 等敏感字段进入 Trace。

### 验证结果

以下结果于 2026-09-17 在本地运行：

| 检查项 | 结果 |
| --- | --- |
| Python 单元与集成测试 | **51 项通过，0 项失败** |
| 源码编译 | `compileall` 通过 |
| Python 单元与集成测试 | **51 项通过，0 项失败** |
| Wheel 构建 | `agent_regression_kit-1.3.0-py3-none-any.whl` 构建成功 |
| 官方 Everything Server / stdio | 通过；13 tools、7 resources、4 prompts |
| 官方 Everything Server / Streamable HTTP | 通过；发现结果一致 |
| MCP 双向交互 | 通过；sampling、elicitation、任务创建/轮询/结果获取 |

核心测试可以这样复现：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

### 快速开始

```bash
python -m venv .venv
.venv/bin/pip install -e .

# 为自己的项目生成 Agent、baseline 和 GitHub Actions 模板
agent-regression init

# 生成一份 candidate Trace（先用模板验证，再替换成自己的 Agent）
python scripts/record_agent.py --out work/my-agent.trace.json

agent-regression record \
  --scenario examples/order-123/baseline.scenario.json \
  --out work/baseline.trace.json

agent-regression record \
  --scenario examples/order-123/candidate-regression.scenario.json \
  --out work/candidate.trace.json

agent-regression compare \
  --baseline work/baseline.trace.json \
  --candidate work/candidate.trace.json \
  --out work/diff.json
```

候选版本发生回归时，`compare` 返回退出码 `1`；匹配时返回 `0`；输入或 Trace 无效时返回 `2`。

### 项目边界

它不是通用 Agent 框架、评分平台、LLM Judge 或 Dashboard。仓库里的订单 Agent 和 MCP Server 是确定性的测试 Fixture，用来证明接入边界可以在没有模型和网络依赖的情况下运行。

### 别人如何接入自己的 Agent

最重要的一点：这个项目不会替你调用 LLM，也不会自动接管一个现有 Agent。你需要写一个很薄的 `AgentAdapter`，把 Agent 的工具调用转发给 `context.call_tool`，把最终回答转发给 `context.final_answer`。之后，回归工具负责录制 Trace、保存 baseline、比较 candidate，并在 CI 中阻断变化。

下面是一个完整的最小接入例子。真实项目里，`MyOrderAgent.run` 内部可以换成你的 LangChain、Spring AI、OpenAI SDK 或自研 Agent 调用；关键是把工具调用和最终回答接到两个 `context` 方法上：

```python
# scripts/record_agent.py
import json
import sys
from pathlib import Path

from agent_regression import record_mcp_run


class MyOrderAgent:
    identity = {"name": "my-order-agent", "version": "1.0.0"}

    def run(self, request, context):
        order_id = str(request).rsplit(" ", 1)[-1]
        order = context.call_tool("get_order", {"order_id": order_id})
        status = order["status"]
        text = f"订单 {order_id} 的状态是 {status}。"
        context.final_answer(
            text,
            {"order_id": order_id, "order_status": status},
        )


trace = record_mcp_run(
    MyOrderAgent(),
    "查询订单 123",
    [sys.executable, "src/agent_regression/fixtures/mcp_stdio_server.py"],
    run_id="my-order-agent-123",
)
Path("work/my-order-agent.trace.json").parent.mkdir(parents=True, exist_ok=True)
Path("work/my-order-agent.trace.json").write_text(
    json.dumps(trace.to_dict(), ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
```

实际使用时通常是四步：

```bash
# 1. 第一次确认行为正确时，生成并审核 baseline
python scripts/record_agent.py
cp work/my-order-agent.trace.json baselines/my-order-agent.trace.json

# 2. 修改 Prompt、模型、工具或 Agent 代码后，再录一份 candidate
python scripts/record_agent.py

# 3. 比较两次运行
agent-regression compare \
  --baseline baselines/my-order-agent.trace.json \
  --candidate work/my-order-agent.trace.json \
  --format junit \
  --out outputs/my-order-agent.junit.xml

# 4. 在 CI 中使用同一个 compare 命令；退出码 1 就表示检测到阻断性回归
```

如果你的 MCP Server 是 Streamable HTTP，只需将 `record_mcp_run` 换成 `record_mcp_http_run` 并传入 `/mcp` 地址；如果你的 Agent 已经有自己的工具执行层，也可以直接使用通用的 `record_run`。仓库中的 `examples/rule_agent_mcp_example.py` 是可以直接运行的完整参考，`examples/order-123/` 则是 CLI 演示数据，不是用户必须采用的 Agent 格式。

### CI 集成

CI 中的职责很简单：你的项目负责运行 Agent 并生成 candidate Trace；Agent Regression Kit 负责和仓库里的 baseline 比较。baseline 应该在本地或专门的审核流程中更新，不能在每次 CI 运行时自动覆盖。

在你的项目中提交一份类似下面的 `.github/workflows/agent-regression.yml`：

```yaml
name: agent-regression

on:
  pull_request:

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # 从 GitHub 安装 Agent Regression Kit
      - name: Install regression kit
        run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git"

      # 这是你的脚本：启动真实 Agent，生成 work/candidate.trace.json
      - name: Record candidate trace
        run: python scripts/record_agent.py

      # 远程复用本项目提供的比较 Action
      - name: Compare with reviewed baseline
        uses: ANTAO94/agent-regression-kit/.github/actions/agent-regression@main
        with:
          baseline: baselines/my-agent.trace.json
          candidate: work/candidate.trace.json
          report: outputs/my-agent.junit.xml

      - name: Upload regression report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: agent-regression-report
          path: outputs/my-agent.junit.xml
```

运行规则：`compare` 返回 `0`，PR 通过；返回 `1`，说明发现阻断性回归，PR 失败；返回 `2`，说明输入、Trace 或运行环境有问题。GitHub 会把 JUnit 文件作为构建产物保存，便于查看具体差异。

详细 API、架构、限制和完整英文文档见后面的 [English](#english) 部分，以及 [`docs/`](docs/) 目录。

## English

Agent Regression Kit is a small, framework-neutral regression-testing layer for AI Agents. It turns an Agent run into versioned, redacted JSON evidence, then compares a candidate run with a reviewed baseline. A changed prompt, model, tool schema, or adapter should produce a visible diff in CI instead of a silent behavior change.

Current release line: **v1.3 development preview**. It supports deterministic local runs plus MCP stdio and Streamable HTTP capture, offline replay, structural comparison, baseline management, JSON/Markdown/JUnit reports, CI exit codes, GitHub job summaries, and one-command project scaffolding.

```text
Agent / MCP Server
        │
        ▼
  record a Trace  ──────►  reviewed baseline
        │                         │
        └──── candidate Trace ────┘
                                  │
                                  ▼
                       compare + JSON/JUnit report
                                  │
                                  ▼
                         CI pass / regression
```

The project is not a general scorer platform, Agent framework, LLM judge, or
dashboard. The included order Agent and MCP server are deterministic fixtures
that make the integration boundary runnable without model or network access.

## Current validation

The following results were run locally on 2026-09-17:

| Check | Result |
| --- | --- |
| Python unit and integration suite | **51 passed, 0 failed** |
| Source compilation | Passed with `compileall` |
| Wheel build | `agent_regression_kit-1.3.0-py3-none-any.whl` built successfully |
| Official Everything Server over stdio | Passed; protocol `2025-11-25`, 13 tools, 7 resources, 4 prompts |
| Official Everything Server over Streamable HTTP | Passed; same discovery counts |
| Bidirectional MCP exercise | Passed; sampling, elicitation, task creation, polling, and final task result |

Reproduce the core result:

```text
$ PYTHONPATH=src python3 -m unittest discover -s tests -q
----------------------------------------------------------------------
Ran 51 tests in 7.6s

OK
```

The official-server check is intentionally separate from the default offline
suite. Run it with the manual workflow in
[`.github/workflows/mcp-compatibility.yml`](.github/workflows/mcp-compatibility.yml)
or with the `mcp-smoke` command described below.

## AgentTrace v0.1

Every trace contains:

- `schema_version`, currently `0.1`;
- a stable `run_id` and an `agent` identity object;
- contiguous, one-based event `sequence` values;
- paired `tool_call` / `tool_result` events linked by `call_id`;
- exactly one terminal `final_answer`;
- optional run `metadata` and optional structured final-answer `claims`.

`claims` make result interpretation explicit enough for deterministic regression checks. The kit does not guess semantic facts from prose in v0.1.

The canonical machine-readable contract is `schema/agent-trace-v0.1.schema.json`. Runtime validation additionally enforces contiguous sequence values, valid call/result pairing, and exactly one terminal answer.

## Quick start

Python 3.9+ is the only runtime dependency.

```bash
python -m venv .venv
.venv/bin/pip install -e .

# Scaffold an integration project
agent-regression init

# Run the generated deterministic example
python scripts/record_agent.py --out work/my-agent.trace.json

agent-regression record \
  --scenario examples/order-123/baseline.scenario.json \
  --out work/baseline.trace.json

agent-regression record \
  --scenario examples/order-123/candidate-regression.scenario.json \
  --out work/candidate.trace.json

agent-regression replay --trace work/baseline.trace.json
agent-regression validate --trace work/baseline.trace.json

agent-regression compare \
  --baseline work/baseline.trace.json \
  --candidate work/candidate.trace.json \
  --out work/diff.json
```

The last command exits `1` because the candidate changes the tool name, changes `order_id` from the string `"123"` to the number `123`, contradicts the recorded result in its structured claim, and changes the final answer. A match exits `0`; invalid input or trace data exits `2`.

To run the automated tests without installing the package:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The default suite is deterministic and offline. It covers trace validation,
record/replay/compare, redaction, JSON/JUnit reports, MCP stdio and HTTP
transports, pagination, cancellation, reconnect, resumable SSE, progress,
concurrent calls, server-initiated requests, task helpers, and failure paths.

## How users integrate their own Agent

The package does not call an LLM or take control of an existing Agent. A user
provides a thin `AgentAdapter`: route tool calls through `context.call_tool`
and finish through `context.final_answer`. The package then records the run,
stores a reviewed baseline, compares a candidate, and returns a CI-friendly
exit code. The `record` and `mcp-record` CLI commands are deterministic fixture
demos; they are not automatic discovery of arbitrary user Agents.

Minimal adapter shape:

```python
from agent_regression import record_mcp_run


class MyAgent:
    identity = {"name": "my-agent", "version": "1.0.0"}

    def run(self, request, context):
        result = context.call_tool("get_order", {"order_id": "123"})
        context.final_answer(
            f"Order status: {result['status']}",
            {"order_status": result["status"]},
        )


trace = record_mcp_run(
    MyAgent(),
    "lookup order 123",
    ["node", "path/to/your-mcp-server.js", "stdio"],
    run_id="my-agent-123",
)
```

Write `trace.to_dict()` to a JSON file, keep the first reviewed file as the
baseline, generate a new candidate after each Agent change, and compare them:

```bash
agent-regression compare \
  --baseline baselines/my-agent.trace.json \
  --candidate work/my-agent.trace.json \
  --format junit \
  --out outputs/my-agent.junit.xml
```

For a Streamable HTTP MCP server, use `record_mcp_http_run` with its `/mcp`
URL. For an Agent that already owns tool execution, use the framework-neutral
`record_run` API. See the Chinese walkthrough above and
[`examples/rule_agent_mcp_example.py`](examples/rule_agent_mcp_example.py) for
a runnable reference.

## Public API

The same flow is available through `record_run`, `record_mcp_run`, `replay_trace`, and `compare_traces`. A real integration implements the small `AgentAdapter` protocol: expose an `identity`, execute one request, route tool calls through `RunContext.call_tool`, and finish through `RunContext.final_answer`.

This boundary keeps framework-specific hooks outside the trace, comparator, and report. See `docs/api.md` for the supported imports and `docs/architecture.md` for component and failure-flow diagrams.

### Rule-driven Agent example

`RuleBasedOrderAgentAdapter` is the smallest reference Agent that makes a real
decision from runtime data. It extracts an order ID from the request, chooses
`get_order`, calls the local MCP fixture, reads the returned status, and only
then creates its final text and structured claims. Its answer is not stored in
a scripted plan.

The example also includes two controlled defects: a parameter regression that
sends a numeric ID with the wrong type, and a result-misread variant that
incorrectly interprets `not_shipped` as `shipped`. Run the full record, replay,
and comparison flow offline:

```bash
python examples/rule_agent_mcp_example.py
python -m json.tool outputs/rule-agent-baseline.replay.json
python -m json.tool outputs/rule-agent-parameter-regression.diff.json
python -m json.tool outputs/rule-agent-result-misread.diff.json
```

This reference Agent is deterministic by design. It proves the integration
boundary without claiming to provide planning, model inference, memory, or a
general natural-language parser.

## Local MCP fixture and capture

The repository now includes a project-owned, deterministic MCP stdio fixture at `src/agent_regression/fixtures/mcp_stdio_server.py`. It is a narrow test double, not a complete MCP conformance server. It is pinned to the MCP `2025-11-25` lifecycle because this fixture intentionally exercises `initialize` followed by `notifications/initialized`; the newer `2026-07-28` revision removed that handshake.

The implemented protocol surface is:

- newline-delimited UTF-8 JSON-RPC 2.0 over a child process's stdin/stdout;
- `initialize` and `notifications/initialized`;
- `tools/list` and `tools/call`;
- one `get_order` tool with a normal result, an invalid-argument tool error, and a deterministic service-error input (`order_id: "500"`);
- JSON-RPC errors for unsupported methods and unknown tools.

Run the complete local capture example:

```bash
python examples/mcp_record_example.py
python -m json.tool outputs/mcp-order-123.trace.json >/dev/null
```

Or run the same fixture through the installed CLI and compare a candidate:

```bash
agent-regression mcp-record \
  --scenario examples/order-123/baseline.scenario.json \
  --out work/mcp-baseline.trace.json
agent-regression mcp-record \
  --scenario examples/order-123/candidate-regression.scenario.json \
  --out work/mcp-candidate.trace.json
agent-regression compare \
  --baseline work/mcp-baseline.trace.json \
  --candidate work/mcp-candidate.trace.json \
  --out outputs/mcp-order-123.diff.json
```

`record_mcp_run` starts the server, performs the handshake and tool discovery, records tool calls/results through the existing AgentTrace recorder, and stores a request/response transcript under `metadata.mcp`. `McpToolExecutor` prefers MCP `structuredContent`, falls back to `content`, and preserves `isError` in the trace.

### Streamable HTTP capture

The same recorder can connect to an MCP Streamable HTTP endpoint. It accepts
the immediate JSON response form and the server-sent-event response form,
preserves the `Mcp-Session-Id`, and stores the HTTP transcript in the same
`metadata.mcp` shape:

```bash
agent-regression mcp-http-record \
  --url http://127.0.0.1:8000/mcp \
  --scenario examples/order-123/baseline.scenario.json \
  --out work/http-baseline.trace.json
```

For a fully local smoke test, start the bundled HTTP fixture in another
terminal:

```bash
python -m agent_regression.fixtures.mcp_http_server --port 8765
agent-regression mcp-http-record \
  --url http://127.0.0.1:8765/mcp \
  --scenario examples/order-123/baseline.scenario.json \
  --out work/http-baseline.trace.json
```

The HTTP client is intentionally synchronous in v1.3. In addition to
request/response capture, `open_event_stream()` provides a bounded iterator for
the session's GET SSE stream; server notifications and requests are recorded in
the same transcript. A server-initiated request can be answered explicitly
with `client.respond(...)` or `stream.respond(...)`. Pagination helpers,
explicit cancellation, reconnect, resumable SSE streams, automatic request
dispatch callbacks, progress filtering, and bounded concurrent calls are
supported. The generic AgentTrace recorder remains sequential in v1.3.
For task-capable tools, pass task metadata such as
`task={"ttl": 60000, "pollInterval": 100}` to `call_tool`; poll the returned
task with `get_task` and fetch its final value with `get_task_result`. When an
HTTP POST response is an SSE stream, the client can dispatch in-band sampling
or elicitation requests through the configured callback before returning the
final tool response.

### Optional compatibility smoke test

`mcp-smoke` performs a non-mutating initialize and capability-discovery check.
It is suitable for a manual compatibility job or a scheduled workflow, but it
is intentionally not part of the default offline test suite:

```bash
agent-regression mcp-smoke \
  --server-command 'npx -y @modelcontextprotocol/server-everything'
```

The official Everything Server is a reference/test server that exercises tools,
resources, prompts, and additional MCP features. Its Streamable HTTP mode can
be checked by starting that server separately and passing its `/mcp` endpoint
with `--url`. The smoke command only discovers advertised primitives; it does
not invoke tools or mutate resources. The stdio client supports both newline
JSON-RPC and Content-Length framing for servers that require the latter.

For a local compatibility check after installing the package:

```bash
agent-regression mcp-smoke \
  --server-command 'npx -y @modelcontextprotocol/server-everything stdio' \
  --stdio-framing newline \
  --timeout 60 \
  --out outputs/official-everything-stdio.json
```

The command writes a machine-readable report with the negotiated protocol,
server identity, advertised capabilities, and discovery counts. It does not
claim full MCP conformance; the deeper sampling, elicitation, and task flow
is covered by the integration exercise used for the validation table above.

This fixture follows the official [MCP 2025-11-25 lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle), [schema reference](https://modelcontextprotocol.io/specification/2025-11-25/schema), and [stdio framing rules](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports). External compatibility validation is optional and is intentionally outside the default test suite.

## Comparison, baselines, and CI

Default comparison is strict: any detected difference fails. Reports categorize `tool_name`, `tool_arguments`, `tool_result`, `tool_error_state`, `result_interpretation`, `final_answer`, and `event_count`. Exact categories or paths can be allowed without hiding them:

```bash
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/candidate.trace.json \
  --allow-path final_answer.text
```

Baseline changes are explicit:

```bash
agent-regression baseline accept \
  --trace work/reviewed.trace.json \
  --out baselines/order-123.trace.json
agent-regression baseline show --baseline baselines/order-123.trace.json
```

Generate a JUnit report while preserving the comparison exit code:

```bash
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/candidate.trace.json \
  --format junit \
  --out outputs/junit.xml
```

`.github/workflows/regression.yml` is an offline CI example. The reusable
local action at `.github/actions/agent-regression` compares a candidate trace,
writes a JUnit report, and preserves the blocking exit code. Exit code `0`
means pass, `1` means a blocking regression, and `2` means invalid input or an
operational error.

For another GitHub repository, the integration has one important boundary:
your project runs the Agent and writes `work/candidate.trace.json`; this kit
compares it with a reviewed baseline committed at
`baselines/my-agent.trace.json`. Do not regenerate the baseline automatically
on every CI run. A minimal external workflow is:

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with:
    python-version: "3.11"
- name: Install Agent Regression Kit
  run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git"
- name: Record candidate trace
  run: python scripts/record_agent.py
- name: Compare with baseline
  uses: ANTAO94/agent-regression-kit/.github/actions/agent-regression@main
  with:
    baseline: baselines/my-agent.trace.json
    candidate: work/candidate.trace.json
    report: outputs/my-agent.junit.xml
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: agent-regression-report
    path: outputs/my-agent.junit.xml
```

The candidate-producing script is owned by the integrating project because
each Agent framework has a different execution API. The action then returns
`0` for a passing comparison, `1` for a blocking regression, and `2` for
invalid input or an operational error.

## Security and reproducibility

Common secret-bearing keys are recursively replaced with `[REDACTED]` before evidence is stored. Use repeatable `--secret-value` flags for secrets embedded in free-form text. Raw arguments still reach the selected tool executor, so only run trusted external MCP commands.

The MCP executor records timeout, attempt, retry count, and request ID on each tool result. It never retries automatically because the side effects of an arbitrary tool are unknown. The bundled fixture is isolated in a child process, performs no network access, and has deterministic results.

See `docs/limitations.md` for the complete trust boundary and intentionally unsupported protocol features. LLM judges, dashboards, latency/cost gates, and general release aggregation remain out of scope.

## Development

```bash
python -m unittest discover -s tests -v
python -m pip wheel --no-build-isolation .
```

The default suite is offline. Official MCP Everything Server checks are
optional compatibility validation and are not default dependencies. The next
natural extension points are authentication, more framework adapters, richer
non-deterministic scoring, and long-term trend reporting.
