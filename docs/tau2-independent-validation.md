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

### v4.11 实测结果

| 指标 | 结果 | 含义 |
| --- | ---: | --- |
| 上游总轨迹 | 456 | 固定数据文件中的全部运行 |
| 进入契约评估 | 420 | 至少有一个预期写操作 |
| 正确放行 | 253 | 上游通过，Contract 也通过 |
| 正确阻断 | 153 | 上游失败，Contract 也失败 |
| 误报 | 14 | 上游通过，但 Contract 阻断 |
| 漏报 | 0 | 上游失败，但 Contract 放行 |
| 准确率 | 96.67% | `(正确放行 + 正确阻断) / 420` |
| 失败召回率 | 100% | 153 个上游失败全部被发现 |
| 误报率 | 5.24% | 14 / 267 个上游成功运行 |

14 个误报不是隐藏掉的噪音。它们主要说明任务参考写操作并不总是唯一正确路径：有些
Agent 使用不同支付方式、跳过一个上游参考动作，或者执行了最终数据库状态等价的
操作，τ²-bench 因此判定成功，而我们的行为契约仍然认为路径不一致。这是后续状态
等价契约需要解决的真实问题。

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
- 当前适配器覆盖半双工零售轨迹和写操作，不覆盖语音、知识检索、航空与电信域；
- 公开结果来自一个固定模型与历史数据集，不代表所有模型版本；
- reward 是独立 oracle，但任务参考 action 仍可能不是唯一正确实现；
- 结果证明当前规则在这份数据上的表现，不构成生产可靠性保证。

上游代码和数据按 MIT License 发布。固定来源见
[`examples/tau2-retail/source.json`](../examples/tau2-retail/source.json)。

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

The v4.11 run evaluates 420 scenarios containing expected writes. It correctly
accepts 253 upstream passes, correctly blocks all 153 upstream failures, raises
14 false alarms and misses no failures. Accuracy is 96.67%, failure recall is
100%, and the false-alarm rate is 5.24%.

False alarms remain visible because they expose a real boundary: a reference
action list is not always the only path to an equivalent final database state.
State-equivalence contracts are the next improvement suggested by this result.

Run the commands in the Chinese section above or execute the dedicated
`tau2 independent validation` GitHub Actions workflow. The check covers pinned
published half-duplex retail trajectories. It is not evidence of upstream
adoption, voice coverage, every τ²-bench domain, every model, or production
reliability.
