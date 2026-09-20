# Agent Regression Kit 使用手册

[English](user-manual.en.md) · [技术方案](technical-design.zh-CN.md) · [首页](../README.md)

适用：v4.20.0。以下命令面向 macOS/Linux Bash 或 Zsh，默认在仓库根目录执行。核心包要求 Python ≥ 3.9；远端矩阵覆盖 3.9、3.11、3.13。首次安装需要联网，默认离线示例无需模型 API Key。

## 1. 先知道要检查什么

以“查询订单 123”为例：期望调用 get_order，参数 order_id 为 123，返回 not_shipped，Agent 的结构化结论也应是 not_shipped。改 Prompt 或代码后重新运行 Agent，再比较这些证据。baseline 是人工审核的预期运行；candidate 是这次改动后的实际运行。

| 名词 | 含义 | 本例 |
| --- | --- | --- |
| Agent | 根据输入执行工具并形成结论的程序 | 订单助手 |
| Tool | Agent 调用的能力 | get_order |
| Fixture | 测试用固定数据或服务 | 订单 123 尚未发货 |
| Trace | 记录运行事件的 JSON | 调用、结果、最终答案 |
| Claims | 由接入代码提供的结构化结论 | order_status=not_shipped |
| Adapter | 把 Agent 接到录制边界的适配代码 | run(request, context) |
| Contract | 明确的行为约束 | 禁止退款、最多调用一次 |
| CI gate | 根据退出码阻断回归 | 发现错误则 PR 检查失败 |

Claims 不会从自然语言自动提取。错误的业务结论必须在接入方输出的 claims 或副作用状态中可见，工具才能检查。

## 2. 五分钟跑通成功与失败


```bash
git clone --branch v4.20.0 https://github.com/ANTAO94/agent-regression-kit.git
cd agent-regression-kit
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
agent-regression --version

agent-regression record \
  --scenario examples/order-123/candidate-ok.scenario.json \
  --out work/candidate.trace.json
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/candidate.trace.json \
  --out work/reports/compare.json
```

预期：compare 返回 0，JSON 中 passed=true，blocking_difference_count=0。使用 GitHub tag 安装可避免依赖尚未确认的 PyPI 发布；不要省略激活虚拟环境。

再验证它确实能发现错误：

```bash
agent-regression record \
  --scenario examples/order-123/candidate-regression.scenario.json \
  --out work/bad.trace.json
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/bad.trace.json \
  --out work/reports/regression.json
```

预期：第二个 compare 返回 1，报告列出工具参数等阻断差异。这是故意构造的回归，不是安装失败。终端可立即执行 echo $? 查看退出码；不要把预期失败当成需要更新 baseline 的理由。

| 退出码 | 解释 | 处理 |
| --- | --- | --- |
| 0 | 比较通过 | 审查报告后继续 |
| 1 | 阻断性差异或门禁未通过 | 修复 Agent 或人工审核预期变化 |
| 2 | 输入、文件或 Trace 校验错误 | 检查路径、配置、schema 和环境 |

以上是 compare 等检查命令的约定；report-index 默认只生成索引，需 --fail-on-regression 才启用门禁。

## 3. 看报告和“回放”


```bash
agent-regression replay --trace work/candidate.trace.json
agent-regression report-index --report-dir work/reports --out work/reports/report-index.json
agent-regression ui
```

浏览器打开 http://127.0.0.1:8765/index.html。选择 baseline、candidate 和 compare JSON 查看；reports.html 选择索引；config.html 生成配置文件。按 Ctrl-C 停止服务。

replay 只校验、整理已有 Trace，**不会重新执行 Agent、模型或工具**。验证新版本必须重新 record。当前也没有自动把历史工具返回值注入任意 Agent 的通用 cassette 回放引擎。

如果你需要让 Agent 逻辑在不触碰真实工具的情况下重新执行，v3.6 起可以使用
`replay_agent_run` 或 `CassetteToolExecutor.from_trace()`。它会严格检查工具名、
参数、额外调用和漏调用，工具结果直接来自已审核 Trace；这与只读的 `replay`
命令是两种不同能力。真实工具实现仍要在隔离环境中重新 record。

要检查本地项目是否有正确的 baseline、candidate、策略和报告，可以执行：

