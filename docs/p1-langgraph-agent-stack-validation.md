# P1 LangGraph 项目接入验证

日期：2026-09-21。对应规划：[product-iteration-plan.zh-CN.md](product-iteration-plan.zh-CN.md)。

## 结论

本轮对独立公开项目
[`Brescou/langgraph-agent-stack`](https://github.com/Brescou/langgraph-agent-stack)
做了可复现的技术预演，候选代码固定在：
`a8a2dac566d46c48619ba94c69dfffb1b370520d`。

预演已经证明：不修改候选项目业务图，可以从其真实 `ResearchAgent` LangGraph
event stream 采集工具生命周期，补回普通 `messages` 状态中缺失的工具参数，并把
最终研究结果转换成有效 `AgentTrace`。本轮又增加了一个固定的业务资料场景：使用
仓库提交的官方 LangGraph Persistence 文档摘要，检查四个结构化事实是否保持正确。

准确的状态是：**P1 技术接入和固定资料回归链路完成；真实模型质量、业务负责人审核、
真实历史缺陷和外部持续采用仍未完成。**

## 验证场景

资料 fixture：[research-fixture.json](../examples/external-pilot/langgraph-agent-stack/research-fixture.json)。
来源是 LangChain 官方 Persistence 文档：
<https://docs.langchain.com/oss/python/langgraph/persistence>，快照日期为
2026-09-21。仓库内只保存短小的中文/英文事实摘要和来源标识，没有把在线页面当成
运行时依赖。

Agent 要回答四个问题：

| 业务字段 | 审核值 |
| --- | --- |
| `checkpointer_scope` | `single_thread` |
| `store_scope` | `cross_thread` |
| `thread_id_required` | `true` |
| `in_memory_survives_restart` | `false` |

最终 summary 中的 `FACTS_JSON` 由固定 provider 在 Agent 执行中产生；harness 的
`_claims` 从实际 `ResearchResult.summary` 解析 facts。它没有把期望值直接写进
Trace。期望值只出现在 [compare.config.json](../examples/external-pilot/langgraph-agent-stack/compare.config.json)
的 assertions 中，作为本轮固定资料场景的维护者审核 Contract；它还不是外部业务
负责人确认的生产契约。

## 可复现结果

| 检查 | 结果 |
| --- | --- |
| 候选环境 | `uv sync`，Python 3.13.15 |
| 候选项目自带 mock eval | 3 个数据集、8 个案例、8/8 通过、退出码 0 |
| 上游代码 | 固定 commit，checkout clean；不修改候选源码 |
| 工具边界 | 3 个 `web_search` query 被实际 wrapper 捕获，并与 event stream 数量一致 |
| 官方资料 fixture | 3 条检索结果、1 个官方来源 URL、3 个 evidence ID |
| 维护者审核基线 | `baseline.trace.json` 已提交；包含 source revision、fixture ID、fixture hash 和 source snapshot |
| 独立 wheel | wheel 安装到候选项目 `.venv`，从 `site-packages` 导入；当前是源码构建 wheel，不是已发布 Release |
| 正常候选 | 退出码 0，`passed: true`，无阻断差异 |
| 合法展示变化 | `--vary-presentation`，退出码 0 |
| 合法证据顺序变化 | `--vary-evidence-order`，退出码 0；只对 evidence IDs 做排序归一化 |
| 错误检索参数 | `--mutate-search-query "unrelated topic"`，退出码 1；包含 `required_tool` |
| 跳过必要检索 | `--skip-search`，退出码 1；包含 `tool_count` |
| 事实误读 | `--misread-fact checkpointer_scope`，退出码 1；包含 `contract_assertion` 和 `result_interpretation` |
| 比较器专项 | `--mutate-confidence 0.10`，退出码 1；不作为业务误读证据 |

候选项目的 mock eval 成本为 `$0.00`。候选项目的测试是候选项目自己的质量证据；本
项目负责把运行证据、事实 Contract 和 CI 门禁串起来。

## 本轮实现

### 1. 固定资料和结构化 facts

`research-fixture.json` 定义请求、三个检索 query、三个文档片段、来源 URL 和四个
审核事实。`capture_trace.py` 在真实 `web_search.invoke(...)` 调用边界记录 query，
调用原始 mock 工具后用固定资料快照替换返回内容，以保证离线、可重复和可审查。

这不是在线搜索适配器，也不是模型评测。它是“真实 graph + 固定资料 + 业务断言”的
回归夹具，后续可以把同一边界替换为真实 connector 或隔离的测试搜索服务。

### 2. 结果误读变体

`--misread-fact checkpointer_scope` 会在 summariser 响应被候选 Agent 解析前，将
`single_thread` 改为 `cross_thread`。Agent 仍然完成真实 graph 运行，最终 summary
和 claims 都来自该错误响应；compare 通过 Contract assertion 阻断。这个变体比只在
Trace 写出后修改 confidence 更接近“工具证据存在，但 Agent 得出了错误业务结论”。

### 3. 固定 baseline 和更强 CI

CI 不再现场生成 baseline，而是复制维护者审核的仓库文件；只有 candidate 每次重新运行。
工作流还验证：

- 候选项目 checkout 没有未提交文件；
- kit 从候选项目虚拟环境的 `site-packages` 导入；
- 正常用例和两种合法变化通过；
- 三种负向用例返回退出码 1；
- 每种负向报告包含预期的差异类别；
- Trace 和 compare 报告作为 artifact 上传。

### 4. 生命周期适配

`trace_from_langgraph_events(...)` 处理：

- `on_tool_start` → `tool_call`；
- `on_tool_end` → 成功 `tool_result`；
- `on_tool_error` → `is_error=true` 的 `tool_result`；
- 缺失工具输入时由接入方显式提供 `tool_input_resolver(event, ordinal)`；
- 未闭合生命周期、未知 `run_id`、缺少 tool 名称时失败。

在本 pilot 中，event stream 中所有工具开始事件都必须是 `web_search`，并且 event
数量必须等于真实工具边界捕获数量；参数缺失不会静默退化为空对象。

## 还没有完成的验收

以下项目不能用本轮的 mock fixture 或注入变体代替：

1. 尚未有上游维护者或业务负责人审核并确认这套业务基线；公开项目技术接入不等于
   维护者采用。
2. 尚未使用真实 provider 做重复运行，也没有在线搜索质量、模型事实性或费用数据。
3. 当前是一个固定场景，不是规划中的 10–20 个业务审核案例；且该候选 Agent 本身
   只有一个 `web_search` 工具的重复调用，尚未满足“两个依赖工具步骤”的完整业务
   验收目标。
4. 尚未记录真实历史回归、误报/漏报或两个真实业务改动周期。
5. 当前 CI 安装的是源码构建的本地 wheel；发布到 GitHub Release/PyPI 后还要再做
   版本、哈希和全新环境安装验证。
6. 尚未完成 P3 的 3 名独立使用者、3 个项目和连续两个周期的试点。

所以本文件应被引用为 **P1 技术预演和证据链验证**，不能写成“框架已经通过真实
业务验证”或“上游项目已经采用”。下一步是找一个愿意提供业务审核和两个依赖工具
步骤的独立项目，再把这套固定场景升级成其真实业务 baseline。
