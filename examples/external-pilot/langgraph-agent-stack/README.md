# LangGraph Agent Stack pilot

这是一个独立公开项目的技术预演，不代表该项目维护者采用或认可 Agent
Regression Kit。它验证两条边界：能否从一个未修改的 LangGraph graph 采集真实
工具生命周期，以及能否用业务事实断言阻断结果回归。

候选项目固定到本次验证的 commit：
`a8a2dac566d46c48619ba94c69dfffb1b370520d`。

候选项目：<https://github.com/Brescou/langgraph-agent-stack>

## 这次到底测什么

场景是一个文档研究 Agent。它读取仓库内的 `research-fixture.json`，资料内容是
对 LangGraph 官方 Persistence 文档的固定摘要，来源 URL 仍保留在 Trace 中。Agent
需要通过真实的 `ResearchAgent` LangGraph graph 完成检索和总结，最后输出四个业务事实：

| 事实 | 期望值 |
| --- | --- |
| checkpointer 的范围 | `single_thread`：保存单个线程的 graph 状态 |
| store 的范围 | `cross_thread`：保存可跨线程使用的应用数据 |
| 线程持久化是否需要 `thread_id` | `true` |
| 内存 checkpointer 是否跨进程重启保留 | `false` |

`FACTS_JSON` 是这个固定场景的结构化输出边界。`capture_trace.py` 从 Agent 实际
产生的 summary 中解析它，再写入 `final_answer.claims.facts`；它不是在写 Trace 时
直接把期望答案塞进去。比较配置中的 assertions 才是审核过的业务契约。

这次仍然使用候选项目的 mock provider 和固定资料，因此不产生 API 费用、不访问真实
搜索服务，也不证明真实模型的事实性。它证明的是：真实外部 graph 的运行证据可以
进入统一 Trace，并且固定资料上的业务结论变化能够被 CI 门禁发现。

## 运行前提

- Python 3.12+；
- `uv`；
- 候选项目依赖已安装；
- 不需要 LLM API Key，不访问真实搜索服务。

```bash
git clone https://github.com/Brescou/langgraph-agent-stack.git /tmp/langgraph-agent-stack
cd /tmp/langgraph-agent-stack
git checkout a8a2dac566d46c48619ba94c69dfffb1b370520d
uv sync
```

还需要把 Agent Regression Kit 安装到候选项目的独立虚拟环境。假设本仓库位于
`/path/to/agent-regression-kit`：

```bash
KIT=/path/to/agent-regression-kit
STACK=/tmp/langgraph-agent-stack
uv pip install --python "$STACK/.venv/bin/python" "$KIT"
"$STACK/.venv/bin/python" -c "import agent_regression; print(agent_regression.__file__)"
```

最后一条命令应输出候选虚拟环境中的安装路径。CI 使用更严格的方式：先构建 wheel，
再安装到候选环境，并确认导入位置不在本仓库的 `src/` 目录中。

## 1. 运行候选项目自己的 mock eval

```bash
LLM_PROVIDER=mock SEARCH_PROVIDER=mock \
  uv run python -m evals --all --json --thresholds
```

本次验证结果：3 个数据集、8 个案例、8/8 通过，退出码 0；成本为 `$0.00`。这是
候选项目自己的结构化 mock eval，不是在线模型质量测试。

## 2. 采集并比较真实 event stream

下面的脚本在本项目内，候选项目不需要修改。它会：

1. 检查候选 checkout 是干净的，并且确实是固定 commit；
2. 启动候选项目真实的 `ResearchAgent` graph；
3. 在 `web_search` 的真实调用边界记录实际 query 和 Agent 真正收到的固定资料；
4. 从 LangGraph v2 event stream 转换 `on_tool_start/end` 和最终结果；
5. 从最终 summary 解析业务 facts，缺少 facts 时直接失败；
6. 与仓库中人工审核后提交的 `baseline.trace.json` 比较。

```bash
KIT=/path/to/agent-regression-kit
STACK=/tmp/langgraph-agent-stack
PY="$STACK/.venv/bin/python"
CAP="$KIT/examples/external-pilot/langgraph-agent-stack/capture_trace.py"
CONFIG="$KIT/examples/external-pilot/langgraph-agent-stack/compare.config.json"
FIXTURE="$KIT/examples/external-pilot/langgraph-agent-stack/research-fixture.json"

"$PY" "$CAP" \
  --project-dir "$STACK" \
  --fixture "$FIXTURE" \
  --run-id "langgraph-agent-stack-candidate" \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/work/candidate.trace.json"

"$PY" -m agent_regression compare \
  --config "$CONFIG" \
  --baseline "$KIT/examples/external-pilot/langgraph-agent-stack/baseline.trace.json" \
  --candidate "$KIT/examples/external-pilot/langgraph-agent-stack/work/candidate.trace.json" \
  --out "$KIT/examples/external-pilot/langgraph-agent-stack/work/compare.json"
```

正常运行应退出 `0`，报告为 `passed: true`。检查 `candidate.trace.json` 可以看到：

- 3 个 `web_search` 工具调用及其实际 query；
- 官方资料 URL 和文档 ID；
- 最终 `FACTS_JSON`；
- `final_answer.claims.facts` 中的四个业务事实。