```bash
agent-regression workspace manifest --directory . --out work/workspace-manifest.json
agent-regression baseline review \
  --baseline baselines/order-123.trace.json \
  --candidate work/candidate.trace.json \
  --format markdown --out outputs/baseline-review.md
```

`baseline review` 只生成比较报告，不修改 baseline；确认是有意的产品变化后，
仍需人工执行 `baseline accept` 并提交 Git review。`workspace manifest` 只保存
相对路径、文件大小和 SHA-256 指纹，不复制 Trace 内容。

Viewer 是本地静态页面：需要显式选择文件，配置导出后由你保存到项目中，页面不会自动写入项目、触发测试或审核 baseline。索引不会自动读取相邻的原始报告。GitHub 上的 HTML 文件链接展示源码；请本地启动 ui。

## 4. 配置断言、噪声过滤与比较范围

baseline 保存预期证据；检查规则放在独立 config 中，便于代码审查。下面是一份可以复制到 .agent-regression/config.json 的配置：

```json
{
  "baseline": "baselines/my-agent.trace.json",
  "candidate": "work/my-agent.trace.json",
  "report": "work/reports/compare.json",
  "format": "json",
  "final_answer_mode": "claims-only",
  "contract": {
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
    "max_steps": 1,
    "required_claims": [
      "final_answer.claims.order_status"
    ],
    "path_rules": {
      "any_of": [[
        {
          "tool": "get_order",
          "result": {"status": "not_shipped"},
          "is_error": false
        }
      ]]
    },
    "ignore_paths": [
      "tool_results[*].result.request_id"
    ],
    "normalizers": [
      {
        "path": "tool_results[*].result.updated_at",
        "type": "timestamp"
      }
    ]
  }
}
```


| 配置 | 用途与边界 |
| --- | --- |
| final_answer_mode=exact | 默认：最终文字和 claims 都参与比较 |
| final_answer_mode=claims-only | 允许措辞变化，仍比较 claims、工具参数和结果 |
| assertions | equals、contains、exists 三选一；检查 candidate |
| ignore_paths | 在结构化比较中移除动态字段，支持 [*]；不要忽略业务状态 |
| normalizers | timestamp 替换为固定标记；sort 按 repr 排序列表；不支持自定义表达式 |
| must_call / must_not_call | 要求或禁止工具，支持参数条件 |
| max_steps | 工具调用数量上限，不是 LLM token 或内部推理步数 |
| allow_paths | 放行比较报告中某个完整差异路径，不是嵌套通配过滤 |
| path_rules.any_of | 显式声明允许的多条工具调用路径，详见技术方案和 API |
| path_rules.mode | 路径匹配模式：`exact`、`ordered_subsequence` 或 `unordered_subset`；省略时为严格 `exact` |
| path_rules.extra_calls | 放宽模式下允许的额外调用白名单；省略保持 v4.6 兼容，`[]` 表示不允许额外调用 |
| tool_limits | 按工具和可选参数限制最小/最大调用次数；失败类别为 `tool_count` |
| tool_allowlist | 限制场景允许调用的完整工具目录；可按参数精确匹配；失败类别为 `unauthorized_tool_call` |
| argument_rules | 对指定工具的每一次调用检查参数值、Trace 参考值、必填和禁用字段；失败类别为 `tool_argument_policy` |
| side_effects | 检查 world_state 的初始/最终状态，要求先录制快照 |
| relations | 检查跨步骤字段关系，例如退款金额不超过查询结果中的 paid_amount |

tool_calls、tool_results、final_answer 是比较器提供的投影视图，不要求你修改原始 events JSON。断言针对 candidate 的原始投影，不能假定 ignore_paths 或 normalizers 会改变断言值。通配断言匹配到的值都必须满足条件。

### 跨步骤业务关系

固定断言只能检查一个字段是否等于某个值；业务 Agent 还经常需要把前一步结果传给后一步。`relations` 使用 JSON 路径和有限的比较操作符表达这种约束，不执行用户脚本：

```json
{
  "relations": [
    {
      "left": "tool_calls[1].arguments.order_id",
      "operator": "equals_path",
      "right_path": "tool_results[0].result.order_id",
      "message": "资格检查必须使用订单查询返回的订单号"
    },
    {
      "left": "tool_calls[2].arguments.amount",
      "operator": "less_or_equal_path",
      "right_path": "tool_results[0].result.paid_amount",
      "message": "退款金额不得超过订单实付金额"
    }
  ]
}
```

