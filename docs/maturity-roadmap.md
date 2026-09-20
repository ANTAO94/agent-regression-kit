# Agent Regression Kit：成熟框架路线图

v4.12 之后的可执行设计、配置草案、测试矩阵和发布门禁见
[v4.13–v4.25 成熟度提升技术方案](maturity-evolution-plan.zh-CN.md)。

本文档把“成熟”定义成可验收的工程目标，而不是功能数量。当前仓库的
v4.12 核心已经可以作为开发团队的本地/CI Agent 回归测试工具使用；后续版本重点是
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
| 场景工具目录边界 | v4.9 | `tool_allowlist` 工具白名单、空白名单拒绝全部、参数范围匹配、`unauthorized_tool_call` 诊断与兼容验收 |
| 工具参数与资源边界 | v4.10 | `argument_rules`、跨 Trace 字段约束、租户与金额反例 |
| 独立项目量化验证 | v4.11 | τ²-bench 公开零售轨迹、标签隔离、误报/漏报矩阵与专用 CI |
| 状态等价与误报控制 | v4.12 | 显式 outcome/hybrid 契约、替代意图分组、幂等重复边界与 0 误报/0 漏报独立复测 |
| 契约安全加固 | v4.13 | 成功要求、失败尝试上限、未声明状态变化检查和迁移诊断 |
| 留出数据验证 | v4.14 | benchmark manifest、决策/评分隔离、哈希 provenance 和 Wilson 区间；真正外部留出数据仍待补齐 |
| 独立项目接入 | v4.15 | 独立消费仓库、发布包接入和三类真实错误注入 |
| 成熟版门禁 | v4.16 | 首用模板、行动建议、性能基线、独立消费升级和发布验收；真实外部用户访谈仍待补齐 |
| 评测来源完整性 | v4.17 | 结果文件与 source manifest 哈希绑定、失败样本下限和模型级 prospective 评测；未见任务域泛化仍待补齐 |
| 路径噪音与跨域证据 | v4.18 | `path_rules.ignore_argument_paths` 的严格边界、airline 第二任务域和模型级前瞻结果；样本量与真实用户研究仍待补齐 |
| actor-aware 电信跨域适配 | v4.19 | assistant/user 行为边界、有限环境断言、telecom 第三任务域和 prospective 结果；真正未见任务与真实用户研究仍待补齐 |
| 任务级留出代理 | v4.20 | 只按 task ID 哈希分桶、校验任务集合摘要、公开与 prospective holdout CI；仍不是独立来源或通用未见域泛化 |
| 独立来源接入 | v4.21 | AgentDojo 外部消息导入、两种工具调用格式、oracle 隔离、固定来源 hash 和 CI artifact；已由 v4.22 矩阵扩展 |
| 独立来源矩阵 | v4.22 | 四个 AgentDojo suite、五条固定样本、逐样本 Contract/哈希/Trace、汇总 gate；仍不是完整上游重跑或通用泛化 |
| 跨模型攻击矩阵 | v4.23 | 两个模型 pipeline、四条正向对照、四条预期阻断攻击、显式 expected outcome 和 CI artifact；仍不是安全率或通用泛化 |
| Contract 预注册 | v4.24 | 每条 Contract 绑定 canonical JSON SHA-256，manifest 声明先冻结再读 oracle，篡改 fail closed；仍不证明规则完整 |
| 决策重复性 | v4.25 | 固定矩阵重复三次，aggregate/case/Trace hash 稳定并进入 CI；仍不等于在线模型方差或通用可靠性 |

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

### v4.9：场景工具目录与未授权调用诊断

- [x] 增加可选 `tool_allowlist`，让每个场景声明允许调用的完整工具目录。
- [x] 保持省略字段时的旧版本兼容行为，并支持显式 `tool_allowlist: []` 拒绝全部工具。
- [x] 支持字符串工具规则和带 `arguments` 的精确参数规则。
- [x] 为每个未命中的候选调用输出 `unauthorized_tool_call` 与 `tool_calls[index]` 路径。
- [x] 在退款案例、迁移检查、双语手册、API/技术文档、发布包检查和测试中覆盖该边界。

v4.9 解决的是“Agent 是否越过当前场景允许的工具边界”这一类安全与可审核性问题。
它验证运行证据，不替代真实 Tool Gateway 的权限执行；与 `tool_limits`、路径、业务关系
和副作用契约组合后，才能同时覆盖工具范围、次数、顺序和业务结果。

### v4.10：工具参数策略与租户/资源边界

- [x] 增加可选 `argument_rules`，按工具名匹配每一次工具调用。
- [x] 支持固定值、Trace 参考路径、`exists` 和 `absent` 参数规则。
- [x] 为越租户、错误资源、超额金额和危险绕过字段生成 `tool_argument_policy` 诊断。
- [x] 保持省略字段时的 v4.9 兼容行为，不改变 Trace、baseline 和 report schema。
- [x] 在退款业务案例、配置中心、迁移检测、双语手册和发布包检查中覆盖该边界。

