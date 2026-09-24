# 能力等级评估与下一轮技术方案：让问题关闭有可复核证据

日期：2026-09-23。状态：P0/P1 本地实现与验收完成；P2 完成自身适配器历史复现。最终验证见 [v4.40 验收](v4.40-acceptance.md)，线上发布状态以该记录为准。

实施调整：v4.39 从未发布，P0 与 P1 代码已经共同接入同一证据闭环，因此合并为 v4.40.0 交付，不发布缺少严格关闭约束的中间包。下文能力评估保留方案制定时的快照；最终结果以本轮验收记录为准。P2 使用自身适配器的真实历史缺陷演练，不计为独立业务采用。

评估对象：当前本地工作树，包括尚未发布的 v4.39 用例生命周期代码。依据为当前源码、工作流和本地验收文档；本次未重新运行完整测试，也未查询远程发布状态。323 项通过与安装验证属于上一轮记录，不代表下列新增验收已通过。

## 1. 当前能力等级

按此前讨论的 L0–L3 自查表，我的判断是：**回归测试核心具备 L2 能力；问题到修复的完整闭环处于 L1 向 L2 过渡；尚不满足整套体系 L3。** 这是项目内部评估，不是外部认证，也不折算为百分比。软件版本 v4.x 与能力等级没有对应关系。

| 维度 | 当前判断 | 现有依据 | 下一步缺口 |
| --- | --- | --- | --- |
| 观测 | L2，限定已接入场景 | 结构化 Trace、工具边界事件、结果与 claims、框架转换器 | 运行来源、输入/环境与版本绑定仍需增强；不能保证所有 Agent 完整采集 |
| 评测集 | L1，已有部分 L2 结构 | 固定样例、用例 revision、tags、正反例审核和显式 suite | 标签并不等于经业务审核的黄金集/错题集；缺持续回流与集合治理证据 |
| 评测标准 | L1，已有确定性规则基础 | Contract、证据前提、审核说明、正常通过/已知错误失败 | 未验证多人标注一致性；一组正反例不能证明规则泛化 |
| 回测门禁 | L2，已有部分 L3 机制 | 自动比较、退出码、现有 CI 示例；新增 case workflow | 新工作流尚无托管执行证据；工作流失败不等于仓库已配置必需检查阻止合并 |
| 在线评测 | L0，未验证 | 当前主要比较已录制证据 | 无真实在线抽样巡检、A/B 或影子验证 |
| 在线监控 | L0，未验证 | 有离线历史/统计能力 | 未接入持续生产流量；离线趋势不能算在线监控 |
| Case 挖掘 | L1 | 手工导入失败报告，保留来源类别 | 来源枚举不代表四类来源都已接入；缺去重、分诊和持续业务回流 |
| 归因 | L1 | 结构化差异、规则命中、工具/参数/结果定位 | 差异定位不能自动证明根因；缺审核过的原因与修复证据关联 |

框架的直接价值是：把 Agent 的执行行为和明确业务约束变成可重复的回归检查，并保留判断依据。适合本地开发和团队试点。完整业务运营体系还需要使用方提供真实场景、预期答案、采集与审核流程；不应为了“凑齐 L3”把这些都做成框架内部平台。

## 2. 本次复查发现的具体缺口

此前“v4.39 功能已完成”的表述应限定为导入、草稿、审核和证据比较主路径完成。它不能代表上一轮方案中的所有闭环约束都已实现。

| 发现 | 代码依据 | 实际影响 | 优先级 |
| --- | --- | --- | --- |
| 问题关闭校验较弱 | `incidents.py` 的 `Incident.validate` 只要求 resolved 时 resolution 为对象；CLI 只有 incident import | `{}` 也符合这一层检查，不能证明同一规则下失败已经恢复 | P0 |
| 审核历史证据未完整复核 | `approve_case` 写入 validation_runs；`cases.py` 的 validate_case 验证主要输入及定义哈希，但未逐一复核审核样本/报告引用 | 审核记录中的样本被删除或替换后，不能保证门禁使用时发现历史证据失效 | P0 |
| Agent 版本是声明 | `_case_run` 接受 CLI agent_revision 或 candidate.agent.version | 手工填版本号不能证明该版本刚刚实际运行，更不能证明修复 | P1 |
| CaseRun 时间不是执行耗时 | `_case_run` 比较结束后给 started_at/finished_at 相同时间 | 不能用它评价 Agent 运行耗时或本次比较耗时 | P1 |
| 关联不完整 | case.incident_refs 与 incident.case_refs 是 ID 列表；草稿路径写入前者 | 尚无完整关系验证和可审计关闭操作 | P1 |
| 证据不足时提前返回 | `_compare` 在发现 evidence_gaps 时生成空 differences | 不会误判通过，但可能掩盖同时存在的明确违规，降低定位效率 | P1 |
| 新 CI 演练覆盖不足 | case-lifecycle.yml 只在 push/手动触发，演练重点为 misread-result | 需要 PR 触发、五类错误及允许噪音的完整验证 | P1 |

