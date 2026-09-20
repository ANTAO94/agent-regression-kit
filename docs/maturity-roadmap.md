# Agent Regression Kit：成熟框架路线图

本文档把“成熟”定义成可验收的工程目标，而不是功能数量。当前仓库的
v4.4 核心已经可以作为开发团队的本地/CI Agent 回归测试工具使用；后续版本重点是
让真实团队接入、服务层需求和更广泛的框架兼容性形成证据，而不是继续堆叠孤立功能。

## 成熟框架的定义

一个团队可以在不阅读核心实现的情况下完成下面的闭环：

```text
安装 → 初始化 → 接入 Agent → 录制 baseline → 生成 candidate
→ 查看差异 → 在 CI 阻断回归 → 在新版本中安全升级
```

最低验收标准：

1. Trace schema、比较策略和公共 API 有版本边界，旧 Trace 不会被悄悄改义。
2. 新用户可以用模板接入一个 Agent，并在离线 Fixture 上跑通契约测试。
3. CLI、配置文件、报告和退出码在本地与 CI 中保持一致。
4. 失败能够定位到差异类别、路径、baseline 值和 candidate 值。
5. 有状态、异步、MCP、多轮和非确定性场景都有明确的限制说明。
6. wheel 安装后仍包含 CLI、Viewer、Fixture 和文档入口。
7. 每个版本都有测试、安装验证、变更记录和升级说明。
8. 安全边界明确：默认 loopback、敏感值脱敏、baseline 不自动覆盖。

## 当前状态

| 能力 | 当前状态 | 说明 |
| --- | --- | --- |
| Trace / compare / contract | 已具备 | v3.2 核心，结构化比较和确定性契约 |
| MCP stdio / HTTP | 已具备 | 含本地 Fixture、兼容性 smoke test 和协议错误边界 |
| Stability / async / session / coverage | 已具备 | 可作为 CI 门禁，但仍是证据型评测，不是统计学证明 |
| Adapter SDK / 模板 | 已具备 | 框架回调边界稳定，含同步/异步接入诊断；框架内部生命周期仍由接入方负责 |
| 本地配置中心 | v3.2 | 表单生成 config JSON，暂不调用 Agent |
| 本地 Trace Inspector | v3.2 | 读取 Trace 和 compare JSON，Python 比较器仍是事实来源 |
| 报告索引与批量 Viewer | v3.3 | 读取 report-index JSON，按相对路径交接多份报告 |
| 统一报告 Action / Job Summary | v3.4 | compare、coverage 和其他 JSON 报告共享输出目录与交接入口 |
| 可信门禁 | v3.5 | required claims、required reports、Action config 和错误注入验收 |
| `agent-regression ui` | v3.2 | loopback 静态服务，源码和 wheel 安装均可启动 |
| 团队后台 / 权限 / 数据库 | 未开始 | 不进入本地 Viewer 的第一阶段 |
| v4 兼容与迁移 | v4.0 | 公共 API、Trace/Session/Contract/Report 检查与显式 Trace 迁移 |
| 真实框架兼容 | v4.1 | PydanticAI、OpenAI Agents、LangGraph 的统一 Trace 与正反例 CI |
| 真实供应商检查 | v4.2 | 低成本 DeepSeek 工具 Agent、密钥边界与每周定时门禁 |
| 多工具依赖传递 | v4.3 | 强制工具序列、跨步骤参数关联、真实在线正例与错误参数反例 |
| 发布可信度与治理 | v4.4 | 校验和、SPDX SBOM、签名证明、安全披露、Issue 模板与依赖更新 |
| 业务回归案例与跨步骤契约 | v4.5 | 退款案例、结构化业务关系、错误注入、可定位报告与 CI 验收 |
| 路径变化与误报控制 | v4.6 | 显式严格/有序子序列/无序子集匹配、额外查询案例与 fail-closed CI |
| 额外调用边界 | v4.7 | tolerant path 的 `extra_calls` 白名单、空白名单拒绝全部额外调用、`extra_tool_call` 诊断与发布验收 |
| 工具调用次数边界 | v4.8 | `tool_limits` 最小/最大次数、参数范围计数、`tool_count` 诊断与重复退款验收 |