路径没有找到值、类型不能比较或关系不成立都会失败。支持 `equals_path`、`not_equals_path`、`less_than_path`、`less_or_equal_path`、`greater_than_path`、`greater_or_equal_path`，以及针对固定值的 `equals`、`not_equals`、`less_than`、`less_or_equal`、`greater_than`、`greater_or_equal` 和 `in`。失败报告会给出左侧路径、右侧路径或固定值，以及规则中的 `message`。

### 路径变化：允许额外查询但保持业务边界

`path_rules.any_of` 默认是完整路径严格匹配。如果 Agent 只是增加了一个合法的只读
查询，可以显式设置：

```json
{
  "path_rules": {
    "mode": "ordered_subsequence",
    "any_of": [["get_order", "get_payment_status"]],
    "extra_calls": [
      {"tool": "get_shipping", "is_error": false}
    ]
  },
  "must_not_call": ["delete_order"],
  "max_steps": 3
}
```

三种模式的区别是：

| 模式 | 规则 |
| --- | --- |
| `exact` | 默认；候选工具路径必须完整匹配，旧的 `ordered` 行为继续兼容 |
| `ordered_subsequence` | 列出的规则必须按顺序出现，前后或中间可以有额外调用 |
| `unordered_subset` | 列出的规则都必须出现，但顺序和额外调用不作为路径条件 |

v4.7 可以用 `path_rules.extra_calls` 把放宽模式收紧成显式白名单。省略该字段会保持
v4.6 兼容行为，所有未匹配的额外调用都允许；配置 `extra_calls: []` 表示不允许任何
额外调用。白名单规则可以进一步检查 `arguments`、`result` 和 `is_error`。未知额外调用
会报告 `extra_tool_call`，并同时报告整体的 `behavior_path` 失败；`extra_calls` 不能
和默认 `exact` 模式组合。

放宽路径不等于放宽业务约束。额外调用仍可能泄露数据或产生副作用，所以应同时
使用 `must_not_call`、`max_steps`、结果/is_error 条件、`assertions`、`relations`、
`side_effects` 和结构化 claims。只有业务真的允许乱序时才使用
`unordered_subset`。完整可运行案例见
[`examples/path-variation/README.md`](../examples/path-variation/README.md)。

### 按工具限制调用次数：防止循环和重复副作用

`max_steps` 只限制所有工具调用的总数；如果要表达“查询最多一次”或“退款必须恰好一次”，
使用 `tool_limits`：

```json
{
  "tool_limits": [
    {"tool": "get_order", "min_calls": 1, "max_calls": 1},
    {"tool": "refund_order", "min_calls": 1, "max_calls": 1},
    {
      "tool": "get_shipping",
      "arguments": {"order_id": "123"},
      "max_calls": 1
    }
  ]
}
```

只配置 `min_calls` 表示至少调用次数，只配置 `max_calls` 表示最多调用次数，两个值相同
表示恰好调用次数。配置 `arguments` 后，只统计工具名和参数都匹配的调用。次数不满足时，
报告会生成 `tool_count`，包含规则、报告路径和实际次数；它和 `must_not_call`、路径规则、
副作用检查互补，不能替代权限控制。完整退款案例已经用它阻断重复退款，见
[`examples/refund-business-case/README.md`](../examples/refund-business-case/README.md)。

### 场景工具白名单：拒绝未授权工具

`tool_limits` 解决“某个工具调用几次”，`tool_allowlist` 解决“这个场景根本允许
调用哪些工具”。省略 `tool_allowlist` 时保持旧版本行为；显式配置空数组表示拒绝
所有工具调用。字符串是只匹配工具名的简写，对象可以用 `arguments` 做完整参数匹配：

```json
{
  "tool_allowlist": [
    "get_order",
    "check_refund_eligibility",
    {
      "tool": "refund_order",
      "arguments": {"order_id": "123", "amount": 88}
    }
  ]
}
```

如果候选 Trace 调用了 `delete_order`，或用不同参数调用 `refund_order`，比较会失败，
并生成 `unauthorized_tool_call`，路径类似 `tool_calls[2]`。它是 Trace 证据边界，
不是生产权限系统；真实 Tool Gateway 仍必须执行权限控制。完整规则和空白名单案例见
[v4.9 验收说明](v4.9-acceptance.md)。