v4.10 解决的是“Agent 调用了允许的工具，但参数是否仍在当前业务边界内”。它是
Trace 级行为验证，不替代生产 Tool Gateway 的租户隔离、资源授权、金额限制和幂等执行。
后续版本应继续完善规则组合/继承和安全攻击场景，而不是把参数策略扩展成可执行脚本。

### v4.11：独立项目验证与检测质量量化

- [x] 固定 τ²-bench `v1.0.1`、tag commit、数据文件路径和 SHA-256。
- [x] 将上游半双工零售轨迹转换成合法 AgentTrace，不把 reward 写入 Trace 或 claims。
- [x] 从上游任务定义生成写操作与沟通要求 Contract，在判断完成后才读取 reward。
- [x] 对 420 条写场景输出正确放行、正确阻断、误报和漏报矩阵。
- [x] 在专用 CI 中下载并校验上游文件，执行质量阈值门禁并上传完整报告和样例 Trace。
- [x] 保留 14 条误报，记录最终状态等价尚未被行为契约完整表达的边界。

v4.11 首次提供第三方项目上的量化证据：准确率 96.67%、失败召回率 100%、误报率
5.24%、漏报 0。它证明当前规则在一份固定公开数据上的表现，不代表 τ²-bench 上游
采用本项目，也不替代真实团队长期接入。下一阶段应利用这些误报设计最终状态等价
契约，并接入另一类独立 Agent 项目验证泛化能力。

### v4.12：状态等价契约与精确动作安全

- [x] 增加 `contract.state_equivalence` 的 `exact`、`outcome` 和 `hybrid` 模式。
- [x] 支持将已声明的替代规则按指定参数分组为同一个业务意图，但仍要求精确命中组内
  工具名和未忽略参数。
- [x] 支持显式允许失败尝试、工具别名和幂等重复；未声明成功写操作继续阻断。
- [x] 支持用 `paths` 比较 baseline/candidate 的最终业务状态，并为缺失或改变状态输出
  `state_equivalence` 差异。
- [x] 为每个安全边界补充正例、错误订单反例、状态变化反例和配置 schema 测试。
- [x] 在同一份固定 τ²-bench 文件上重新验证：267 true pass、153 true block、0 false
  alarm、0 missed failure。

v4.12 的核心不是“把回放改成模糊匹配”，而是把误报归因转化成可审核的领域规则：哪些
参数只是路由选择，哪些参数标识业务资源，哪些失败可以重试，哪些重复是幂等的。等价
关系必须由项目维护者配置并配套负向用例，框架不会从工具名称或模型输出自动推断。

### v4.13：契约安全加固

- [x] 增加显式 `attempt_policy`，让失败尝试不能单独满足要求成功的业务动作。
- [x] 增加失败尝试上限，并输出 `required_success_missing` 与
  `retry_limit_exceeded` 结构化差异。
- [x] 增加 `state_scope`：`declared_only`、`declared_and_unchanged_rest` 和 `full`。
- [x] 对缺失状态证据输出 `state_evidence_missing`，对未声明状态变化输出
  `unexpected_state_change`。
- [x] 保持旧 `allow_failed_expected` 可读取，并在 `config`/`check` 输出迁移诊断，避免
  旧配置被静默改义。
- [x] 配置中心支持新字段；231 项测试和固定 τ²-bench 复测通过。

### v4.14：冻结规则与留出数据验证基础设施

- [x] 增加 benchmark manifest，绑定不可变来源、拆分、证据、Contract、标签和版本哈希。
- [x] 增加 `benchmark prepare`，校验输入文件、样本 ID、Contract 覆盖和 Trace 结构。
- [x] 增加 `benchmark decide`，只读取证据和规则，不读取标签语义。
- [x] 增加 `benchmark score`，校验 decision digest 后再读取标签，输出混淆矩阵和 Wilson 95% 区间。
- [x] unsupported 样本显式进入报告，哈希或样本覆盖异常 fail-closed。
- [x] 明确 τ² 当前结果仍是 calibration 证据，不冒充留出泛化成绩。

### v4.15：独立消费项目接入

- [x] 创建独立仓库 `ANTAO94/agent-regression-pilot`，不复制核心实现，不引用本地源码。
- [x] 只安装 Release wheel，并在消费仓库记录 v4.15.0 URL、SHA-256 和固定提交。
- [x] 接入一个两工具订单 Agent，检查跨步骤 customer ID、业务 claims、禁止工具和步数上限。
- [x] 注入错资源、漏工具、结果误读三类回归；正常场景退出 0，三类错误退出 1。
- [x] 通过消费仓库 GitHub Actions 复核，并记录边界与未覆盖能力。

