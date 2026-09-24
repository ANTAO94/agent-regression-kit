# 经过审核的回归用例（开发源码）

本文说明 v4.40.0 源码中的用例闭环，包含此前未发布的 v4.39 工作。这些新命令不属于旧 v4.38.1 安装包；发布验证期间请从当前源码安装。[English guide](case-lifecycle.en.md) 提供同一流程。

## 先理解五个对象

**Incident（问题记录）**保存失败的来源，以及脱敏后的运行记录和比较报告。**EvaluationCase（评测用例）**引用人工认可的正常基线与比较策略；`expected_behavior` 写给审核人看，可执行的业务检查由策略中的 Contract（业务规则）负责。**CaseRun（用例运行结果）**记录一次已审核用例与新候选运行的比较。Trace（运行记录）包含 Agent 的工具调用、结果和最终回答。

这里的执行方式是 `evidence_compare`：先由你的业务脚本运行 Agent 并产生候选 Trace，再交给本工具比较。本工具不会运行未知 shell 命令，也不会自动判断业务正确答案。若候选 Trace 没有声明版本，`agent_revision` 是 `unknown`；只拿旧 Trace 重比一次，不能证明新代码已被执行。

新增 **ExecutionRecord（实际执行记录）**记录一次回调运行的时间、输入/环境摘要、代码版本，以及它产出的 Trace。**IncidentResolution（问题关闭记录）**将原始失败、同一版审核规则、新运行和人工关闭理由串起来。比较通过不自动关闭问题；必须单独通过关闭校验。

## 准备文件

用 `python -m pip install -e .` 从当前源码安装，建一个 bundle 目录。除 `--root` 外，下述路径都必须相对于该目录，禁止绝对路径、`..` 和软链接逃逸。

```text
bundle/
  baseline.trace.json    # 人工确认的正常运行
  policy.json            # 比较规则和 Contract
  failed.trace.json      # 已发生的错误运行
  failed.compare.json    # 原有 compare 命令生成的报告
  normal.trace.json      # 审核用的正常样本
  incident.json
  cases/refund.json
  candidate.trace.json   # CI 中新录制的运行
  suite.json
```

策略示例：

```json
{
  "final_answer_mode": "claims-only",
  "contract": {
    "required_claims": ["final_answer.claims.refund_issued"],
    "assertions": [{"path": "final_answer.claims.refund_issued", "equals": true}]
  },
  "evidence_requirements": [{"path": "metadata.fixture_version", "exists": true, "type": "string"}]
}
```

Contract 约束“明确违反了什么”，违反时可以判失败；`evidence_requirements` 约束“采集的信息是否足以判断”，缺失时返回 `inconclusive`（无法判断）。同一字段不要重复放两处。允许的动态噪音可以使用已有的 `allow_categories`、`allow_paths`、`final_answer_mode` 和 Contract normalizer。旧配置中的 `baseline`、`candidate`、`report` 路径不会控制新用例的输入；用例引用和命令参数负责指定它们。

## 从失败走到审核

先运行自己的 Agent，得到 `failed.trace.json`，再用原有 `agent-regression compare` 生成 `failed.compare.json`。之后执行：

```bash
agent-regression incident import --root bundle \
  --trace failed.trace.json --report failed.compare.json \
  --out incident.json --source-kind injected

agent-regression case draft --root bundle --incident incident.json \
  --baseline baseline.trace.json --policy policy.json \
  --expected-behavior "回复必须与实际退款结果一致" \
  --out cases/refund.json

agent-regression case validate --root bundle --case cases/refund.json

agent-regression case approve --root bundle --case cases/refund.json \
  --positive normal.trace.json --negative failed.trace.json \
  --reviewer antao --reason "错误退款结论必须被拦截"

agent-regression case compare --root bundle --case cases/refund.json \
  --candidate candidate.trace.json --out candidate.case-run.json
```

导入时会脱敏敏感键；还可以重复传 `--secret-value` 指定字面量。若脱敏移除了判断业务所需字段，应人工检查脱敏后的证据并修订规则，不能把缺失默认为通过。审核要求正常样本通过、已知错误样本失败。草稿无法充当 CI 门禁。审核指纹将用例定义与基线、策略以及可选输入/环境文件的 SHA-256 绑定；引用内容变化会使审核失效。使用 `case revise` 创建新草稿版本，不会改写旧的已审核版本：

```bash
agent-regression case revise --root bundle --case cases/refund.json \
  --policy policy-v2.json --out cases/refund-r2.json
```

新版本需重新校验并审核。`--reviewer` 只是本地身份声明，团队审核记录应通过 Git 保留。

门禁还会逐一复核审核正反例的文件、内容指纹、运行 ID 和报告，并用原规则重算。删除审核样本或手改 `outcome` 都不能继续使用该批准。旧用例缺少审核证据时，用 `case upgrade --root bundle --case cases/refund.json --out cases/refund-r2.json` 创建新草稿，再重新审核；升级不会制造历史证据。

`case compare` 会写 `candidate.case-run.json` 和原始比较报告 `candidate.case-run.compare.json`。前者保留报告引用及其 SHA-256、用例版本和候选证据引用；差异与证据缺口保存在后者，批量报告会逐例内嵌比较报告。退出码：`0` 通过，`1` 明确回归，`2` 证据不足或错误；旧命令行为不变。

## 批量接入 CI

`bundle/suite.json` 必须逐例明确指定候选：

```json
{"schema_version":"0.1","cases":[
  {"case":"cases/refund.json","candidate":"candidate.trace.json"}
]}
```

CI 先运行 Agent 录制新 Trace，再执行：

```bash
agent-regression case suite compare --root bundle \
  --manifest suite.json --out suite.report.json
```