### 工具参数策略：防止越租户、越资源和危险参数

`tool_allowlist` 只回答“这个场景能不能调用该工具”；如果工具在白名单内，Agent 仍可能
传入错误订单、其他租户或超额金额。`argument_rules` 按工具名匹配，并检查该工具的每一
次调用。参数路径相对于本次调用的 `arguments`：

```json
{
  "contract": {
    "tool_allowlist": ["get_order", "refund_order"],
    "argument_rules": [
      {
        "tool": "get_order",
        "path": "order_id",
        "operator": "equals_path",
        "right_path": "metadata.input.order_id",
        "message": "查询必须使用用户请求中的订单号"
      },
      {
        "tool": "get_order",
        "path": "tenant_id",
        "operator": "equals_path",
        "right_path": "metadata.input.tenant_id",
        "message": "禁止跨租户查询"
      },
      {
        "tool": "refund_order",
        "path": "amount",
        "operator": "less_or_equal_path",
        "right_path": "tool_results[0].result.paid_amount",
        "message": "退款金额不得超过实付金额"
      },
      {
        "tool": "refund_order",
        "path": "admin_override",
        "operator": "absent"
      }
    ]
  }
}
```

固定值操作符使用 `value`，例如 `equals`、`less_or_equal` 和 `in`；引用 Trace 中其他
字段时使用 `*_path` 操作符和 `right_path`；`exists` 要求参数存在，`absent` 要求参数
不存在。没有调用该工具时本规则不失败，必须调用请另外配置 `must_call`。参数违规会
生成 `tool_argument_policy`，例如 `tool_calls[2].arguments.amount`，并在报告中保留
实际值、参考值和 `message`。

不要把同一条固定下标的参数关系同时写进 `relations` 和 `argument_rules`；如果条件应该
适用于某个工具的每一次调用，应优先使用 `argument_rules`。完整配置和错误案例见
[v4.10 验收说明](v4.10-acceptance.md)。

可以直接运行完整的退款案例：

```bash
python examples/refund_business_case.py \
  --behavior normal \
  --out work/refund-business-case/candidate.trace.json
agent-regression compare --config examples/refund-business-case/compare.config.json
```

案例还提供 `wrong-order`、`wrong-amount`、`skip-eligibility` 和 `duplicate-refund` 四种可控错误，用来确认门禁确实能拦截业务回归。详见 [退款业务案例](../examples/refund-business-case/README.md)。

路径规则：配置放在 .agent-regression/ 下时相对项目根目录解析；放在其他位置时相对配置文件所在目录解析。命令行参数优先于文件配置。

可运行的比较策略示例位于 v4.14.0 的 examples/quickstart/compare.config.json。已有上节 candidate 后执行：

```bash
agent-regression config validate --config examples/quickstart/compare.config.json --kind single
agent-regression check --config examples/quickstart/compare.config.json --kind single
agent-regression compare --config examples/quickstart/compare.config.json
```

config validate 检查配置结构；check 进一步读取 Trace，检查 schema 和文件是否齐全；compare 才判断行为是否回归。

## 5. 接入自己的 Agent

在你的业务项目根目录、已安装本工具的环境执行：

```bash
agent-regression init
python scripts/record_agent.py --out work/my-agent.trace.json
agent-regression validate --trace work/my-agent.trace.json
```

init 生成 scripts/record_agent.py、比较配置、baseline 说明和 CI 模板。默认保留已有文件，并不自动生成已审核 baseline。先运行生成的订单示例，审查结果后首次接受：

```bash
agent-regression baseline accept --trace work/my-agent.trace.json --out baselines/my-agent.trace.json
agent-regression check --config .agent-regression/config.json --kind single
agent-regression compare --config .agent-regression/config.json
```

baseline accept 会写入指定目标，可能覆盖已有文件；只在明确审核后执行，随后将 baseline 和策略一起提交 Git。

然后替换 scripts/record_agent.py 中的示例 Agent。接入有两个必要条件：

1. 每次工具调用经过 context.call_tool(name, arguments)，获取结果后继续业务逻辑。
2. 结束时调用 context.final_answer(text, claims)，claims 应来自实际结果解释。