## 迭代顺序

### v3.2：可安装、可查看、可配置

- [x] Viewer 静态页面：Trace 时间线、Diff 明细、配置生成。
- [x] `agent-regression ui` 统一启动入口。
- [x] Viewer 资产进入 source distribution 和 wheel data files。
- [x] 显式目录错误、loopback 默认和 CLI 帮助。
- [x] Viewer 静态检查、CLI 测试和全新 wheel 安装验证。
- [x] 将 Viewer 的本地文件选择与项目输出目录做更清晰的向导连接。

### v3.2.0–v3.2.2：真实框架接入质量

- [x] 提供一个不强绑定第三方依赖的完整 callback 示例。
- [x] 提供一个可选 LangChain Core 示例，并明确第三方依赖和 Python 版本边界。
- [x] 用 Python 3.9、3.11、3.13 的 GitHub matrix 持续验证该可选接入。
- [x] 增加 adapter contract test 的失败诊断和版本兼容检查。
- [x] 固化公共导出列表、弃用策略和 Trace schema compatibility tests。
- [x] 增加项目级 `check` 命令，一次执行 config、Trace 和批量输入预检。

### v3.3：团队 CI 体验

- [x] 为 compare、stability、coverage、history 统一报告目录和 Job Summary。
- [x] 增加失败报告索引和基于相对路径的批量 Viewer 入口。
- [x] 增加 release workflow：测试、构建 wheel、检查 manifest、生成 changelog。
- [x] 对 MCP 官方 Server 和目标框架建立定期兼容性矩阵。

### v3.4：统一报告交接

- [x] 提供可复用的 `agent-report-index` GitHub Action。
- [x] coverage Action 输出 JSON，可与 compare 报告进入同一索引。
- [x] 生成项目模板和双语文档中的统一报告目录示例。

### v3.5：可信业务门禁

- [x] Contract 支持 required claims，防止候选 Trace 通过“少报结论”。
- [x] Report Index 支持 required report/glob，防止报告生成步骤静默缺失。
- [x] 比较 Action 支持直接读取项目 config/contract，同时保留旧输入。
- [x] 主 CI 使用真实策略和报告完整性检查，覆盖参数错误、结果误读和缺失报告。

### v3.6：可控工具重放

- [x] 将已审核 Trace 转换为严格顺序的工具 cassette。
- [x] 允许 Agent 代码在不触碰真实工具的情况下重跑并验证参数。
- [x] 对多余调用、漏调用、工具名/参数不匹配输出结构化失败原因。
- [x] 保留 `replay` 的“只读查看证据”语义，避免命令含义混淆。

### v3.7：合法路径与结果关联

- [x] 让路径规则可以约束工具结果和错误状态，而不只是工具名称。
- [x] 以 call_id 关联结果，降低并发/事件到达顺序造成的误报。
- [x] 增加分支覆盖和替代路径的最小充分断言示例。

### v3.8：真实框架事件接入

- [x] 提供框架回调事件到 Trace 的统一事件接收器。
- [x] 用真实 LangChain Core 示例验证工具调用、结果和最终 claims 的关联。
- [x] 保持第三方依赖可选，并为每个适配器提供 contract diagnostics。

### v3.9：本地工作台与基线审核

- [x] Viewer 支持从一个工作区入口查看策略、Trace、差异和报告完整性。
- [x] 增加只读 review 流程；baseline 接受必须由命令/API 显式触发。
- [x] 为报告、策略和 Trace 增加可追溯的 manifest 与脱敏摘要。

### v4.0：稳定兼容契约

- [x] 发布稳定的 v4 public API、迁移检查和弃用策略。
- [x] 固化 Trace/Contract/Report 的兼容边界与安装级验收。
- [x] 完成全量离线夹具、框架示例、CI、wheel 安装和安全门禁。
- [x] 保持服务化层为独立评估项，不让后台需求污染本地/CI 核心：
  - 报告持久化和检索；
  - 项目、用户、权限和审计；
  - Webhook、远程 Runner 和通知；
  - 多租户隔离和服务端密钥管理。

