# Agent Regression Kit

[![CI](https://github.com/ANTAO94/agent-regression-kit/actions/workflows/regression.yml/badge.svg)](https://github.com/ANTAO94/agent-regression-kit/actions/workflows/regression.yml)
[![Release](https://img.shields.io/github/v/release/ANTAO94/agent-regression-kit)](https://github.com/ANTAO94/agent-regression-kit/releases)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.9-blue)](setup.cfg)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Languages / 语言: [English](#english) · [简体中文](#简体中文)**

## English

**Regression tests for AI Agents: catch wrong tools, changed arguments, skipped steps, and incorrect business conclusions after changing a prompt, model, tool, or code.**

[中文](#简体中文) · [5-minute quick start](#5-minute-quick-start) · [Connect your Agent](#connect-your-agent) · [CI](#run-in-ci) · [English-only README](README.en.md) · [User manual](docs/user-manual.en.md)

Python ≥ 3.9 · Prepared patch `v4.38.1` (not yet tagged) · Latest published release `v4.38.0` · No required third-party core runtime dependencies

> Release status: the `v4.38.1` source contains the HelpPilot evidence and generated CI fixes. The tag/package is pending release; `v4.38.0` does not contain these fixes. See the [HelpPilot case study](docs/helppilot-case-study.md) and [patch acceptance record](docs/v4.38.1-acceptance.md).

### English contents

- [Why this exists](#why-this-exists)
- [How it works and key terms](#how-it-works)
- [5-minute quick start](#5-minute-quick-start)
- [Connect your Agent](#connect-your-agent)
- [Configure business rules and noise filters](#configure-business-rules-and-noise-filters)
- [Run in CI](#run-in-ci)
- [Source capabilities and validation evidence](#current-source-capabilities)
- [Boundaries and documentation](#what-it-does-not-solve)

### Why this exists

An Agent can produce a plausible final answer while its execution has regressed. A prompt change might call the wrong tool, send `order_id="132"` instead of `"123"`, repeat a refund, skip a required step, or read “not shipped” and answer “shipped.”

Agent Regression Kit records a real run as a structured **Trace**. It compares the new run with a reviewed **Baseline** and explicit business **Contract**, reports concrete differences, and returns an exit code that can block CI.

| Same request: look up order 123 | Tool behavior | Final conclusion | Result |
| --- | --- | --- | --- |
| Reviewed version | `get_order(order_id="123")` | Not shipped | Save as Baseline |
| Correct changed version | Same tool and order | Not shipped | Pass |
| Argument regression | `get_order(order_id="132")` | Another order's status | Block |
| Result misread | Correct tool and result | Incorrectly says “shipped” | Block |

An evaluation platform measures overall quality across datasets and cases. This kit checks what a particular change did to recorded behavior. They can work together: the platform handles batch quality metrics; this kit provides behavioral evidence, precise differences, and a CI gate.

### How it works

1. Run the reviewed Agent and commit its approved Trace as a Baseline.
2. Run the changed Agent and record a fresh Candidate Trace.
3. Apply a Contract and compare the two Traces. CI continues on a pass and stops on a blocking regression.

| Term | Meaning | Typical file |
| --- | --- | --- |
| Trace | One run's request, tool calls, arguments, results, final answer, and structured conclusions | `*.trace.json` |
| Baseline | A reviewed Trace committed to Git | `baselines/*.trace.json` |
| Candidate | A fresh Trace from the current implementation | `work/*.trace.json` |
| Contract | Required or forbidden tools, assertions, path, and side-effect rules | `.agent-regression/config.json` |
| Claims | Structured business facts extracted from the Agent's **actual output** | `final_answer.claims` |

> The kit cannot infer your correct business answer. Review each Baseline and derive claims from actual output; do not fill in expected answers as claims.

### 5-minute quick start

This starter example is offline and needs no model API key. Commands target macOS, Linux, and Windows WSL.
The install command below is for after the `v4.38.1` tag is published. Before
then, install from this checkout with `python -m pip install .`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git@v4.38.1"
agent-regression --version
mkdir agent-regression-demo
cd agent-regression-demo
agent-regression init
```

The published `v4.38.0` package lacks the fixes. `init` creates an offline Agent, fixed tool results, a starter Baseline, a strict Contract, a CI example, and integration notes. Its Baseline demonstrates the template; it is not approval of your business behavior.

Run the passing case:

```bash
python scripts/record_agent.py --variant normal --out work/my-agent.trace.json
agent-regression check --config .agent-regression/config.json
agent-regression compare --config .agent-regression/config.json
```

Expect `passed: true` and exit code **0**. Then prove the gate can fail:

```bash
python scripts/record_agent.py --variant wrong-resource --out work/my-agent.trace.json
agent-regression compare --config .agent-regression/config.json
```

Expect `passed: false` and exit code **1**: the framework detected a regression. The report identifies changed resources, missing calls, arguments, or business conclusions. Other negative variants are `skip-tool` and `misread-result`. Run `agent-regression ui` to inspect Traces and reports in a read-only local Viewer; the CLI decides the result.

### Connect your Agent

A real integration must record the tool name, actual arguments and returned result at the execution boundary; capture the Agent's actual final answer; and extract important business facts into claims.

| Your Agent | Entry point |
| --- | --- |
| PydanticAI, OpenAI Agents SDK, LangGraph | [Framework converters](docs/framework-integrations.md) |
| Custom Python Agent | [Callback example](examples/framework_callback_example.py) |
| Existing tool start/end events | [Event ingestion example](examples/langchain_core_event_example.py) |
| MCP tool or server | [MCP example](examples/mcp_record_example.py) |
| Sync/async Adapter scaffold | `agent-regression adapter-init --name my-agent --mode both` |

The integration calls your Agent in `invoke_framework(request, context)`, routes real tool execution through `context.call_tool(...)`, and saves the final answer and extracted facts through `context.final_answer(text, claims)`.

Inspect the first Trace before accepting it:

```bash
agent-regression baseline accept \
  --trace work/my-agent.trace.json \
  --out baselines/my-agent.trace.json
```

Future runs should regenerate the Candidate only. **Do not overwrite the Baseline automatically in CI.** The [independent LangGraph pilot](docs/p1-langgraph-agent-stack-validation.md) and [HelpPilot case study](docs/helppilot-case-study.md) show deterministic external-project integrations. They do not establish upstream adoption or online-model quality.

### Configure business rules and noise filters

The Baseline stores reference behavior; the config stores decision rules. This example allows wording changes while checking tools, arguments, and business conclusions:

```json
{
  "baseline": "baselines/my-agent.trace.json",
  "candidate": "work/my-agent.trace.json",
  "report": "work/reports/compare.json",
  "final_answer_mode": "claims-only",
  "contract": {
    "required_claims": ["final_answer.claims.order_status"],
    "assertions": [
      {"path": "final_answer.claims.order_status", "equals": "not_shipped"}
    ],
    "must_call": [
      {"tool": "get_order", "arguments": {"order_id": "123"}}
    ],
    "must_not_call": ["cancel_order", "refund"],
    "ignore_paths": ["tool_results[*].result.request_id"]
  }
}
```

```bash
agent-regression check --config .agent-regression/config.json
agent-regression compare --config .agent-regression/config.json
```

Use `ignore_paths` or normalizers for request IDs and timestamps; `must_call`, `must_not_call`, and `tool_allowlist` for tool boundaries; `tool_limits` and `max_steps` for loops; `path_rules` and `state_equivalence` for safe route variation; `relations` for cross-step arguments; and world-state snapshots plus `side_effects` for state changes. Pair each relaxed rule with a negative case: ignoring a request ID must not allow a wrong order ID. See the [configuration manual](docs/user-manual.en.md).

For batches with different legitimate outcomes, `case_contracts` selects assertions by relative Trace path, such as `orders/shipped.trace.json`. Cases without an override use the default Contract; unsafe paths, missing Traces, and invalid Contracts fail. See the [batch-case guide](docs/usage-guide.en.md#6-multiple-cases-and-ci).

### Run in CI

Commit the recording script, reviewed Baseline, and Contract. CI generates only the Candidate:

```text
scripts/record_agent.py                 runs the Agent and writes a Candidate
baselines/my-agent.trace.json           reviewed Baseline committed to Git
.agent-regression/config.json           Contract and comparison policy
```

The CI install below also requires the `v4.38.1` tag to have been published.

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
      - name: Install
        run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git@v4.38.1"
      - name: Record candidate
        run: python scripts/record_agent.py --out work/my-agent.trace.json
      - name: Compare
        run: agent-regression compare --config .agent-regression/config.json
      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: agent-regression-report
          path: work/reports/
          if-no-files-found: error
```

Exit codes are **0 = pass, 1 = regression, 2 = invalid input, configuration, or execution error.** Keep the comparison step blocking; do not add `|| true` or `continue-on-error`.

### Current source capabilities

The source includes structured Traces, deterministic Contracts, tool and argument checks, call counts and paths, cross-step relations, final-state and side-effect checks, synchronous/asynchronous/concurrent/multi-turn runs, MCP stdio and Streamable HTTP recording, framework converters, JSON/Markdown/JUnit reports, a local Viewer, redaction, history, batch scenarios, and coverage/study tools.

### Validation status

The current source is suitable for local development and team CI pilots. The main CI matrix covers Python 3.9, 3.11, and 3.13; the 2026-09-23 local source run recorded **317 passing tests** on Python 3.9.

That review found and fixed HelpPilot claims taken from mutation flags, dropped actions, missing retrieval bodies, and generated CI tag references. The fixes are in the prepared `v4.38.1` source, not the published `v4.38.0` artifact. Earlier green CI does not rule out those false negatives. See the [patch acceptance record](docs/v4.38.1-acceptance.md) and [architecture/value review](docs/architecture-value-review.zh-CN.md).

| Evidence | What it verifies | What it does not prove |
| --- | --- | --- |
| [Independent consumer repository](docs/consumer-pilot.md) | Released wheel, public API, CLI, and three regression gates run outside this checkout | Zero-code compatibility with every Agent |
| [Independent LangGraph pilot](docs/p1-langgraph-agent-stack-validation.md) | External graph events, pinned evidence, and four negative cases | Upstream adoption or online-model quality |
| [HelpPilot case study](docs/helppilot-case-study.md) | External graph, SQLite tools, RAG, human approval, and business-shaped regressions | Production quality or real-money safety |
| [DeepSeek live run](docs/deepseek-live.md) | Real-model order lookup and two-tool dependency | Reliability across every model or domain |
| [τ²-bench](docs/tau2-independent-validation.md) | Rule behavior and error evidence on pinned public trajectories | Generalization to unseen data |
| AgentDojo acceptance matrix | Contracts, hashes, and repeatability on pinned public security trajectories | A complete security rate |

These are pinned, maintainer-run pilots, not evidence of sustained independent adoption or production reliability. See the [iteration plan](docs/product-iteration-plan.zh-CN.md) and [limitations](docs/limitations.md).

### What it does not solve

The kit does not automatically decide whether arbitrary prose is factually true. It is not a production Tool Gateway, authorization system, tenant-isolation layer, DLP product, or model sandbox. It checks recorded evidence and explicit rules; hidden side effects need project-owned state snapshots, and real writes need isolated environments.

### Documentation

| Goal | Document |
| --- | --- |
| Full onboarding and configuration | [User manual](docs/user-manual.en.md) |
| Architecture and core boundaries | [Technical design](docs/technical-design.en.md) |
| Integrate Agent frameworks | [Framework integrations](docs/framework-integrations.md) |
| Configure safe path variation and final state | [State equivalence](docs/state-equivalence.md) · [Path variation example](examples/path-variation/README.md) |
| Troubleshoot installation, configuration, and exit codes | [FAQ](docs/usage-guide.en.md) |
| Upgrade an older version | [Upgrade guide](UPGRADING.md) · [Changelog](CHANGELOG.md) |
| Review evidence and the next iteration | [Maturity evidence](docs/maturity-roadmap.md) · [Iteration plan](docs/product-iteration-plan.zh-CN.md) |
| Security and contribution | [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) |

### Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m unittest discover -s tests -v
```

License: [MIT](LICENSE).

---

## 简体中文

**给 AI Agent 加回归测试：在 Prompt、模型、工具或代码变化后，发现错误工具、错误参数、漏步骤和错误业务结论。**

[English on this page](#english) · [5 分钟上手](#5-分钟跑通) · [接入自己的-agent](#接入自己的-agent) · [CI](#放进-ci) · [中文手册](docs/user-manual.zh-CN.md) · [技术设计](docs/technical-design.zh-CN.md)

Python ≥ 3.9 · 待发布补丁 `v4.38.1`（尚未打 tag）· 当前已发布 `v4.38.0` · 核心无必需第三方运行时依赖

> 发布状态：`v4.38.1` 源码包含 HelpPilot 证据采集和初始化 CI 修复，但 tag/发布包仍待发布；`v4.38.0` 发布包不包含这些修复。见 [HelpPilot 案例](docs/helppilot-case-study.md)和[补丁验收记录](docs/v4.38.1-acceptance.md)。

## 目录

- [为什么需要它](#为什么需要它)
- [工作方式](#工作方式)
- [5 分钟跑通](#5-分钟跑通)
- [接入自己的 Agent](#接入自己的-agent)
- [配置业务规则与噪音过滤](#配置业务规则与噪音过滤)
- [放进 CI](#放进-ci)
- [当前源码能力与验证状态](#当前源码能力)
- [边界与文档导航](#不解决什么)

## 为什么需要它

Agent 的问题往往不在最后一句话，而在中间过程。修改一个 Prompt 后，回答看起来仍然合理，但 Agent 可能已经：

- 调用了错误工具，或者漏掉必要步骤；
- 把 `order_id="123"` 传成 `132`；
- 重复执行退款等有副作用的操作；
- 正确拿到“未发货”，却回答成“已发货”；
- 走了一条结果相同、但风险完全不同的工具路径。

Agent Regression Kit 将一次真实运行保存为结构化 **Trace**，再把新运行与审核过的 **Baseline** 和业务 **Contract** 比较。差异会进入报告，并通过退出码直接阻断 CI。

| 同一个请求：查询订单 123 | 工具行为 | 最终结论 | 结果 |
| --- | --- | --- | --- |
| 审核过的版本 | `get_order(order_id="123")` | 未发货 | 保存为 Baseline |
| 修改后的正常版本 | 同一个工具和订单 | 未发货 | 通过 |
| 参数回归 | `get_order(order_id="132")` | 另一个订单的状态 | 阻断 |
| 结果误读 | 参数和工具结果都正确 | 错误地回答“已发货” | 阻断 |

### 它和评测平台有什么不同

| | 评测平台 | Agent Regression Kit |
| --- | --- | --- |
| 回答的问题 | Agent 整体表现有多好 | 这次改动具体弄坏了什么 |
| 典型输出 | 得分、准确率、通过率 | 工具、参数、结果、状态或 claims 的结构化差异 |
| 运行时机 | 定期评测、模型选型、版本验收 | 每次 PR、Prompt 或工具修改 |
| 核心对象 | Dataset、Case、Scorer | Baseline、Candidate Trace、Contract |

两者可以组合：评测平台负责数据集、批量运行和质量指标，本项目负责行为证据、差异定位和 CI 回归门禁。

## 工作方式

```mermaid
flowchart TD
    A[运行审核过的 Agent] -->|记录真实行为| B[Baseline Trace]
    C[运行修改后的 Agent] -->|记录真实行为| D[Candidate Trace]
    B --> E{Compare + Contract}
    D --> E
    F[业务规则与噪音过滤] --> E
    E -->|通过| G[CI 继续]
    E -->|发现回归| H[报告具体差异并阻断]
```

一句话：保留正确版本的运行证据，每次改动后重新运行，比较器负责解释变化并决定 CI 是否放行。

| 名词 | 含义 | 常见文件 |
| --- | --- | --- |
| Trace | 一次 Agent 运行中的请求、工具调用、参数、结果、最终回答和结构化结论 | `*.trace.json` |
| Baseline | 由人审核正确并提交到 Git 的参考 Trace | `baselines/*.trace.json` |
| Candidate | 当前代码重新运行得到的 Trace | `work/*.trace.json` |
| Contract | 必须调用/禁止调用的工具、业务断言、路径和副作用规则 | `.agent-regression/config.json` |
| Claims | 从 Agent **实际输出**提取的结构化业务事实 | `final_answer.claims` |

> 框架不会自动知道业务正确答案。Baseline 必须审核；claims 必须来自实际输出，不能预填“正确答案”。

## 5 分钟跑通

以下示例完全离线，不需要模型 API Key。命令适用于 macOS、Linux 和 Windows WSL。
以下 `v4.38.1` 安装命令须等 tag 发布后使用；发布前可在本仓库目录执行 `python -m pip install .`。

### 1. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git@v4.38.1"
agent-regression --version
```

已发布的 `v4.38.0` 不包含本次修复。

### 2. 生成可运行项目

```bash
mkdir agent-regression-demo
cd agent-regression-demo
agent-regression init
```

`init` 会生成一个离线 Agent、固定工具结果、starter baseline、严格 Contract、CI 示例和接入说明。这个 baseline 只适用于模板场景，不代表你的业务已经审核通过。

### 3. 运行正常场景

```bash
python scripts/record_agent.py \
  --variant normal \
  --out work/my-agent.trace.json
agent-regression check --config .agent-regression/config.json
agent-regression compare --config .agent-regression/config.json
```

预期 `passed: true`，退出码为 **0**。

### 4. 确认门禁真的会失败

```bash
python scripts/record_agent.py \
  --variant wrong-resource \
  --out work/my-agent.trace.json
agent-regression compare --config .agent-regression/config.json
```

预期 `passed: false`，退出码为 **1**。这表示框架成功发现回归，不是命令执行失败。报告会指出错误资源、缺失调用、参数变化或业务结论差异。

其他内置负向变体：`skip-tool` 和 `misread-result`。

### 5. 查看报告

```bash
agent-regression ui
```

打开终端给出的本地地址，可查看 Trace、比较报告和配置。Viewer 是只读本地页面；比较结果仍以 Python CLI 为准。

## 接入自己的 Agent

模板只是演示。真实接入需要完成三件事：

1. 在工具执行边界记录工具名、真实参数和真实返回值；
2. 记录 Agent 实际产生的最终回答；
3. 将需要稳定检查的业务结论提取成结构化 claims。

| 你的 Agent | 推荐入口 |
| --- | --- |
| PydanticAI、OpenAI Agents SDK、LangGraph | [框架转换器](docs/framework-integrations.md) |
| 自己实现的 Python Agent | [Callback 示例](examples/framework_callback_example.py) |
| 已有工具开始/结束事件 | [事件接入示例](examples/langchain_core_event_example.py) |
| MCP 工具或 Server | [MCP 示例](examples/mcp_record_example.py) |
| 需要同步/异步 Adapter 模板 | `agent-regression adapter-init --name my-agent --mode both` |

最小接入代码中，各部分职责如下：

| 代码位置 | 责任 |
| --- | --- |
| `invoke_framework(request, context)` | 调用真实 Agent |
| `context.call_tool(...)` | 让真实工具执行经过记录边界 |
| `context.final_answer(text, claims)` | 保存真实回答及从中提取的业务事实 |

首次运行后，检查 Trace 中的参数、结果和 claims，确认正确再接受基线：

```bash
agent-regression baseline accept \
  --trace work/my-agent.trace.json \
  --out baselines/my-agent.trace.json
```

之后只重新生成 candidate。**不要在 CI 中自动覆盖 baseline。**

仓库还提供一条固定 commit 的[独立 LangGraph 项目接入验证](docs/p1-langgraph-agent-stack-validation.md)：不修改候选项目业务图，从真实事件流记录 Agent 实际消费的工具证据，并验证参数回归、漏调用、结果误读和证据正文损坏。它是确定性技术预演，不代表上游采用或在线模型质量。

待发布的 `v4.38.1` [HelpPilot 案例](docs/helppilot-case-study.md)在公开 LangGraph 客服项目中跑通“查询订单 → 查询物流 → 检查退款政策 → 创建退款草稿 → 人工审批 → 执行退款 → 回复引用”，并验证错误资源、漏工具、结果误读、额外写操作和检索正文变化。固定 commit、seed/demo 数据和确定性替身使其可复现；这不代表上游采用或生产质量。[历史 v4.38.0 验收记录](docs/v4.38.0-acceptance.md)保留了原发布包的证据边界。

## 配置业务规则与噪音过滤

Baseline 保存参考行为，config 保存判断规则。下面的配置允许回答措辞变化，但仍检查工具、参数和业务结论：

```json
{
  "baseline": "baselines/my-agent.trace.json",
  "candidate": "work/my-agent.trace.json",
  "report": "work/reports/compare.json",
  "final_answer_mode": "claims-only",
  "contract": {
    "required_claims": ["final_answer.claims.order_status"],
    "assertions": [
      {
        "path": "final_answer.claims.order_status",
        "equals": "not_shipped"
      }
    ],
    "must_call": [
      {
        "tool": "get_order",
        "arguments": {"order_id": "123"}
      }
    ],
    "must_not_call": ["cancel_order", "refund"],
    "ignore_paths": ["tool_results[*].result.request_id"]
  }
}
```

```bash
agent-regression check --config .agent-regression/config.json
agent-regression compare --config .agent-regression/config.json
```

常用规则：

| 诉求 | 配置能力 |
| --- | --- |
| 忽略 request ID、时间戳等噪音 | `ignore_paths`、normalizers |
| 必须/禁止调用某工具 | `must_call`、`must_not_call`、`tool_allowlist` |
| 限制次数、防止循环 | `tool_limits`、`max_steps` |
| 允许多条安全路径 | `path_rules`、`state_equivalence` |
| 检查跨步骤参数 | `relations` |
| 检查执行前后状态和副作用 | world-state snapshots、`side_effects` |
| 允许措辞变化但保留业务判断 | `claims-only` + required claims + assertions |

任何放宽规则都应配一个邻近负向用例：例如忽略 `request_id` 后，错误 `order_id` 仍必须失败。完整字段见[配置手册](docs/user-manual.zh-CN.md)。

如果你有多个业务用例，而且每个用例的合法结果不同，可以在批量配置里使用
`case_contracts`，按 `orders/shipped.trace.json` 这样的相对 Trace 路径配置单独的断言。
没有单独配置的用例使用默认 Contract；路径不安全、Trace 缺失或 Contract 无效都会失败。
完整示例见[批量用例说明](docs/usage-guide.zh-CN.md#6-多用例和-ci)。

## 放进 CI

项目中需要提交三类文件：

```text
scripts/record_agent.py                 每次运行真实 Agent，生成 candidate
baselines/my-agent.trace.json           人工审核并提交的 baseline
.agent-regression/config.json           Contract 和比较策略
```

下面的 CI 安装命令同样需要等 `v4.38.1` tag 发布。

最小 GitHub Actions：

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
      - name: Install
        run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git@v4.38.1"
      - name: Record candidate
        run: python scripts/record_agent.py --out work/my-agent.trace.json
      - name: Compare
        run: agent-regression compare --config .agent-regression/config.json
      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: agent-regression-report
          path: work/reports/
          if-no-files-found: error
```

退出码约定：**0 = 通过，1 = 发现回归，2 = 输入、配置或运行错误。** 不要给比较命令添加 `|| true` 或 `continue-on-error`。

## 当前源码能力

- 结构化 Trace、baseline/candidate 比较和确定性 Contract；
- 工具参数、结果、调用次数、调用路径和未授权工具检查；
- 跨步骤关系、最终状态、副作用和状态隔离；
- 同步、异步、并发、多轮 Session 和稳定性重复运行；
- MCP stdio / Streamable HTTP 记录与协议边界；
- PydanticAI、OpenAI Agents SDK、LangGraph 和 LangChain Core 接入；
- JSON、Markdown、JUnit、GitHub Job Summary 和本地 Viewer；
- 脱敏、历史趋势、批量场景、覆盖率和可审计 study/benchmark。

## 已验证到什么程度

当前源码适合本地开发和团队 CI 试点。主分支测试矩阵覆盖 Python 3.9、3.11 和 3.13；2026-09-23 的本地源码运行在 Python 3.9 上有 **317 个测试通过**。

2026-09-22 复审发现并在 main 修复 HelpPilot claims、动作过滤和检索正文采集缺口，以及初始化 CI 的 tag 引用。
修复已在待发布的 v4.38.1 源码中，尚未进入已发布的 v4.38.0 包。原有 CI 结果不能证明不存在这些漏报，详见
[补丁验收记录](docs/v4.38.1-acceptance.md)和
[架构与开源价值复审](docs/architecture-value-review.zh-CN.md)。

| 证据 | 已验证 | 不能说明 |
| --- | --- | --- |
| [独立消费仓库](docs/consumer-pilot.md) | 发布 wheel、公开 API、CLI 和三类回归门禁可在独立仓库运行 | 不代表无代码兼容所有 Agent |
| [独立 LangGraph 技术预演](docs/p1-langgraph-agent-stack-validation.md) | 真实外部 graph 的事件接入、固定资料和四类负向场景 | 不代表上游采用或在线模型质量 |
| [HelpPilot 业务案例](docs/helppilot-case-study.md) | 真实外部 graph、SQLite 工具、RAG、人工审批和业务形状回归 | 不代表生产质量、上游采用或真实资金安全 |
| [DeepSeek 实测](docs/deepseek-live.md) | 真实模型的订单查询和两步工具依赖 | 不代表所有模型或所有业务可靠 |
| [τ²-bench](docs/tau2-independent-validation.md) | 固定公开轨迹上的规则验证和误报/漏报记录 | 不代表未见数据泛化 |
| AgentDojo 验收矩阵 | 固定公开安全轨迹的 Contract、哈希和重复性 | 不代表完整安全率 |

这些是固定版本、维护者执行的预演，尚不能证明独立项目持续采用或生产可靠性。详见[后续迭代方案](docs/product-iteration-plan.zh-CN.md)和[能力限制](docs/limitations.md)。

## 不解决什么

本项目不会自动判断任意自然语言是否真实，也不是生产 Tool Gateway、权限系统、租户隔离、DLP 或模型安全沙箱。它只能检查已经记录的证据和明确配置的规则；隐藏副作用需要项目提供状态快照，真实写操作需要隔离环境。

## 文档导航

| 目标 | 文档 |
| --- | --- |
| 从零接入和全部配置 | [中文使用手册](docs/user-manual.zh-CN.md) |
| 理解架构和核心边界 | [技术设计](docs/technical-design.zh-CN.md) |
| 接入主流 Agent 框架 | [框架集成](docs/framework-integrations.md) |
| 配置合法路径和最终状态 | [状态等价](docs/state-equivalence.md) · [路径变化示例](examples/path-variation/README.md) |
| 排查安装、配置和退出码 | [常见问题](docs/usage-guide.zh-CN.md#7-常见问题) |
| 升级旧版本 | [升级说明](UPGRADING.md) · [Changelog](CHANGELOG.md) |
| 查看真实验证和下一阶段 | [证据清单](docs/maturity-roadmap.md) · [迭代方案](docs/product-iteration-plan.zh-CN.md) |
| 安全与贡献 | [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) |

## 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m unittest discover -s tests -v
```

## 许可证

[MIT](LICENSE)