以上是本次静态检查结论。实施前应为 P0 项添加能够复现缺口的测试，先确认失败，再实现修复。已有 323 个测试通过与这些缺口可以同时成立。

## 3. 下一轮目标与范围

目标：对一个问题，能够回答“来自哪次失败、由谁审核了哪版规则、什么运行证明恢复、原错误是否仍会被拦截”，并生成可独立复核的交付目录。

继续复用 JSON、Git 审查、现有比较引擎和 CLI。首轮仍只处理单次 Trace。执行 Agent 的脚本由业务项目维护；框架提供记录与校验 API。保留核心无必需第三方运行时依赖。

本轮不扩展多租户管理后台、通用任务调度器、自动修改 Agent、LLM 根因判断或在线流量代理。Session 用例和观测平台适配在本轮达标后按需求选择。

建议版本安排：先将下述 P0 与 v4.39 发布验收补齐；再交付 v4.40 的运行记录及问题关闭能力。两个交付点各自形成可复现验收，不按文件数量拆版本。

## 4. 目标操作过程

以现有 HelpPilot 退款流程为固定技术演练：

1. 业务脚本运行错误变体，保存实际 Trace 与失败报告；导入 source_kind=injected 的 Incident。
2. 从问题生成 Case 草稿，审核人明确预期；同一规则要求正常样本通过、错误样本失败。
3. 审核后保存用例执行定义、样本和报告的内容指纹。
4. 重新运行正常变体，由记录器保存本次执行信息和 Trace 的关联。
5. 同一 case_id、revision、definition_sha256 下，旧错误得到 fail，新运行得到 pass。
6. 审核人填写恢复说明并请求关闭；框架校验完整证据链，生成不可覆盖的关闭记录。
7. CI 对之后的新运行继续执行该 Case；旧错误作为门禁自检样本保留。

切换注入模式只证明演练恢复。真实缺陷修复必须有对应历史问题和实际改动依据；报告分别显示“注入演练已恢复”和“历史问题已验证修复”。

## 5. 数据设计

### 5.1 术语

Trace 是一次 Agent 的实际运行证据；Case 是规则与基线的版本化定义；CaseRun 是一次比较结果。ExecutionRecord 是本轮拟新增的实际执行记录；IncidentResolution 是本轮拟新增的问题关闭记录。SHA-256 是内容指纹，只能检测内容不一致，不能认证是谁运行或是谁批准。

### 5.2 审核证据约束

approved Case 必须包含一份正例和一份反例审核记录，分别满足 pass 和 fail。每条记录必须关联可解析的 Trace、报告、run_id 和 SHA-256；报告中的候选 ID 必须匹配 Trace。

`validate_case(require_approved=True)` 递归复核这些引用，而非只检查 review 字段非空。固定规则下重算审核样本，确认保存的结果仍成立；批量运行可按内容哈希在单进程内缓存验证，不能按文件名缓存。

Case 的定义指纹覆盖规则、基线、输入、环境和证据前提。审核证据的完整性单独验证，避免 review 与自身哈希递归。修改正反例需要重新审核；不能直接修补旧审核。

### 5.3 ExecutionRecord v0.1

建议字段：execution_id、trace_ref、trace_run_id、agent_revision、dirty、input_sha256、environment_sha256、recorder_version、started_at、finished_at、producer、provenance_level。

- trace_ref 使用 bundle 相对路径和 SHA-256，记录 Trace 实际产出后的内容。
- agent_revision 表示业务代码提交；dirty 表示存在未提交变动。不存在 Git 信息时明确 unknown。
- environment_sha256 来自经过脱敏的环境清单，例如依赖锁文件、fixture 版本、模型 ID 和工具版本；不能哈希或保存凭证内容。
- producer 可保存 CI run ID、job ID、仓库和 commit 等关联信息。
- provenance_level 区分 declared（调用方声明）和 ci_correlated（与 CI 元数据及产物关联）。本轮不提供密码学来源证明，两者均不保证抵抗恶意伪造。

记录器 API 包裹业务现有调用，真实记录开始/结束时间，并在 Trace 成功写出后生成 ExecutionRecord；不接受“对旧 Trace 补个当前时间就证明新运行”的流程。外部导入的旧记录可以标记 declared，用于比较，但不能在严格关闭模式下证明重新执行。

允许相同代码提交重新运行后通过，例如外部依赖恢复；仍需新 execution_id、独立候选产物和恢复原因。输入/环境变化需显式说明；若改变了用例固定前提，应建新 revision，不能混作同一条件下修复。

