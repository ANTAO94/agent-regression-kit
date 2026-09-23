# HelpPilot case study / HelpPilot 业务案例

This is a reproducible, maintainer-run integration with the independent public
[HelpPilot](https://github.com/poysa213/HelpPilot) repository at commit
`3767824fb90b89a8b19fc4169d912645aaf6fe0b`. HelpPilot owns the LangGraph
graph, SQLite tools, retrieval and human-approval interrupt. Agent Regression
Kit owns the [recording adapter](../examples/external-pilot/helppilot/record_trace.py),
[reviewed Baseline](../examples/external-pilot/helppilot/baseline.trace.json),
[Contract](../examples/external-pilot/helppilot/compare.config.json) and gate.

这是对独立公开 [HelpPilot](https://github.com/poysa213/HelpPilot) 项目固定 commit
`3767824fb90b89a8b19fc4169d912645aaf6fe0b` 的维护者接入预演。HelpPilot 负责
LangGraph 图、SQLite 工具、检索及人工审批；本项目负责[录制适配器](../examples/external-pilot/helppilot/record_trace.py)、
[审核过的 Baseline](../examples/external-pilot/helppilot/baseline.trace.json)、
[Contract](../examples/external-pilot/helppilot/compare.config.json) 和比较门禁。

## Baseline → Candidate → rule / 基线 → 候选 → 规则

The reviewed Baseline records a lost `ORD-5001` order, tracking and refund-policy
evidence (including the retrieved passage), a `129.99` refund draft, an approval
interrupt, the simulated refund, `send_reply`, and claims parsed from the actual
final reply. A fresh run of the same pinned graph creates the Candidate; the
Contract compares its evidence and business facts with the Baseline. No expected
answer is prewritten into the Candidate.

已审核的 Baseline 记录丢件订单 `ORD-5001`、物流与退款政策证据（含检索正文）、`129.99`
退款草稿、审批 interrupt、模拟退款、`send_reply`，以及从实际最终回复解析的 claims。
同一固定版本图的新运行产生 Candidate，Contract 将其证据和业务事实与 Baseline 比较；
Candidate 不预填预期答案。

| Injected Candidate fault / 注入错误 | Rule that blocks it / 阻断规则 |
| --- | --- |
| Wrong order resource / 错误订单 | `tool_argument_policy` |
| Skip tracking lookup / 跳过物流工具 | `required_tool` |
| Misread lost as another status / 误读丢件状态 | `contract_assertion` |
| Extra CRM write / 额外 CRM 写操作 | `unauthorized_tool_call` |
| Change policy passage but keep its ID / 政策正文变更但 ID 不变 | `tool_result` |

## Reproduce / 复现

From the Agent Regression Kit checkout, with `git`, `uv`, and Python available:
在本项目源码目录中运行，需有 `git`、`uv` 和 Python：

```bash
git clone https://github.com/poysa213/HelpPilot.git /tmp/helppilot
git -C /tmp/helppilot checkout 3767824fb90b89a8b19fc4169d912645aaf6fe0b
uv sync --directory /tmp/helppilot
export ARK_ROOT="$PWD"
PYTHONPATH="$ARK_ROOT/src" uv run --directory /tmp/helppilot python \
  "$ARK_ROOT/examples/external-pilot/helppilot/record_trace.py" \
  --project-dir /tmp/helppilot --out "$ARK_ROOT/work/helppilot/candidate.trace.json"
PYTHONPATH="$ARK_ROOT/src" python3 -m agent_regression compare \
  --config "$ARK_ROOT/examples/external-pilot/helppilot/compare.config.json"
```

The normal comparison exits `0`. The following uses the same graph and expects
exit `1` for each fault; `2` means invalid input or execution error, not a
detected regression. 正常比较应以 `0` 退出；以下每个错误应以 `1` 退出，`2` 表示输入或执行错误，
不能当作检测到回归。

```bash
for mutation in wrong-resource skip-tool misread-result extra-write corrupt-policy; do
  PYTHONPATH="$ARK_ROOT/src" uv run --directory /tmp/helppilot python \
    "$ARK_ROOT/examples/external-pilot/helppilot/record_trace.py" \
    --project-dir /tmp/helppilot --mutation "$mutation" \
    --out "$ARK_ROOT/work/helppilot/$mutation.trace.json"
  code=0
  PYTHONPATH="$ARK_ROOT/src" python3 -m agent_regression compare \
    --config "$ARK_ROOT/examples/external-pilot/helppilot/compare.config.json" \
    --candidate "$ARK_ROOT/work/helppilot/$mutation.trace.json" || code=$?
  test "$code" -eq 1 || exit 1
done
```

The [external workflow](../.github/workflows/helppilot-external-pilot.yml)
builds a wheel, installs it into the pinned HelpPilot environment, checks the
normal result and exact negative difference categories, and uploads traces and
reports. See [v4.38.1 acceptance](v4.38.1-acceptance.md) and the
[detailed adapter README](../examples/external-pilot/helppilot/README.md).

独立 workflow 会构建 wheel、装进固定版本的 HelpPilot 环境，检查正常结果和负向差异类别，
并上传 Trace 与报告。详见 [v4.38.1 验收](v4.38.1-acceptance.md)和
[适配器说明](../examples/external-pilot/helppilot/README.md)。

## Evidence boundary / 证据边界

This uses seeded/demo data, deterministic model/retrieval substitutes and a
scripted reviewer. The upstream refund is simulated. The answer parser supports
this fixture's English reply grammar only; it is not a general factual judge.
Approval ordering is checked by the harness before resume, while the flat Trace
alone does not prove it. Unlogged upstream side effects remain invisible. This
does not demonstrate upstream adoption, online-model quality, production safety,
or real-money handling. The [v4.38.0 historical record](v4.38.0-acceptance.md)
explains why its original green runs did not cover the corrected evidence.

这里使用 seed/demo 数据、确定性模型/检索替身和固定 reviewer；上游退款是模拟操作。
回复解析器仅支持本 fixture 的英文格式，不是通用事实评审。审批先后由恢复前的 harness
检查，平铺 Trace 本身不能证明；上游未记录的副作用仍不可见。此案例不证明上游采用、
在线模型质量、生产安全或真实资金处理。[v4.38.0 历史记录](v4.38.0-acceptance.md)
说明其原有绿色运行为什么没有覆盖修正后的证据。