这些能力属于平台层，不应该反过来污染核心 Trace、Adapter 和 Compare API；
v4.0 本身仍以本地/CI 核心为主，不以“有后台”作为成熟的必要条件。

### v4.5：业务回归案例与跨步骤契约

- [x] 增加 `contract.relations`，检查跨工具调用、工具结果和状态之间的字段关系。
- [x] 提供订单退款完整案例、审核后的正常 baseline 和可复制的 compare 配置。
- [x] 注入错订单、超额金额、跳过资格检查和重复退款四类业务错误，并让 CI 阻断。
- [x] 把失败类别、路径、实际值和规则解释写入报告。
- [x] 补充双语案例说明、业务契约文档和 v4.5 验收说明。

v4.5 的目标是证明用户可以发现有意义的业务回归；它不把确定性案例结果扩大成
所有模型或生产系统的可靠性承诺。

### v4.6：路径变化与误报控制

- [x] 保持未配置模式时的 `exact` 严格路径行为，确保旧 Contract 不改变含义。
- [x] 增加 `ordered_subsequence`，允许额外查询但要求关键步骤保持顺序。
- [x] 增加 `unordered_subset`，只在业务明确允许时放宽关键步骤顺序。
- [x] 保留 `must_not_call`、`max_steps`、结果约束和业务 Contract，避免“允许额外查询”变成全量放行。
- [x] 提供路径变化双语案例、反例报告、专用 CI 和 v4.6 验收说明。

v4.6 解决的是路径兼容性，不是把比较器变成模糊匹配器。下一阶段应继续把路径
策略与资源/权限分类、批量场景和真实框架运行证据结合起来，而不是默认扩大放行范围。

### v4.7：额外调用白名单与 fail-closed 诊断

- [x] 为 `ordered_subsequence` 和 `unordered_subset` 增加可选 `path_rules.extra_calls`。
- [x] 保持省略 `extra_calls` 时的 v4.6 兼容行为，并支持 `extra_calls: []` 明确拒绝全部额外调用。
- [x] 支持按工具、参数、结果和 `is_error` 约束允许的额外调用。
- [x] 为未知额外调用输出 `extra_tool_call`，同时保留整体路径失败，避免误报难以定位。
- [x] 增加双语验收文档、路径变化案例、配置校验测试、完整测试和发布包文档检查。

v4.7 解决的是“允许合法额外查询”和“拒绝未知行为”之间的边界问题。它不把额外
调用自动视为安全，也不替代 `must_not_call`、权限系统或业务副作用检查。

### v4.8：工具调用次数与重复副作用控制

- [x] 增加 `tool_limits`，支持单个工具的 `min_calls`、`max_calls` 和精确次数。
- [x] 支持按 `arguments` 精确匹配后再统计调用次数，避免把不同业务对象混在一起。
- [x] 失败报告输出 `tool_count`、规则路径、配置边界和实际次数。
- [x] 在退款案例中把重复退款同时交给次数、路径和全局步骤上限阻断。
- [x] 增加双语验收文档、升级说明、API/技术文档和发布包检查。

v4.8 解决的是“工具调用了多少次”这一类传统接口回放容易忽略的 Agent 风险。它
仍然只证明 Trace 中可观察到的调用次数，不等于权限校验、幂等实现或真实事务成功。

## 有意不做的事情

- 不把 Agent 框架自动发现当作核心承诺；
- 不用 LLM Judge 替代结构化 claims 和确定性契约；
- 不在 CI 中自动接受 candidate 为 baseline；
- 不让本地 Viewer 直接执行生产 Agent；
- 不为了“看起来成熟”提前引入数据库、账号和复杂部署系统。

## 每个版本的发布门禁

```text
单元/集成测试通过
    ↓
源码 compileall + wheel 构建
    ↓
全新虚拟环境安装并执行 CLI
    ↓
离线 Fixture：record / compare / contract / report
    ↓
Viewer 静态链接与脚本检查
    ↓
MCP 兼容性 smoke test（可选手动工作流）
    ↓
CHANGELOG + README + 双语接入文档
    ↓
Git commit + annotated tag + push
```