### 5.4 IncidentResolution v0.1

建议字段：resolution_id、incident_ref、case_ref、case_id、case_revision、definition_sha256、before_run_ref、after_run_ref、after_execution_ref、resolution_kind、reviewer、reviewed_at、reason、change_ref。

resolution_kind 首轮只支持 injected_recovery 和 bug_fix。记录文件使用相对引用及哈希，生成后拒绝覆盖。问题 ID 与用例关联也要可解析；仅有 ID 的旧数据通过显式升级补齐位置。

关闭条件全部满足才成功：

- 问题已经分诊并关联 approved Case；所有必要引用通过结构和哈希检查。
- before 与 after 属于同一 Case revision 和定义指纹；before=fail、after=pass。
- before 的失败来源与 Incident 导入证据有明确关系；不能拿无关错误关闭当前问题。
- before/after 的比较结果由现有引擎复核，不能相信手写 outcome。
- after 候选关联新的 ExecutionRecord；重复旧失败执行或缺来源不能关闭。
- 审核理由非空；注入来源必须显示为演练恢复。bug_fix 需历史问题和改动引用，并保留人工责任。

新 API 的 resolved 状态由有效 Resolution 推导。不要同时原子更新两个 JSON 文件；先写不可变 Resolution，再由查询/报告计算状态。旧 Incident 的 status 和 case_refs 在升级前仅为历史声明，不作为“已修复”的证明。

### 5.5 兼容策略

保留现有 Trace 与 compare/session-compare 语义。Incident/CaseRun 新增来源和关闭约束使用对象 schema 0.2 或独立记录 schema 0.1，具体由字段兼容性决定；包版本与对象版本独立。

读取旧 0.1 数据继续允许普通证据比较；缺审核凭据或执行来源的数据不能自动获得新严格门禁/关闭资格。提供显式 upgrade 命令，生成新文件并列出缺失项；无法补齐时要求重新审核或重新运行，不能制造历史证据。

## 6. API、CLI 与模块边界

以下为拟议接口，尚未实现。具体参数在实现阶段冻结后更新双语指南。

| 模块 | 责任 |
| --- | --- |
| cases.py | 审核样本和引用校验、旧定义升级；保留现有业务规则解释 |
| execution_records.py（新增） | 执行记录器、来源声明与一致性校验；不解释 Contract |
| incident_resolution.py（新增） | 校验前后 CaseRun 与问题关联、生成关闭记录、推导问题状态 |
| case_runner.py | 引用 ExecutionRecord、真实比较起止时间、保留证据不足时可安全判定的差异 |
| incidents.py | 导入及来源校验；结构校验不得把空 resolution 当成有效关闭 |
| cli.py | 参数与退出码转换，核心规则留在业务模块 |
| reports.py 或现有 CaseRun renderer | 展示问题、规则、前后证据及缺口；不重新做判定 |
| schema/、tests/ | 新记录格式、兼容与失败场景测试 |

拟议命令示例：

```bash
agent-regression incident validate --root bundle --incident incidents/refund.json
agent-regression case validate --root bundle --case cases/refund.json --review-evidence
agent-regression case compare --root bundle --case cases/refund.json \
  --candidate work/new.trace.json --execution work/new.execution.json --out work/after.case-run.json
agent-regression incident resolve --root bundle --incident incidents/refund.json \
  --case cases/refund.json --before work/before.case-run.json --after work/after.case-run.json \
  --kind injected_recovery --reviewer antao --reason "同一规则下恢复正常退款回复" \
  --out resolutions/refund.json
agent-regression incident report --root bundle --incident incidents/refund.json \
  --resolution resolutions/refund.json --format markdown
```

比较退出码继续 0=pass、1=fail、2=inconclusive/error。关闭操作成功为 0，不满足关闭约束或输入无效为 2；拒绝关闭不等于 Agent 新发生业务回归。CLI 错误需指向具体缺失或冲突引用。

证据不足且同时存在明确违规时，报告分别保留 evidence_gaps 与可安全验证的 violations；整体按既有约定返回 inconclusive/2。不能将缺失采集字段转换成虚构的业务失败，也不能隐藏已确认的问题。

## 7. 存储与一致性

继续使用 bundle 目录：incidents/、cases/、executions/、runs/、resolutions/，每个引用均为根目录内的相对路径和内容哈希。

生成结果采用临时文件与原子发布，默认拒绝覆盖；审核操作涉及多个文件时先在临时目录生成完整产物，全部成功再发布。故障后可安全重试，不能留下半份审核记录导致后续永远失败。

问题关联查询从 Case/Resolution 推导，避免 Incident 与 Case 双向字段产生不同步的第二份事实。未来可加可重建索引；当前不新增数据库。默认单写入者，Git 负责团队合并；并发写入明确拒绝或检测冲突。

