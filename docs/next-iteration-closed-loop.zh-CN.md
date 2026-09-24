# 下一轮技术方案：将一次失败沉淀为持续回归用例

日期：2026-09-23。依据：main `da5038f`、发布版 v4.38.1。
状态：方案对应的 v4.39 源码功能已实现；323 项本地测试、sdist/wheel 构建、包内容与干净环境安装复核均通过，详见 [v4.39 验收记录](v4.39-acceptance.md)。GitHub 托管工作流尚未运行，且当前未改版本号、打 tag、推送或发布；正式发布版仍为 v4.38.1。
建议发布窗口：v4.39.0，最终以完整验收结果决定。

## 1. 已走通的链路和证据

现有工程链路是：执行 Agent → 采集 Trace → 与审核基线及 Contract 比较 → 生成报告 → 用退出码接入 CI → 构建发布包并在独立环境安装。

| 证据 | 本轮核对结果 | 能说明什么 |
| --- | --- | --- |
| [main CI](https://github.com/ANTAO94/agent-regression-kit/actions/runs/35813185519) | success，提交 da5038f | 当前主分支已配置的检查通过 |
| [HelpPilot 验证](https://github.com/ANTAO94/agent-regression-kit/actions/runs/35813034848) | success，提交 46e3c9b | 固定公开项目安装 wheel 后，正常和负向流程可复现 |
| [LangGraph 验证](https://github.com/ANTAO94/agent-regression-kit/actions/runs/35813034815) | success，提交 46e3c9b | 已接入的外部 graph 可以采集和比较 |
| [发布流程](https://github.com/ANTAO94/agent-regression-kit/actions/runs/35813034766) | success，提交 46e3c9b | 构建、干净环境安装及发布检查通过 |

[v4.38.1 验收记录](v4.38.1-acceptance.md)记载 Python 3.9/3.11 各 317 项通过；HelpPilot 正常运行退出 0，错误资源、漏工具、结果误读、额外写操作、政策正文变化五类注入均退出 1。本次编写方案核对了远程状态和记录，没有重新跑完整测试。

这验证了固定条件下的技术接入，未证明所有 Agent 的可观测性、线上监控效果、独立团队持续使用或真实生产收益。现有业务规则由维护者提供，公开项目验证仍由维护者执行。

目前缺失的是统一的问题和用例生命周期：失败被记录后，如何审核正确行为、进入用例库、关联修复，并在后续 CI 中持续执行。

## 2. 本轮目标与范围

用户目标：把一份失败报告及对应运行证据，变成经过审核、可重复比较的用例；修复后能明确看到同一规则下从失败到通过的证据。

首轮继续使用 JSON 文件、Git 审查、现有 CLI 和 CI artifact。新增 Incident、EvaluationCase 和 CaseRun 三类对象，复用 AgentTrace、AgentSession、ComparisonPolicy 和 ContractPolicy。

本轮以 trace 用例完成全流程；session 类型预留明确扩展位置但在首轮校验中拒绝，不宣称支持完整会话用例管理。原有 session-compare 继续承担现有多轮比较。线上监控接入、LLM 自动归因、自动派单、多用户后台以及任意命令执行器属于后续需求。

用例执行的第一版入口是“比较已有运行证据”。Agent 仍由业务项目原有脚本执行，CI 显式先录制候选、再比较用例。报告必须写明 evidence_compare；只有候选生产记录提供明确关联时，才能证明它来自指定新版本的实际执行。

## 3. 用 HelpPilot 完成一条可复现闭环

1. 使用已固定的 HelpPilot commit、测试数据及隔离数据库运行正常流程。
2. 用现有 misread-result 注入产生实际错误回复；由实际回复提取 claims，正常与错误运行使用同一份规则。
3. 导入该运行和比较报告，创建 source_kind=injected 的问题，记录所用注入方式。
4. 从问题生成用例草稿，引用已审核的正常 baseline 和现有 Contract，保留 expected_behavior 供人工确认。
5. 执行者确认“实际工具结果和最终回复事实必须一致”，填入 reviewer、理由和审核时间。
6. 同一用例对错误运行返回 1，对恢复正常行为后的新运行返回 0。
7. 在 CI 中重新运行 Agent 后比较该用例；修改无关措辞或允许噪音仍通过，业务事实错误仍失败。
8. 在演练记录中标注：切换注入模式是故障注入演练，不是修复上游真实缺陷；真实历史问题出现后用同一流程验证。

无需新建完整业务 Agent。此演练验证用例管理流程，业务采用验证另行保留状态。

## 4. 数据契约

### Incident：问题记录

字段：schema_version、incident_id、title、source_kind、summary、evidence_refs、reported_at、status、case_refs。

- source_kind：injected、historical_bug、user_feedback、ci_failure；不把不同来源混为真实生产问题。
- evidence_refs：失败 Trace、比较报告、可选正常 baseline 和 policy；每项保存相对路径、角色和 SHA-256。
- status：open、triaged、resolved。生成草稿不会自动把问题标记 resolved。
- resolved 必须有人工判定、修复说明和同一用例版本的前后运行关联。
- 原始失败报告和证据保留；导入时验证报告内运行标识与 Trace 是否相符。无法确认关联则保留为未验证来源，不能自动进入审核通过状态。

### EvaluationCase：用例定义

字段：schema_version、case_id、revision、title、kind、status、tags、input_ref、environment_ref、baseline_ref、policy_ref、expected_behavior、incident_refs、review。

- schema_version 与包版本分别管理，首次为 0.1。
- kind 首期只支持 trace；baseline_ref 和 policy_ref 必填，复用现有比较语义。
- expected_behavior 用自然语言说明业务期望和依据；它帮助审核，不直接代替可执行断言。
- input_ref 与 environment_ref 记录输入、固定数据和依赖版本，支持复现；声明中不能包含生产凭证。
- tags 可同时包含 golden、challenge、regression，不复制同一用例来表示不同集合。
- status：draft → approved → retired。审核前必须验证 baseline/policy 有效、必填证据齐全、正常样本通过、已知错误样本失败。
- review：reviewer、reviewed_at、reason、definition_sha256，以及验证前后运行引用。身份字段是本地声明，Git 审查提供团队审核记录，SHA-256 不等于身份认证。
- definition_sha256 覆盖规范化用例执行定义和其引用内容指纹；不包括 review 自身和运行结果。输入、环境、baseline、policy 或业务期望变动须生成新 revision 并重新审核。
- 对无需 baseline 的纯业务规则用例另行设计，本轮不以伪造 baseline 绕过现有 API。

### CaseRun：一次用例比较结果

字段：schema_version、case_run_id、case_id、case_revision、definition_sha256、execution_mode、candidate_ref、agent_revision、report_ref、outcome、started_at、finished_at。

- execution_mode 首期为 evidence_compare。agent_revision 从候选生产方声明取得；缺失则标为 unknown，不推断已经执行新代码。
- outcome：pass、fail、inconclusive、error。同时保存原始 compare 报告，保持现有报告语义。
- pass：输入及关联有效，且所有规则通过。
- fail：规则检查发现明确违规，包括规则明确要求的字段缺失。
- inconclusive：用例声明的采集前提不满足，无法作出完整判断。
- error：文件损坏、错误配置、执行器异常等。
- 新入口退出码：0=pass；1=fail；2=inconclusive/error。既有 compare/session-compare/batch-compare 的映射保持兼容。
- 批量入口存在 error/inconclusive 时返回 2，否则存在 fail 返回 1；空集合返回 2。逐例报告保留已发现违规，不能因其他用例错误丢失失败信息。

### 证据完整性

新增用例级 evidence_requirements 声明所需输入、版本、状态快照等前提，仅提供存在性和类型约束，避免复制完整 Contract 运算符体系。
同一条件只能有一个负责层：业务字段要求使用 Contract；能否评价的采集前提使用 evidence_requirements。规范中列出冲突诊断，防止把明确业务违规改报为“无法判断”。

## 5. 已新增命令与接口

本轮已在源码中实现以下能力。完整参数、bundle 路径规则和可复制示例见[中文使用指南](case-lifecycle.zh-CN.md)及[英文指南](case-lifecycle.en.md)。命令均需显式提供 `--root`，避免相对路径意外越过证据 bundle。

```bash
# 1. 从失败证据登记问题；初始实现默认以 ci_failure 标记
agent-regression incident import --root bundle --trace work/failed.trace.json \
  --report work/failed.compare.json --out incidents/refund-001.json

# 2. 创建草稿，人工补齐业务期望、输入和环境引用
agent-regression case draft --root bundle --incident incidents/refund-001.json \
  --baseline baselines/refund.trace.json --policy policies/refund.json \
  --expected-behavior "工具结果与回复中的退款结论必须一致" --out cases/refund-001.json

# 3. 校验并用正常/错误样本检查规则有效性后审核
agent-regression case validate --root bundle --case cases/refund-001.json
agent-regression case approve --root bundle --case cases/refund-001.json \
  --positive work/normal.trace.json --negative work/failed.trace.json \
  --reviewer antao --reason "工具结果与退款回复必须一致"

# 4. CI 已通过原有脚本生成新的 candidate 后执行
agent-regression case compare --root bundle --case cases/refund-001.json \
  --candidate work/candidate.trace.json --out work/case-run.json
```

approve 创建新审核记录并检查变动，不隐式修改 baseline。CLI 明确输出审核过的内容指纹。对已有输出文件默认拒绝覆盖，重新审核使用显式 revision。

Python 接口按职责划分：`import_incident`、`create_case_draft`、`validate_case_definition`、`approve_case`、`compare_case`、`compare_case_suite`。比较函数复用 `compare_traces`；新增逻辑负责对象校验、路径、审核状态、证据前提及结果关联。

集合使用一个小型 manifest 明确列出 case 引用和 candidate 对应关系；case_id 不重复，每个必跑用例必须有候选，筛选结果为空失败。不要把不同业务用例的候选按目录排序配对。

## 6. 文件与实现分工

| 文件/模块 | 改动 |
| --- | --- |
| 新 incidents.py | 问题模型、来源及证据导入、状态校验 |
| 新 cases.py | 用例模型、审核指纹、生命周期、路径解析 |
| 新 case_runner.py | 单例/集合比较，复用 compare_traces 和 ComparisonPolicy |
| cli.py | 新子命令注册与退出码；业务逻辑留在上述模块 |
| reports.py | 新增 CaseRun 渲染，展示问题、用例、规则和证据位置 |
| 新 schema/incident-v0.1.schema.json 等 | 三类对象的公开格式，与运行时校验同步 |
| examples/external-pilot/helppilot/ | 增加完整演练入口及脱敏后的输入示例 |
| 新 .github/workflows/case-lifecycle.yml | 正常、注入、审核、候选重跑、比较和 artifact |
| docs 与双语 README | 用一条完整操作路径说明功能与边界 |

路径相对于 bundle 根目录解析，拒绝绝对路径、目录穿越、软链接逃逸和输入输出同路径。审核后校验引用文件指纹；证据变动导致审核失效。写入采用临时文件加原子替换，旧 revision 保留。首期依靠 Git 管理协作冲突；不提供多进程共享数据库承诺。

导入边界统一脱敏，引用路径和报告不暴露凭证。脱敏后的文件重新计算指纹并重新检查规则适用性；必要业务字段被脱敏移除时不得静默通过。未审核的外部文件不能携带并自动执行 shell 命令。

## 7. 实施顺序

1. 演练规格：固定 HelpPilot 场景、同一 baseline/policy 的正常与五类负向证据；记录现有操作耗时和人工步骤。
2. 模型与单例入口：完成三类对象和 case validate/compare；用现有 Trace 验证正常和失败，不增加第二套比较引擎。
3. 草稿和审核：incident import、case draft/approve；实现审核指纹、变更失效、引用校验。
4. CI 与集合：显式候选映射、逐例输出、退出码聚合，以及从问题到修复演练。
5. 交付：公开 API/配置兼容检查、发布包安装演练、中英文文档和验收记录。满足下节条件后发布 v4.39.0。

不把上述内部步骤逐个当成版本发布；本轮以完整用户流程作为交付单位。

## 8. 验收矩阵

| 场景 | 必须结果 |
| --- | --- |
| 正常候选 | approved 用例通过，退出 0 |
| 错误资源、漏工具、结果误读、额外写操作、政策正文变化 | 各失败，退出 1，并指向对应规则和证据 |
| 合法措辞/动态字段变化 | 明确配置允许后通过；错误订单号仍失败 |
| 问题导入与草稿 | 保留来源，草稿不得当作已审核门禁执行 |
| 正确/错误样本均通过的弱规则 | approve 拒绝，提示缺乏有效负例 |
| 正常样本不能通过 | approve 拒绝，人工检查规则或预期 |
| 引用 baseline/policy/输入被修改 | 审核失效，退出 2，要求新 revision 审核 |
| 必要采集前提缺失 | inconclusive，退出 2；不显示通过 |
| 必须的业务字段缺失 | 原 Contract 规则失败，退出 1 |
| 空集合、缺候选、重复 case_id、文件损坏、路径越界 | 明确错误，退出 2 |
| 多轮用例被传入首轮入口 | 明确报不支持，退出 2，不扁平化后静默比较 |
| Agent 声称修复但复用旧候选 | 报告仍标证据重评；缺少新运行关联不能宣称修复完成 |
| 故障恢复演练 | 同一规则/用例版本对错误运行失败、正常新运行通过 |
| 老 CLI、Trace、Contract | 兼容检查保持通过，原退出码不变 |
| 独立环境安装 | 从 wheel 完成导入、草稿、审核和比较；无需源码 PYTHONPATH |

测试覆盖上述实际用户风险；完整源码套件、HelpPilot CI 和打包检查作为发布验收。记录实际测试数量，不能预写预计通过数。

## 9. 价值、成熟度与下一步准入

本轮能证明：问题证据可以沉淀成经过审核的回归用例，且被 CI 持续执行。工程收益通过首次建例耗时、人工步骤、失败报告的可定位性衡量。保留演练前后的实际记录，不预先承诺节约百分比。

现有内核属于工程试点阶段；完成本轮后，可称为“在固定示例中完成问题到回归的技术闭环”。不能因此宣称独立团队采用、业务标准人机一致或线上自进化。

下一阶段根据使用反馈选一个：真实历史问题复现、Session 用例生命周期、现有观测平台的导入适配。首选独立维护者提供的历史问题，并由其确认预期、实际收益和后续保留门禁意愿。没有真实业务时可以继续技术演练，产品价值验证状态单独保留。

若导入成本高于手工写测试、审核者看不懂规则或持续大量误报，则优先降低成本和修正规则，不用继续增加功能掩盖这些问题。