### v4.16：接入体验与成熟版门禁

- [x] `init` 生成可直接运行的 baseline、candidate、严格 Contract、双语说明和 CI。
- [x] 内置 `normal`、`wrong-resource`、`skip-tool`、`misread-result`，正常退出 0，故意错误退出 1。
- [x] `check` 输出 `guidance`/`next_actions`，提示 Contract、宽松路径和状态证据问题。
- [x] compare JSON/Markdown 输出按差异类别归纳的下一步动作。
- [x] 增加 dependency-free `performance run/gate`、PR smoke 和每周完整基线工作流。
- [x] 独立消费仓库升级到 v4.15.0 wheel 并通过 CI；v4.16 的 clean-room proxy 通过。
- [x] 保留边界：未完成真实外部用户访谈，不宣称托管平台、大规模生产 SLA 或通用框架兼容。

### v4.17：评测来源完整性与 prospective 证据

- [x] 结果文件在生成报告前必须匹配 source manifest 的 SHA-256，错配直接失败。
- [x] 增加 `--min-failures`，避免只有极少失败样本时给出虚高的召回率结论。
- [x] 固定 o4-mini retail 结果 manifest，420 个可判定样本、126 个失败样本通过门禁。
- [x] 把 prospective 评测加入独立 GitHub Actions，并上传完整报告与抽样 Trace。
- [x] 在双语文档中明确模型结果级证据与真正未见任务域泛化的边界。
- [ ] 仍需未参与实现的真实使用者完成 30/60/90 分钟接入记录。

### v4.18：路径噪音与第二任务域

- [x] 增加 `path_rules.ignore_argument_paths`，只忽略 baseline 未声明的路径字段。
- [x] 用正向、错误业务对象和显式字段变化测试证明该配置不会把业务字段变成通配符。
- [x] 增加 τ²-bench airline 的独立导入器、Contract、来源 manifest 和 GitHub Actions。
- [x] 发布 airline 结果：120 个适用场景、69 个失败样本、100% 失败召回、3.92% 误报率。
- [x] 增加 o4-mini airline prospective 结果，并将实测 10.42% 误报率和 12% 观察阈值写入报告。
- [x] 独立消费仓库升级到 v4.18.0 Release wheel，固定发布哈希，正常流程与三类故意回归在远端 CI 通过。
- [ ] airline 适用样本仍低于最终 300 样本门槛；需要更大的独立任务集。
- [ ] 仍需未参与实现的真实使用者完成 30/60/90 分钟接入记录。

### v4.19：actor-aware 电信域与环境证据边界

- [x] 区分 telecom 轨迹中的 assistant-owned Agent 行为和 user-owned 模拟器行为，并在
  Trace metadata 中保留 `requestor`。
- [x] 为 telecom 单独定义写工具、观察工具和 Contract builder；user-owned 动作不能满足
  assistant-owned 业务写操作。
- [x] 增加服务状态、移动数据、测速、MMS、数据加油和欠费账单的有限环境断言解析，并把
  `max_steps` 作为终止差异报告。
- [x] 固定公开和 prospective telecom 结果的来源 URL、tag、commit 与 SHA-256，CI 上传完整
  report 和 sample Trace。
- [x] 记录 364 个可判定样本的 147/217/0/0 calibration 结果，以及 prospective o4-mini
  的 136/216/9/3 观察结果和明确放宽门槛。
- [x] 本地测试达到 248 项，补齐 API、限制、复现和 v4.19 验收文档。
- [ ] 在规则冻结后引入真正未见的 telecom 任务集，并由未参与实现的用户完成接入研究。

### v4.20：task-disjoint holdout 代理

- [x] 增加 `split_tau2_payload_by_task`，仅使用 task ID 的 SHA-256 分桶，不读取 reward 标签。
- [x] 固定 114 个任务的分区摘要：86 个 calibration tasks、28 个 holdout tasks，并在 CI 校验
  全量、calibration 和 holdout 的任务集合哈希。
- [x] 公开 telecom holdout 的 100 个可判定样本得到 47/53/0/0；prospective o4-mini 得到
  50/46/4/0，误报率 7.41%，漏报率 0%。
- [x] 增加独立的 holdout 验证脚本、JSON 报告、sample Trace、CI artifact、双语使用说明和
  v4.20 验收记录。
- [x] 本地测试达到 250 项，v4.20 wheel、干净环境安装和独立消费仓库升级纳入发布门禁。
- [ ] 该 holdout 仍来自同一公开任务族；下一阶段必须引入真正独立来源或任务族，并完成
  未参与实现用户的 30/60/90 分钟接入研究。

### v4.21：独立来源 AgentDojo 接入

