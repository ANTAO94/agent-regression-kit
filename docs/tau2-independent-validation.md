# τ²-bench 独立项目验证 / Independent project validation

## 中文

这项验证使用第三方项目
[`sierra-research/tau2-bench`](https://github.com/sierra-research/tau2-bench)
公开的零售客服 Agent 运行结果。任务、工具、轨迹和最终 reward 都由上游项目维护，
Agent Regression Kit 只负责把轨迹转换成 `AgentTrace`，从任务定义生成确定性契约，
再把契约判断与上游 reward 对照。

### 为什么它是独立证据

- 来源固定为上游 `v1.0.1` 标签与明确的 Git commit；
- 下载的 23 MB JSON 文件必须通过 SHA-256 校验；
- 上游文件包含 456 条由 `gpt-4.1-mini-2025-04-14` 产生的真实工具 Agent 轨迹；
- 我们不控制任务定义、真实工具输出或 τ²-bench 的最终数据库评分；
- reward 不进入 Trace、claims 或 Contract，只在契约判断完成后用于统计混淆矩阵。

最后一点防止“把答案写进待测输入”。如果 reward 提前进入 claims，框架当然可以得到
完美结果，但那不能证明回归检测能力。

### 检查方法

零售任务以最终数据库状态和必须向用户传达的信息作为主要判据。适配器从上游任务
定义中提取写操作，例如退货、换货、修改订单和取消订单；读操作允许变化，失败的
写操作允许重试，成功的额外写操作会被拒绝。对于 `item_ids`，适配器按照上游工具
语义处理无序列表；成对的 `item_ids/new_item_ids` 会一起排序，避免破坏对应关系。

导入器还检查 `communicate_info` 是否出现在 Agent 的任意文本回复中，规则与上游
大小写和逗号归一化逻辑保持一致。当前验证只评估至少包含一个写操作的任务；纯查询
任务没有足够的确定性业务副作用契约，因此被明确排除。

### v4.13 实测结果（v4.14 起标记为 calibration）

| 指标 | 结果 | 含义 |
| --- | ---: | --- |
| 上游总轨迹 | 456 | 固定数据文件中的全部运行 |
| 进入契约评估 | 420 | 至少有一个预期写操作 |
| 正确放行 | 267 | 上游通过，Contract 也通过 |
| 正确阻断 | 153 | 上游失败，Contract 也失败 |
| 误报 | 0 | 上游通过，但 Contract 阻断 |
| 漏报 | 0 | 上游失败，但 Contract 放行 |
| 准确率 | 100% | `(正确放行 + 正确阻断) / 420` |
| 失败精确率 | 100% | 被阻断的 153 条全部是上游失败 |
| 失败召回率 | 100% | 153 个上游失败全部被发现 |
| 误报率 | 0% | 0 / 267 个上游成功运行 |

v4.11 的 14 个误报不是被删除的噪音，而是 v4.12 的设计输入。它们主要说明任务参考写
操作并不总是唯一正确路径：有些 Agent 使用不同支付方式、在失败后选择替代方式、执行
幂等地址更新，或者使用最终状态等价的 pending-order 操作。v4.12 将这些情况分别表达
为“已声明规则的意图分组”“显式允许失败尝试”“显式幂等工具”和“显式工具别名”，而
不是用模糊相似度放宽所有调用。

v4.11 与 v4.12 的对照如下：

| 版本 | 误报 | 漏报 | 主要语义 |
| --- | ---: | ---: | --- |
| v4.11 | 14 | 0 | 参考写操作按严格路径匹配 |
| v4.12 | 0 | 0 | 显式 outcome 分组 + 精确动作安全约束 |

从 v4.14 开始，这份结果在 benchmark 治理中被标记为 `calibration`：历史标签参与过规则
设计，因此不能作为真正留出数据的泛化成绩。正式评测应使用 `benchmark prepare` 固定输入，
先运行 `benchmark decide`，再由独立步骤执行 `benchmark score`。

### 本地复现

```bash
mkdir -p work/tau2
curl --fail --location --retry 3 \
  --output work/tau2/results.json \
  "https://raw.githubusercontent.com/sierra-research/tau2-bench/v1.0.1/data/tau2/results/final/gpt-4.1-mini-2025-04-14_retail_base_gpt-4.1-2025-04-14_4trials.json"

echo "6d6badb43b716adca31591b0b40e15fd493b49adddaa8e2c47035bb557549257  work/tau2/results.json" \
  | shasum -a 256 -c -

python examples/tau2_retail_validation.py \
  --results work/tau2/results.json \
  --out work/tau2/report.json \
  --traces-dir work/tau2/sample-traces
```

命令的默认门禁要求：至少 400 条写场景、失败召回率不低于 99%、误报率不超过
6%、漏报率为 0。原始结果、完整逐条分类和三类样例 Trace 会由 CI 保存为 artifact。

### 边界

- 这是第三方公开轨迹验证，不代表 τ²-bench 维护者采用或认可本项目；
- 当前适配器覆盖半双工零售、航空和电信轨迹的有限业务子集，不覆盖语音、知识检索或
  所有其他任务域；
- 公开结果来自一个固定模型与历史数据集，不代表所有模型版本；
- reward 是独立 oracle，但任务参考 action 仍可能不是唯一正确实现；
- 结果证明当前规则在这份数据上的表现，不构成生产可靠性保证。

上游代码和数据按 MIT License 发布。固定来源见
[`examples/tau2-retail/source.json`](../examples/tau2-retail/source.json)。

### v4.18 航空任务域验证

v4.18 增加了同一上游固定版本中的 airline 任务域。航空域使用独立的写工具集合和
`payment_id` 噪音规则，不复用 retail 的 Contract；任务未声明的 `payment_id` 可以变化，
但任务明确声明的支付 ID 仍然必须匹配。

固定的 `gpt-4.1-mini` 航空结果包含 200 条轨迹，其中 120 条进入写场景评估，69 条上游
oracle 失败。结果为 49 条正确放行、69 条正确阻断、2 条误报、0 条漏报：失败召回率 100%，
误报率 3.92%。这是一条跨任务域迁移证据，说明契约引擎不只适用于零售；但它仍来自同一
τ²-bench 发布版本，不能扩大解释为所有未见任务分布的泛化证明。

对应的前瞻 `o4-mini` 航空结果为 43 条正确放行、72 条正确阻断、5 条误报、0 条漏报，
失败召回率 100%，误报率 10.42%。由于这个模型/任务域组合的实际误报率高于项目通用的 5%
目标，CI 使用显式的 12% 观察阈值，并把该差异写入报告；它不是 5% 通用保证。详见
[`v4.18 验收记录`](v4.18-acceptance.md) 和
[`examples/tau2-airline/README.md`](../examples/tau2-airline/README.md)。

### v4.19 电信任务域验证

v4.19 增加 telecom 任务域。它与 retail/airline 的关键区别是轨迹包含两个行为者：
`assistant` 工具调用是 Agent 路径，`user` 工具调用是模拟器或环境动作。适配器把
assistant-owned 写操作用于 Contract，把 user-owned 结果保留为环境断言证据，避免把
模拟器主动改变的状态错误归因给 Agent。

固定的 `gpt-4.1-mini` 电信结果包含 456 条轨迹，其中 364 条含有至少一个
assistant-owned 写操作，92 条只有 user-owned 动作，因此明确排除。范围内结果为 147 条
正确放行、217 条正确阻断、0 条误报和 0 条漏报。适配器还对服务状态、移动数据、测速、
MMS、数据加油和欠费账单提供有限的环境断言解析。

前瞻 `o4-mini` 电信结果为 136 条正确放行、216 条正确阻断、9 条误报和 3 条漏报，失败
召回率 98.63%、误报率 6.21%、漏报率 1.37%。CI 使用明确的观察阈值：召回率至少 98%、
误报率不超过 10%、漏报率不超过 2%。该阈值只描述这组模型/域结果，不是通用质量承诺。

电信验证的来源、复现命令、Trace 边界和限制见
[`v4.19 验收记录`](v4.19-acceptance.md) 与
[`examples/tau2-telecom/README.md`](../examples/tau2-telecom/README.md)。

## English

This validation consumes published retail Agent results from the independent
[`sierra-research/tau2-bench`](https://github.com/sierra-research/tau2-bench)
project. Upstream owns the tasks, tools, trajectories and final reward. Agent
Regression Kit converts trajectories to `AgentTrace`, derives deterministic
contracts from task definitions, and compares contract decisions with the
upstream reward.

The source is pinned to tag `v1.0.1`, an exact tag commit and a SHA-256 digest.
The 23 MB file contains 456 real tool-Agent trajectories produced by
`gpt-4.1-mini-2025-04-14`. Reward labels are read only after each contract
decision; they are never written into Trace metadata, claims or rules.

The v4.13 run evaluates 420 scenarios containing expected writes. It correctly
accepts 267 upstream passes, correctly blocks all 153 upstream failures, raises
no false alarms and misses no failures. Accuracy, failure precision, failure
recall and the false-alarm rate are all 100%, 100%, 100% and 0% respectively.

The v4.11 false alarms remain useful historical evidence: a reference action
list is not always the only path to an equivalent final database state. v4.12
addresses that boundary with explicit state-equivalence configuration, while
keeping unrelated tools, objects and successful writes fail-closed.

From v4.14, this same-dataset result is labeled `calibration`, not held-out
generalization: its labels informed Contract design. Use the generic
`benchmark prepare`, `benchmark decide` and `benchmark score` workflow when a
separate evaluation set is available.

### v4.17 prospective model evaluation

v4.17 adds a second, checksum-bound result file for the `o4-mini-2025-04-16`
agent. It contains 420 eligible write scenarios and 126 oracle failures. The
contract gate produced 288 true passes, 126 true blocks, 6 false alarms and 0
missed failures: failure recall 100% and false-alarm rate 2.04%.

The validator now compares the bytes passed through `--results` with the
`sha256` in `--source-manifest` before it writes the report. The report records
both the observed result hash and the manifest hash, so using the old default
manifest with the new model file fails closed instead of creating misleading
provenance. The prospective manifest and CI job are
[`examples/tau2-retail/prospective-o4-mini-source.json`](../examples/tau2-retail/prospective-o4-mini-source.json)
and [the independent validation workflow](https://github.com/ANTAO94/agent-regression-kit/actions/workflows/tau2-independent-validation.yml).

This is model-result-level prospective evidence: the task family, task
definitions and upstream reward oracle are shared with the calibration source.
It is not an unseen-domain or independent-task generalization claim.

### v4.18 airline domain validation

v4.18 adds the airline domain from the same pinned tau2-bench release. The
airline adapter has its own write-tool set and treats `payment_id` as ignorable
only when the task does not declare that field. An explicitly declared payment
ID remains an assertion.

The pinned `gpt-4.1-mini` airline result has 200 trajectories and 120 eligible
write scenarios, including 69 oracle failures. It yields 49 true passes, 69
true blocks, 2 false alarms and 0 missed failures: 100% failure recall and a
3.92% false-alarm rate. This is cross-domain transfer evidence, not proof of
generalization to every unseen task distribution.

The prospective `o4-mini` airline result yields 43 true passes, 72 true
blocks, 5 false alarms and 0 missed failures. Its observed false-alarm rate is
10.42%, so CI uses an explicit 12% observation threshold and records that
relaxation. It is not a general 5% guarantee. See the [v4.18 acceptance
record](v4.18-acceptance.md) and the [airline example](../examples/tau2-airline/README.md).

### v4.19 telecom domain validation

v4.19 adds the telecom domain. Telecom trajectories contain two actors:
`assistant` tool calls are the Agent path, while `user` tool calls are simulator
or environment activity. The adapter checks assistant-owned writes in the
Contract and keeps user-owned results as evidence for bounded environment
assertions. This prevents simulator actions from satisfying an Agent action by
accident.

The pinned `gpt-4.1-mini` telecom file has 456 trajectories, 364 eligible
assistant-write scenarios and 92 user-only exclusions. It yields 147 true
passes, 217 true blocks, 0 false alarms and 0 missed failures. The adapter also
supports bounded evidence parsers for service status, mobile data, speed, MMS,
data refueling and overdue bills.

The prospective `o4-mini` telecom file yields 136 true passes, 216 true blocks,
9 false alarms and 3 missed failures: 98.63% failure recall, 6.21%
false-alarm rate and 1.37% missed-failure rate. CI records explicit observation
thresholds of recall >= 98%, false alarms <= 10% and missed failures <= 2%.
These thresholds describe this model/domain result; they are not universal
quality guarantees.

See the [v4.19 acceptance record](v4.19-acceptance.md) and the
[telecom example](../examples/tau2-telecom/README.md) for source manifests,
reproduction commands, actor boundaries and limitations.

Run the commands in the Chinese section above or execute the dedicated
`tau2 independent validation` GitHub Actions workflow. The check covers pinned
published half-duplex retail, airline and telecom trajectories, including the
v4.17 retail, v4.18 airline and v4.19 telecom prospective o4-mini result files.
It is not evidence of upstream adoption, voice coverage, every τ²-bench domain,
every model, or production reliability.
