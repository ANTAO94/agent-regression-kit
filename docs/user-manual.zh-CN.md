# Agent Regression Kit 使用手册

[English](user-manual.en.md) · [技术方案](technical-design.zh-CN.md) · [首页](../README.md)

适用：v4.3.0。以下命令面向 macOS/Linux Bash 或 Zsh，默认在仓库根目录执行。核心包要求 Python ≥ 3.9；远端矩阵覆盖 3.9、3.11、3.13。首次安装需要联网，默认离线示例无需模型 API Key。

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
git clone --branch v4.3.0 https://github.com/ANTAO94/agent-regression-kit.git
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
| side_effects | 检查 world_state 的初始/最终状态，要求先录制快照 |

tool_calls、tool_results、final_answer 是比较器提供的投影视图，不要求你修改原始 events JSON。断言针对 candidate 的原始投影，不能假定 ignore_paths 或 normalizers 会改变断言值。通配断言匹配到的值都必须满足条件。

路径规则：配置放在 .agent-regression/ 下时相对项目根目录解析；放在其他位置时相对配置文件所在目录解析。命令行参数优先于文件配置。

可运行的比较策略示例位于 v4.3.0 的 examples/quickstart/compare.config.json。已有上节 candidate 后执行：

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
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        id: install
        run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git@v4.3.0"
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
        uses: ANTAO94/agent-regression-kit/.github/actions/agent-report-index@v4.3.0
        with:
          report-dir: work/reports
          json-report: work/reports/report-index.json
          markdown-report: work/reports/report-index.md
          fail-on-regression: 'true'
      - uses: actions/upload-artifact@v4
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
清单见 [v4.3 验收说明](v4.3-acceptance.md)。

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