- [x] 增加 `trace_from_agentdojo_run`，将 AgentDojo assistant/tool/final-answer 消息转换为
  AgentTrace，兼容字符串函数和对象函数两种导出格式。
- [x] 增加 `evaluate_agentdojo_run`，通过现有 Contract 检查必需/禁止工具；外部
  `utility`/`security` 只进入报告，不写入 Trace，也不参与 Contract 构建。
- [x] 固定 AgentDojo commit、数据路径和结果 SHA-256，加入 source manifest、复现脚本、
  转换 Trace、报告和 `agentdojo-independent-source-smoke` CI artifact。
- [x] 固定样本的 `get_current_day → search_calendar_events` 通过，未调用 `send_email`，
  外部标签为 `utility=true/security=false`；本地测试目标为 257 项。
- [ ] 目前只有一个 suite/task/attack 组合；需要扩展多 suite、多攻击类型和独立审查矩阵，
  仍需未参与实现用户完成 30/60/90 分钟接入研究。

### v4.22：独立来源 AgentDojo 矩阵

- [x] 增加 `agentdojo_matrix_validation.py`，按 matrix manifest 逐样本校验固定 revision、
  结果 SHA-256、suite/task/attack 身份和人工 Contract。
- [x] 固定 workspace、banking、slack、travel 四个 suite 的五条样本，覆盖
  `direct` 和 `ignore_previous` 路径；本地矩阵结果为 5/5 通过。
- [x] 每条样本输出脱敏报告和 Trace，汇总报告输出 `case_count`、逐样本 gate、oracle 隔离检查
  和 aggregate gate；独立 CI 上传全部产物。
- [x] 明确 Contract 与 `utility/security` 外部标签隔离，不用标签反推规则；manifest 自身也
  绑定 revision 和摘要，便于审阅后增删样本。
- [ ] 当前仍是一个固定 upstream revision/model pipeline 的导出结果矩阵，不是完整 AgentDojo
  重跑或安全率；后续仍需更多模型/攻击组合、外部复核和未参与实现用户的 30/60/90 分钟研究。

### v4.23：跨模型攻击矩阵

- [x] 增加 `expected_contract_passed`，让攻击样本可以声明“预期被 Contract 阻断”，并要求
  实际结果与预期一致；这不是把失败当成成功或跳过校验。
- [x] 固定四条 gpt-4o direct 正向对照和四条 gpt-4o-mini `important_instructions` 攻击路径，
  覆盖 workspace、banking、slack、travel 四个 suite。
- [x] 在 CI 下载固定 revision 的八条结果，校验 pipeline metadata、结果哈希、oracle 隔离、
  Trace 边界并上传逐样本报告/Trace artifact。
- [x] 本地验收达到 261 项测试，矩阵 8/8 通过，其中 4 条预期 Contract 阻断。
- [ ] 当前仍是四条攻击样本和两个模型 pipeline 的固定导出结果；下一阶段需要更多独立攻击族、
  预注册 Contract、重复运行方差和未参与实现用户的可用性研究。

### v4.24：Contract 预注册

- [x] 增加 `contract_provenance.frozen_before_oracle=true` manifest 声明和每条 case 的
  `contract_sha256`，摘要排序、紧凑化后的 Contract JSON。
- [x] 在逐样本与 aggregate gate 中记录 Contract provenance；缺失或篡改 Contract 时
  fail closed，并增加对应负向单测。
- [x] 将跨模型攻击矩阵 CI 切换到 v4.24 manifest；本地结果为 8/8 gate、4 条预期阻断、
  8/8 Contract hash 匹配。
- [x] 本地测试达到 263 项，文档、wheel 资源清单和 release 检查同步更新。
- [ ] 预注册证明规则来源可审计，但不替代规则质量审查；仍需更多独立攻击族、重复运行方差
  和未参与实现用户的 30/60/90 分钟可用性研究。

### v4.25：固定输入下的决策重复性

- [x] 增加 `agentdojo_repeatability_validation.py`，对 v4.24 固定矩阵重复执行三次。
- [x] 比较 aggregate report、逐 case report 和 Trace 的 SHA-256；内部 gate 或任一 hash
  变化都会失败。
- [x] 增加 `agentdojo-repeatability` CI job 和上传三次运行 artifact。
- [x] 本地测试达到 265 项，三次均 8/8 matrix gate 且 `stable=true`。
- [ ] 该证据只证明固定导出输入的确定性产物可重复生成；在线模型采样方差、更多独立攻击族
  和未参与实现用户研究仍需单独完成。

v4.13 的目标不是让所有配置自动变严格，而是让“严格程度”成为配置中可读、可审计、可测试
的契约。τ² 适配器对外部 reward 语义做了显式例外，普通业务回归仍使用严格成功默认值。

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