## 8. 验收矩阵

| 场景 | 必须结果 |
| --- | --- |
| resolved 配空对象 | 严格校验拒绝，不报告已修复 |
| 审核样本/报告缺失、哈希变化、run_id 不匹配 | 门禁校验失败并定位文件 |
| 删除 review.validation_runs 或伪造 outcome | 严格门禁拒绝；不能靠手填 approved 绕过 |
| 正常样本/五类 HelpPilot 错误 | 同一 Case 下正常 0，各错误 1；记录命中规则 |
| 合法措辞与动态噪音变化 | 配置允许后通过；订单号错误仍失败 |
| 重用旧运行、不同 Case revision、换规则后关闭 | 拒绝关闭并说明不一致 |
| 新运行通过且同一规则下旧错误失败 | 生成可复核 Resolution，状态可推导为 resolved |
| 缺执行来源但候选通过 | 普通比较可通过，严格关闭失败 |
| 证据不足且有明确违规 | 返回 2，并保留安全可判定的违规和证据缺口 |
| 关闭后修改候选/策略/Resolution 引用 | 再校验失败；不继续展示“有效关闭” |
| 审核中途写文件失败后重试 | 无部分批准状态，可恢复或明确冲突 |
| 旧 0.1 对象 | 普通兼容路径可读；严格路径提示升级缺项 |
| wheel 独立环境执行完整闭环 | 无源码 PYTHONPATH，完成导入、审核、失败、恢复、关闭 |
| PR CI | 真实新候选、正常/负例断言、artifact 上传均完成 |

CI 的预期负例必须检查退出码确为 1，不能用 `|| true` 吞掉异常。业务候选门禁为 1/2 时工作流失败。区分“验证框架能拦住坏样本的自检”与“检查当前 Agent 是否能合并的门禁”。需要仓库必需检查配置才可宣称自动阻止合并；验收记录应另列配置证据。

## 9. 实施顺序与交付物

### P0：补齐 v4.39 的证据完整性

复现并修复审核历史引用漏检、空关闭记录误认；补充兼容说明与测试。将当前只比较证据的边界写清。对五类负例和噪音例执行新 Case 入口，而非仅复用旧 compare 的验收结果。

交付：缺口复现测试、修复、双语指南和一份准确验收记录。通过后完成 v4.39 版本元数据、构建与发布流程检查；版本发布前应真实运行新 workflow。

### P1：交付 v4.40 运行记录与问题关闭

实现 ExecutionRecord、Resolution、严格校验、兼容升级及报告。记录器先接 HelpPilot 一条路径；用同一规则完成错误和恢复前后关联。新增 CLI 不引入第二套比较引擎。

交付：Schema/API/CLI、HelpPilot 可复现 bundle、独立 wheel 闭环验收、PR CI、中文和英文操作说明。

### P2：完成一条历史缺陷验证

选择一个有公开失败描述、修复前后 commit、可隔离运行且无需生产凭证的外部 Agent 问题。先做复现可行性核查；无法稳定复现则更换对象，不把注入故障改名为历史缺陷。

使用相同输入和规则运行修复前后版本，由人工独立确认预期。维护者确认与使用意愿是另一个证据项；没有确认就写“维护者执行的公开历史复现”，不能称为独立采用。联系维护者或发帖另行安排，不属于本次方案产出动作。

暂无合适外部问题时，可以先选择本框架已有、具备修复前后提交的真实缺陷做工程演练，但要标注为自身项目，不能计入独立 Agent 业务验证。

## 10. 如何判断这轮有价值

先记录当前人工流程，再对同一组场景测量新流程。记录建例主动操作时间、命令数、人工修改字段数、定位失败所需时间、关闭证据是否可独立复核。重复至少三次并保留每次原始数据；小样本用于发现易用性问题，不外推生产收益百分比。

误报是已确认正确的运行被判 fail；漏报是已确认错误的运行被判 pass。inconclusive 单独统计，不悄悄并入准确率。公布每类样本数量及分母、规则变更情况和来源类型，禁止使用同一批调规则样本宣称泛化。

规则调试样本与保留验证样本分开。邀请一位未参与实现的人按文档完成接入并记录卡点；暂时没人参与就保留待验证状态。

下一阶段准入要求：上述关键验收全部通过；有至少一份从失败到关闭的可复核 bundle；旧 CLI 兼容；轮子独立安装闭环完成；线上 CI 运行有证据。真实业务收益和多人标注一致性继续单独跟踪。

## 11. 后续选择

完成本轮后，依据实际需求依次考虑 Session 用例闭环、单一观测源导入、人工审核辅助界面。只有持续产生真实案例，才优先做在线抽样与自动挖掘。现阶段最有价值的升级，是让已有回归结论可追溯、问题关闭可信、别人按文档能复现。