可运行的最小 Python 接入：

```python
import json
from pathlib import Path
from agent_regression import CallableAgentAdapter, FixtureTools, record_run

def invoke(request, context):
    order = context.call_tool("get_order", {"order_id": request["order_id"]})
    context.final_answer("Order status: " + order["status"],
                         {"order_status": order["status"]})

trace = record_run(
    CallableAgentAdapter({"name": "my-agent", "version": "1.0"}, invoke),
    {"order_id": "123"},
    FixtureTools({"get_order": {"status": "not_shipped"}}),
    run_id="order-123",
)
Path("work").mkdir(exist_ok=True)
Path("work/my-agent.trace.json").write_text(
    json.dumps(trace.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
)
```

这段示例是确定性业务回调；真实模型的工具分发器也必须接到同样的 context。只包住一个已经完成所有内部工具调用的 invoke，并不能自动捕获内部行为。

FixtureTools 按工具名返回固定值，不按 arguments 匹配；参数错误依靠 compare/contract 检测。需要参数分支时，实现 ToolExecutor.call(tool, arguments) 或使用 StatefulFixtureTools。

Python 是当前 SDK 的实现语言。Java/Spring AI 或 TypeScript 系统需要自行插桩后输出符合 schema 的 JSON，或自建桥接层；目前没有现成的 Java/TypeScript SDK。MCP Server 是工具服务，不等于完整 Agent。

需要更正式的同步/异步适配器模板：

```bash
agent-regression adapter-init --directory my-adapter --name my-agent --mode both
cd my-adapter
PYTHONPATH=. python -m unittest discover -s tests -v
```

可选框架示例：返回仓库根目录，安装 examples/optional-requirements.txt，运行 examples/langchain_core_callback_example.py。它验证 RunnableLambda 回调边界，无需模型密钥，不证明完整 LangGraph 或任意生产 Agent 的自动兼容。

## 6. CI：使用相同配置执行门禁

将下面内容保存为业务项目 .github/workflows/agent-regression.yml。前提：已提交 scripts/record_agent.py、审核后的 baseline 和 .agent-regression/config.json，且本地 compare 已通过。

```yaml
name: Agent regression
on: [push, pull_request]
permissions:
  contents: read
jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.11"
      - name: Install
        id: install
        run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git@v4.20.0"
      - name: Record candidate
        run: python scripts/record_agent.py --out work/my-agent.trace.json
      - name: Validate inputs
        run: agent-regression check --config .agent-regression/config.json --kind single
      - name: Compare with project policy
        shell: bash
        run: |
          set +e
          agent-regression compare --config .agent-regression/config.json --format json --out work/reports/compare.json
          json_status=$?
          agent-regression compare --config .agent-regression/config.json --format markdown --out work/reports/compare.md
          markdown_status=$?
          agent-regression compare --config .agent-regression/config.json --format junit --out work/reports/compare.xml
          junit_status=$?
          if [ -f work/reports/compare.md ]; then
            cat work/reports/compare.md >> "$GITHUB_STEP_SUMMARY"
          fi
          if [ "$json_status" -ne 0 ]; then exit "$json_status"; fi
          if [ "$markdown_status" -ne 0 ]; then exit "$markdown_status"; fi
          exit "$junit_status"
      - name: Index reports
        if: always() && steps.install.outcome == 'success'
        uses: ANTAO94/agent-regression-kit/.github/actions/agent-report-index@v4.20.0
        with:
          report-dir: work/reports
          json-report: work/reports/report-index.json
          markdown-report: work/reports/report-index.md
          fail-on-regression: 'true'
      - uses: actions/upload-artifact@v7
        if: always()
        with:
          name: agent-regression-report
          path: work/reports/
```

自定义 contract 可以通过 `compare --config` 生效；v3.5 起 agent-regression
composite Action 也接受 `config` 输入，旧的 baseline/candidate、allow-path、
allow-category、final-answer-mode 用法仍兼容。报告完整性可以在 Report Index
Action 中传 `required-reports: compare.json,coverage.json`。

此示例在差异存在时仍生成三种报告并保留非零退出码。JUnit 是可供 CI 系统读取的测试报告格式；这里上传文件，并不自动创建逐测试用例的 GitHub Checks 注释。索引是汇总导航，不能取代前面各命令的失败状态。每次 CI 用独立目录，别混入旧失败样例。