报告保留所有用例结果。有 `error` 或 `inconclusive` 时整体返回 `2`；否则只要有 `fail` 就返回 `1`；全通过返回 `0`。空集合、重复 case_id、缺候选和越界路径返回 `2`。CI 应上传候选 Trace 与报告。完整的固定演练见 [HelpPilot workflow](../.github/workflows/case-lifecycle.yml) 和 [独立 Agent 示例](../examples/external-pilot/helppilot/README.md)。

本轮只管理单次 Trace；`kind: session` 会明确拒绝，原有 `session-compare` 仍可单独使用。HelpPilot 的错误是故障注入，不能说成上游真实生产故障。对象格式见 [`schema/`](../schema/)。测试、构建和托管发布状态见 [v4.40 验收记录](v4.40-acceptance.md)。

## 记录一次新执行，而不是给旧文件盖时间戳

在自己的录制脚本中，用 `record_execution` 包住现有的 Agent 调用：

```python
from agent_regression import record_execution

# run_agent 是你的现有函数：执行 Agent 并返回 AgentTrace。
# 必须在该函数内部新建 FrameworkTraceRecorder，采集真实工具结果和回答。
record_execution(
    root="bundle", trace_path="candidate.trace.json",
    out_path="candidate.execution.json", invoke=run_agent,
    agent_revision=git_commit, dirty=False,
    input_data=request, environment={"fixture": "refund-v1"},
)
```

上面是接入片段，不是独立可执行脚本；`run_agent`、`git_commit`、`request` 由业务代码提供。`FrameworkTraceRecorder` 在回调内自动取得执行 ID。手工构造 Trace 的适配器应在回调内读取 `agent_regression.execution_records.current_execution_id()` 并写入 `metadata.execution_id`。回调外提前生成的旧 Trace 会被拒绝。当前接口是同步回调；不能把 coroutine 当作 Trace 返回。

记录器保存脱敏后的 Trace，并绑定输入/环境摘要；不要将密钥放进环境清单。`ExecutionRecord` 的时间是 Agent 回调耗时，`CaseRun` 的时间是比较耗时，两者不能混用。附加执行记录时，CaseRun 使用记录里的代码版本，并检查 Trace 中的 `source_commit` 是否一致。

这些是完整性检查，不是数字签名：恶意调用方仍能伪造回调和文件。默认 `declared` 表示本地声明；提供完整的 CI producer（`runner`、`repository`、`commit`、`job_id`、`run_id`）可标为 `ci_correlated`，仍不代表认证。CI commit 必须对应执行的 Agent 版本，不要把工具包仓库的提交误填成外部 Agent 提交。

## 从失败到关闭

以下假设 `before.case-run.json` 已由原失败 Trace 比较生成，且正反例已经审核：

```bash
agent-regression execution validate --root bundle \
  --record candidate.execution.json --candidate candidate.trace.json --require-recorded
agent-regression case validate --root bundle --case cases/refund.json --review-evidence
agent-regression case compare --root bundle --case cases/refund.json \
  --candidate candidate.trace.json --execution candidate.execution.json --out after.case-run.json
agent-regression incident resolve --root bundle --incident incident.json \
  --case cases/refund.json --before before.case-run.json --after after.case-run.json \
  --kind injected_recovery --reviewer antao --reason "同一规则下新执行已恢复" \
  --out resolutions/refund.json
agent-regression incident report --root bundle --incident incident.json \
  --resolution resolutions/refund.json --format markdown
```

关闭要求原问题确实对应 before，前后 Case ID、revision、定义指纹相同，before 失败、after 通过且通过重新计算复核。after 必须有新的 Trace/run ID 与有效执行记录；没有执行来源的旧候选可以比较，但不能用于严格关闭。固定输入和环境的变化不能冒充同条件修复。

若 before 有执行记录，前后输入与环境摘要都必须存在且相同。若历史失败没有执行记录，Case 必须固定 `input_ref` 和 `environment_ref`，新运行必须匹配它们；报告会明确说明旧运行的实际环境未经独立记录，不能将这一兼容路径当成完整来源证明。

关闭文件拒绝覆盖，不回写原 Incident；展示的 resolved 状态由有效关闭证据推导。移动 bundle 时整体复制，保留相对目录。缺文件、哈希不符、修改规则或伪造报告都会导致再次校验失败。关闭失败退出 `2`，不会写一份“假成功”的记录。

`injected_recovery` 仅用于故障注入演练；`bug_fix` 要求 `historical_bug` 来源及非空 `--change-ref`。改动引用仍需人工审核，框架不会仅凭一个 Git 链接证明因果关系。

## 一次跑通现成的 HelpPilot 示例

先按 [HelpPilot 接入说明](../examples/external-pilot/helppilot/README.md) 准备固定提交的外部项目和 Python 环境，将本工具包装入该环境，然后运行：

```bash
/path/to/helppilot/.venv/bin/python examples/external-pilot/helppilot/run_lifecycle.py \
  --project-dir /path/to/helppilot --root /tmp/my-new-case-bundle
```

根目录必须为空。该脚本执行正常样本、五类错误、新恢复运行、审核、关闭和 suite，自检预期错误必须返回 `1`，不会吞掉程序异常。输出 `verification.json`、`closure.md` 和可重新校验的全部引用文件。不需要模型密钥，不发生实际退款。它使用真实外部 graph，但模型/检索由固定替身控制，因此证明技术集成与规则闭环，不证明线上模型质量或独立用户采用。

suite 中可加入 `"execution":"candidate.execution.json"` 将候选与执行记录绑定。示例工作流是框架自检，不能直接替代你的业务门禁；业务 CI 应先录制当前候选，再运行审核用例，并将非零退出码传给 CI。只有额外配置仓库必需检查，才会阻止不合格 PR 合并。
