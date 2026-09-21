# HelpPilot external validation / HelpPilot 独立项目验证

This example validates the published Agent Regression Kit boundary against the
independent public [poysa213/HelpPilot](https://github.com/poysa213/HelpPilot)
repository. HelpPilot owns the LangGraph graph, SQLite business tools, RAG
boundary and human approval interrupt. This repository owns only the adapter,
the reviewed baseline and the Contract.

这个案例把正式发布的 Agent Regression Kit 接到独立公开项目
[poysa213/HelpPilot](https://github.com/poysa213/HelpPilot)。HelpPilot 自己维护
LangGraph 图、SQLite 业务工具、RAG 边界和人工审批 interrupt；本仓库只维护接入脚本、审核过的
baseline 和 Contract，不复制候选项目实现。

## What is exercised / 验证什么

The pinned scenario is a lost-order refund:

```text
get_order
  → get_tracking
  → check_refund_policy
  → create_refund_draft
  → human approval interrupt
  → issue_refund
  → final reply with citation
```

The adapter runs the external graph with deterministic model and retrieval
substitutes, so no Groq, LangSmith or payment credential is needed. The graph
and its own SQLite tools still execute. Before resume, the adapter asserts that
`issue_refund` has not happened; after a human approval resume, it records the
issued refund and final reply as an `AgentTrace`.

接入脚本使用确定性模型和检索替身运行候选项目，因此不需要 Groq、LangSmith 或支付凭证；但候选项目
自己的 graph、SQLite 工具和审批节点仍然实际执行。恢复前脚本断言没有发生 `issue_refund`，人工批准恢复后
才把退款结果和最终回复记录为 `AgentTrace`。

## Reproduce / 复现

Clone the external project at the pinned revision, install its dependencies,
then run the adapter from the Agent Regression Kit checkout:

```bash
git clone https://github.com/poysa213/HelpPilot.git /tmp/helppilot
git -C /tmp/helppilot checkout 3767824fb90b89a8b19fc4169d912645aaf6fe0b
uv sync --directory /tmp/helppilot

export ARK_ROOT=/path/to/agent-regression-kit
PYTHONPATH="$ARK_ROOT/src" uv run --directory /tmp/helppilot python \
  "$ARK_ROOT/examples/external-pilot/helppilot/record_trace.py" \
  --project-dir /tmp/helppilot \
  --out "$ARK_ROOT/work/helppilot/candidate.trace.json"

agent-regression check \
  --config "$ARK_ROOT/examples/external-pilot/helppilot/compare.config.json"
agent-regression compare \
  --config "$ARK_ROOT/examples/external-pilot/helppilot/compare.config.json"
```

正常运行应返回退出码 `0`。候选项目的 commit 会写入 Trace 的 Agent identity 和 metadata，
因此报告不会把“某次本地运行”误认为任意版本的 HelpPilot。

## Injected regressions / 注入回归

The same external graph can be rerun with controlled defects:

```bash
for mutation in wrong-resource skip-tool misread-result; do
  PYTHONPATH="$ARK_ROOT/src" uv run --directory /tmp/helppilot python \
    "$ARK_ROOT/examples/external-pilot/helppilot/record_trace.py" \
    --project-dir /tmp/helppilot \
    --mutation "$mutation" \
    --out "$ARK_ROOT/work/helppilot/$mutation.trace.json" || true
done
```

| Mutation / 注入 | Expected gate / 预期阻断 |
| --- | --- |
| `wrong-resource` | order argument Contract and refund claim |
| `skip-tool` | missing required `get_tracking` |
| `misread-result` | `order_status=lost` Contract assertion |

These are framework regression cases, not claims about HelpPilot's production
quality. The external repository uses seeded/demo order data; production
credentials, customer data and real money movement are intentionally excluded.

这些是框架回归用例，不是对 HelpPilot 生产质量的结论。候选项目使用 seed/demo 订单数据；生产凭证、客户
隐私和真实资金流转都被明确排除。