## 7. 扩展场景

### v4.14：可审计 benchmark 流程

当你需要公开“误报/漏报”数字时，使用 manifest 把数据源、拆分、证据、Contract、标签和
包版本固定下来，并把决定与评分分开：

```bash
agent-regression benchmark prepare --manifest benchmark/manifest.json
agent-regression benchmark decide --manifest benchmark/manifest.json --out work/benchmark/decisions.json
agent-regression benchmark score --manifest benchmark/manifest.json --decisions work/benchmark/decisions.json --out work/benchmark/score.json
```

`prepare` 检查所有 SHA-256 和样本/Contract 覆盖；`decide` 只读取 Trace 和 Contract，不读取
标签语义；`score` 校验 `decision_digest` 后才读取 `labels.json`。报告包含混淆矩阵、Wilson
95% 区间和 provenance；`unsupported` 会明确列出。不要把 reward、人工标签或期望结论写进
Trace、claims 或 Contract。完整 manifest 示例见 [v4.14 验收](v4.14-acceptance.md)。

| 需求 | 入口 | 使用注意 |
| --- | --- | --- |
| 多用例 | batch-record / batch-compare | baseline/candidate 使用相同相对文件名；缺文件失败 |
| 真实 MCP | mcp-record / record_mcp_run / mcp-http-record | 指向本地 Fixture 或测试服务；不要把 MCP 等同于 Agent 框架 |
| 多轮追问 | session-record / session-compare | 每轮独立 Trace，跨轮复用 Agent/工具状态 |
| 并行工具 | async_record_run | 用 await 和 parallel_group 记录并行组 |
| 状态清理 | isolated_record_run / SnapshotBackend | 只恢复你接入的状态；数据库事务/外部服务清理由业务实现 |
| 随机性 | record_stability | 每次新建 Agent/工具；CLI stability 用脚本场景，真实模型用 API |
| 场景覆盖 | coverage | 统计工具路径和 claims 分支，不是代码覆盖率 |
| 长期趋势 | history | 按文件名顺序聚合；只在同一用例/指标的历次报告间解释趋势 |
| 报告导航 | report-index | 收集 compare/batch/stability/coverage/history；可选失败门禁 |

命令和完整示例见[高级使用指南](usage-guide.zh-CN.md)与[API 参考](api.md)。history 的退出码跟随最后一个识别的历史点；report-index 则要求收集到的报告全部通过。它们不是相同门禁语义。

### 用独立 Agent 项目验证框架

