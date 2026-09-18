# Agent Regression Kit：成熟框架路线图

本文档把“成熟”定义成可验收的工程目标，而不是功能数量。当前仓库的
v3.4 核心已经可以作为开发团队的 Agent 回归测试工具使用；下一步重点是
继续扩大真实框架覆盖，并在真实团队使用后再评估服务化层。

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
| `agent-regression ui` | v3.2 | loopback 静态服务，源码和 wheel 安装均可启动 |
| 团队后台 / 权限 / 数据库 | 未开始 | 不进入本地 Viewer 的第一阶段 |

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

- [ ] 为 compare、stability、coverage、history 统一报告目录和 Job Summary。
- [x] 增加失败报告索引和基于相对路径的批量 Viewer 入口。
- [x] 增加 release workflow：测试、构建 wheel、检查 manifest、生成 changelog。
- [x] 对 MCP 官方 Server 和目标框架建立定期兼容性矩阵。

### v3.4：统一报告交接

- [x] 提供可复用的 `agent-report-index` GitHub Action。
- [x] coverage Action 输出 JSON，可与 compare 报告进入同一索引。
- [x] 生成项目模板和双语文档中的统一报告目录示例。

### v4.0：可选服务化层

只有在 CLI/Viewer 被真实用户持续使用后才考虑：

- 报告持久化和检索；
- 项目、用户、权限和审计；
- Webhook、远程 Runner 和通知；
- 多租户隔离和服务端密钥管理。

这些能力属于平台层，不应该反过来污染核心 Trace、Adapter 和 Compare API。

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