事实由 Agent summariser 收到的摘录正文确定，不从 fixture 的 `facts` 字段复制。
`facts` 字段只代表维护者审核的期望值，用来交叉检查资料和配置。

不要在 CI 中重新生成 baseline。当前 baseline 是本项目维护者针对固定资料审核的
技术参考；接入真实业务后，只有完成业务审核才允许人工更新提交的 baseline。

## 3. 验证允许的变化不会误报

### 3.1 只变化展示措辞

```bash
"$PY" "$CAP" --project-dir "$STACK" \
  --run-id wording --vary-presentation \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/work/wording.trace.json"
"$PY" -m agent_regression compare --config "$CONFIG" \
  --baseline "$KIT/examples/external-pilot/langgraph-agent-stack/baseline.trace.json" \
  --candidate "$KIT/examples/external-pilot/langgraph-agent-stack/work/wording.trace.json"
```

预期退出 `0`。配置使用 `claims-only`，所以最终自然语言前缀变化不会被当成业务回归。

### 3.2 证据 ID 顺序变化

```bash
"$PY" "$CAP" --project-dir "$STACK" \
  --run-id evidence-order --vary-evidence-order \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/work/evidence.trace.json"
"$PY" -m agent_regression compare --config "$CONFIG" \
  --baseline "$KIT/examples/external-pilot/langgraph-agent-stack/baseline.trace.json" \
  --candidate "$KIT/examples/external-pilot/langgraph-agent-stack/work/evidence.trace.json"
```

预期退出 `0`。配置只对 `evidence_ids` 做显式排序归一化，四个事实仍然严格断言。

## 4. 验证错误会被阻断

这些是测试框架检测能力的确定性负向用例，不是候选项目真实缺陷。每条命令之后都
要单独执行 compare；预期退出码为 `1`。

```bash
# 1. 在真实 web_search 边界替换 query；应出现 required_tool / tool_result 差异
"$PY" "$CAP" --project-dir "$STACK" \
  --run-id wrong-query --mutate-search-query "unrelated topic" \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/work/wrong-query.trace.json"

# 2. 移除必要的 web_search；应出现 tool_count / required_tool 差异
"$PY" "$CAP" --project-dir "$STACK" \
  --run-id skipped-search --skip-search \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/work/skipped-search.trace.json"

# 3. 在 Agent 执行期间把 checkpointer 的事实改成 cross_thread；
#    应出现 contract_assertion / result_interpretation 差异
"$PY" "$CAP" --project-dir "$STACK" \
  --run-id misread --misread-fact checkpointer_scope \
  --output "$KIT/examples/external-pilot/langgraph-agent-stack/work/misread.trace.json"
```

这里的第三种用例与“只把 Trace JSON 的 confidence 改成 0.10”不同：错误事实是在
summary 被候选 Agent 解析前注入，最终 claims 再从错误 summary 读取，契约因此能够
定位真实的结构化业务结论变化。旧的 `--mutate-confidence` 仍保留，但只用于比较器
专项，不作为业务误读证据。

## 5. 比较规则在哪里

[`compare.config.json`](compare.config.json) 是本场景的 Contract：

- `required_claims` 要求四个事实和 evidence IDs 必须存在；
- `assertions` 要求四个事实必须等于审核值；
- `must_call` 要求三条检索 query 真实出现；
- `tool_limits` 要求恰好三次检索；
- `normalizers` 只允许 evidence ID 重排；
- `path_rules` 允许这三个只读检索以任意顺序完成，但不会放宽 query 内容。

因此“换个顺序”可以通过，“查了无关主题”仍然会失败。这就是传统流量回放里
断言字段、噪音规则和关键路径约束在 Agent 场景中的对应关系。

## 6. CI 证据

`.github/workflows/langgraph-external-pilot.yml` 会：

- 固定 clone 上游 commit；
- 在候选项目虚拟环境中安装本项目构建的 wheel，并检查导入来自 `site-packages`；
- 校验提交的 baseline，而不是现场重录 baseline；
- 运行正常、两种合法变化和三种负向用例；
- 检查负向报告里确实包含预期类别，而不是只检查退出码；
- 上传所有 Trace 和 compare 报告。

当前工作流安装的是本次源码构建的 `4.36.1` wheel，不是 PyPI/GitHub Release 下载物。
因此这是“独立环境 wheel 边界”证据，发布包验证仍待真正发布一个新版本后补做。

## 已知边界

- harness 为了观察 event stream 和注入确定性用例，会访问候选项目的私有
  `_graph`/`_invoke_llm_with_retry`；长期业务接入只应依赖公开运行事件、工具边界和
  业务方 claims/Contract。
- 候选项目的 `web_search` 在普通 Python 节点内执行，最终 `messages` 里没有工具
  调用；所以本预演使用 `trace_from_langgraph_events(...)`，不能只用最终 message state。
- 固定资料和 mock provider 用于可复现回归，不证明在线搜索质量、真实模型事实性或
  上游项目维护者采用。
- 目前是一个技术预演，尚未有业务负责人审核的 10–20 个真实案例、历史缺陷发现或
  外部团队持续使用记录；这些仍是后续 P1/P3 验收项。