v4.13 自带一个可复现的独立项目适配案例：验证
[tau2-bench](https://github.com/sierra-research/tau2-bench) 已发布的零售轨迹。
当你希望证据不只来自仓库自己的 toy fixture 时，可以按下面四步执行：

1. 查看 `examples/tau2-retail/source.json`，确认上游 tag、commit 和数据集校验和。
2. 下载固定数据集并运行 `examples/tau2_retail_validation.py`。
3. 检查 `work/tau2/report.json` 和导出的样例 Trace。
4. 复用 `.github/workflows/tau2-independent-validation.yml`，让数据篡改或
   质量回归在 CI 中失败。

验证器把工具调用和结果映射为 `AgentTrace`，从任务的期望写操作和通信要求
生成 Contract，然后才与上游 reward 对比；reward 不会变成 claims，也不会
作为 Contract 输入。固定的 456 次 simulation 中，420 个写场景可纳入契约：
267 个 true pass、153 个 true block、0 个 false alarm、0 个 missed failure；
准确率、失败召回率和漏报率分别为 100%、100% 和 0%。这组结果从 v4.14 起标记为
calibration，因为历史标签曾参与规则设计，不能当作未见数据泛化成绩。

这是一个独立兼容性与测量案例，不代表 tau2-bench 上游背书或依赖本项目。
完整字段映射和限制见 [`docs/tau2-independent-validation.md`](tau2-independent-validation.md)。

### v4.16：首次接入模板与性能基线

如果你还没有自己的接入代码，在项目根目录执行：

```bash
agent-regression init
python scripts/record_agent.py --variant normal --out work/my-agent.trace.json
agent-regression check --config .agent-regression/config.json
agent-regression compare --config .agent-regression/config.json
```

`init` 会生成并预置：

- `baselines/my-agent.trace.json`：由本地 MCP Fixture 生成的可审核 baseline；
- `work/my-agent.trace.json`：初始 candidate，便于第一次 `check` 直接通过；
- `.agent-regression/config.json`：包含 required claims、工具参数、禁用工具和步数限制；
- `AGENT_REGRESSION.md`：中英文起步说明；
- `.github/workflows/agent-regression.yml`：固定到当前 Release tag 的 CI。

`scripts/record_agent.py` 的 `normal` 会通过，`wrong-resource`、`skip-tool`、
`misread-result` 是故意失败的教学变体，预期比较退出码为 1。把其中的
`ExampleAgent` 替换成你的真实 Agent，保留 `context.call_tool` 和结构化 `claims`。

预检命令除了校验路径和 Trace，还会给出 `guidance` 与 `next_actions`；它们是建议，不会
改变 compare 的阻断语义。Markdown/JSON compare 报告也会把阻断类别映射成下一步动作。

框架自身性能基线：

```bash
agent-regression performance run --out work/performance-baseline.json
mkdir -p performance
cp work/performance-baseline.json performance/reference.json
agent-regression performance gate \
  --current work/performance-baseline.json \
  --baseline performance/reference.json \
  --out work/performance-gate.json
```

默认耗时回退超过 20% 报警，超过 40% 阻断；性能结果必须在同一 Python、操作系统和硬件
条件下比较。详见[性能基线说明](performance.md)与[v4.16 验收](v4.16-acceptance.md)。

### v4.20：任务级留出代理

如果想验证“规则是否只在原始公开轨迹上有效”，可以按 task ID 做互斥分区。分区算法只读
task ID，不读 reward；脚本会校验任务集合哈希，然后在 holdout 上运行同一套 Contract：

```bash
python3 examples/tau2_telecom_holdout_validation.py \
  --results work/tau2-telecom/results.json \
  --source-manifest examples/tau2-telecom/source.json \
  --split-definition examples/tau2-telecom/task-split.json \
  --partition holdout \
  --out work/tau2-telecom-holdout/report.json \
  --min-eligible 80 \
  --min-failures 30 \
  --min-failure-recall 0.99 \
  --max-false-alarm-rate 0.05 \
  --max-missed-failure-rate 0.0
```

公开 holdout 为 28 个任务、100 个可判定场景，结果 47/53/0/0；prospective o4-mini 为
50/46/4/0，失败召回率 100%、误报率 7.41%。它是同一公开任务族内的 task-disjoint
holdout 代理，不是独立来源任务集或通用未见域泛化。完整边界见[v4.20 验收](v4.20-acceptance.md)。

### v4.19：电信域 actor 边界与环境断言

电信域不是把所有工具调用简单拼成一条回放列表。轨迹中的 `assistant` 调用代表 Agent
行为，`user` 调用代表模拟器/环境动作。适配器只用 assistant-owned 写操作构建 Contract，
并把 user-owned 结果作为环境断言证据：

```bash
python3 examples/tau2_telecom_validation.py \
  --results work/tau2-telecom/results.json \
  --source-manifest examples/tau2-telecom/source.json \
  --out work/tau2-telecom/report.json \
  --traces-dir work/tau2-telecom/sample-traces \
  --min-eligible 300 \
  --min-failures 200 \
  --min-failure-recall 0.99 \
  --max-false-alarm-rate 0.05 \
  --max-missed-failure-rate 0.0
```

v4.19 的公开电信结果包含 364 个 assistant-write 可判定场景、92 个 user-only 排除场景，
结果为 147/217/0/0；prospective o4-mini 结果为 136/216/9/3。后者使用显式的
98% 召回、10% 误报、2% 漏报观察阈值。它是有限领域适配和可追溯验证，不是通用模拟器状态
还原，也不是未见任务泛化证明。完整命令、来源和限制见[电信复现](../examples/tau2-telecom/README.md)
与[v4.19 验收](v4.19-acceptance.md)。

### v4.18：路径噪音字段与第二任务域

如果 baseline 的路径规则没有声明某个传输字段，但 candidate 每次运行都会生成不同值，
可以使用 `path_rules.ignore_argument_paths`：

```json
{
  "contract": {
    "path_rules": {
      "any_of": [[{"tool": "get_order", "arguments": {"order_id": "123"}}]],
      "ignore_argument_paths": ["request_id"]
    }
  }
}
```

它只忽略 baseline 没有写出的字段；如果 baseline 明确写出 `request_id`、订单号或支付 ID，
这些值仍然严格检查。与 outcome 意图分组使用的 `state_equivalence.ignore_argument_paths`
不要混用。完整的航空域复现命令见[航空示例](../examples/tau2-airline/README.md)，v4.18
验收数据为 246 项测试、已发布航空结果 120 个适用场景和 100% 失败召回。

### v4.17：外部评测 provenance

外部模型结果不能只看最终数字，必须确认结果文件和来源 manifest 是同一份数据。运行 tau²
prospective 评测时，使用匹配的 manifest：

```bash
python3 examples/tau2_retail_validation.py \
  --results work/tau2-prospective/results.json \
  --source-manifest examples/tau2-retail/prospective-o4-mini-source.json \
  --out work/tau2-prospective/report.json \
  --min-eligible 300 \
  --min-failures 50
```

如果 SHA-256 不匹配，命令会在写报告前失败；报告会保留结果哈希、manifest 哈希和 source
manifest 哈希。`--min-failures` 防止只有极少失败样本时用百分比制造虚假确定性。v4.17 的
固定 o4-mini 结果为 420 个可判定样本、126 个失败样本、失败召回率 100%、误报率 2.04%。
这属于模型结果级 prospective 证据，不是未见任务域泛化。详见[v4.17 验收](v4.17-acceptance.md)。

## 8. v4 兼容检查与迁移

v4 把升级前检查做成 CLI，而不是只靠阅读变更记录。它会分别检查公共
Python API 代际、Trace、Session、Contract/config 和 Report 的 schema 边界：

```bash
agent-regression compatibility \
  --public-api-version 4 \
  --trace baselines/order-123.trace.json \
  --config .agent-regression/config.json \
  --report outputs/compare.json \
  --out outputs/compatibility.json
```

退出码 `0` 表示输入兼容，`1` 表示版本/schema 不支持，`2` 表示文件或
JSON 输入错误。v3 公共 API 会返回 `status=deprecated` 和
`migration_required=true`，不会被悄悄当成当前版本。

Trace schema 0.1 在 v4 没有改变，但仍提供显式迁移入口，源文件不会覆盖：

```bash
agent-regression migrate trace \
  --trace baselines/order-123.trace.json \
  --out work/order-123.v4.trace.json \
  --report outputs/order-123.migration.json
agent-regression validate --trace work/order-123.v4.trace.json
```

迁移报告只记录迁移状态和 schema 版本，不复制 Trace 事件。完整的 v4 验收
清单见 [v4.9 验收说明](v4.9-acceptance.md)；调用次数边界见 [v4.8 验收说明](v4.8-acceptance.md)，路径白名单边界见 [v4.7 验收说明](v4.7-acceptance.md)。

## 9. 排错与维护

| 现象 | 先检查 |
| --- | --- |
| command not found | 是否激活 .venv，或使用 .venv/bin/agent-regression |
| 配置有效但 check 失败 | Trace 是否生成，路径基准是否正确 |
| 正常回复却回归 | exact 模式会比较文字；需要时改为 claims-only，并保留业务断言 |
| 参数错误却工具返回正常 | FixtureTools 按工具名匹配；检查参数差异/断言 |
| 自定义策略在 CI 消失 | 是否错误使用不支持 --config 的 Action |
| 更换模型后大量变化 | 先保留报告，逐条审核噪声与业务差异，再决定更新 baseline |
| 报告泄露信息 | 检查录制、比较及上传边界；默认脱敏不保证所有自由文本和路径都安全 |

同步 RunContext 将脱敏后的工具结果返回给 Agent；如果敏感字段也参与业务决策，必须在测试设计中评估这项行为。真实模型/工具的调用会有成本和副作用，使用隔离环境。

维护基线：固定模型/Prompt/工具 schema → 录制 → 审查行为与契约 → 显式接受 → Git review。升级框架先运行旧基线，不要自动刷新基线来让 CI 变绿。发布记录见 [CHANGELOG](../CHANGELOG.md) 和 [UPGRADING](../UPGRADING.md)。
