# Performance baseline / 性能基线

## Purpose

The performance command measures the framework boundary, not an LLM or an
external MCP server. It generates valid deterministic `AgentTrace` objects,
validates them and compares identical baseline/candidate evidence. This keeps
the number reproducible and prevents network/model latency from being mixed
into a release decision.

性能命令测量的是框架本身，不是模型或外部 MCP 服务。它生成确定性的合法
`AgentTrace`，执行校验并比较相同的 baseline/candidate 证据，因此不会把网络、模型
延迟混入发布门禁。

## Workloads

| Workload | Default | Shape | Purpose |
| --- | ---: | --- | --- |
| `small` | 10,000 traces | 2 tool calls, 5 events | startup and high-volume throughput |
| `medium` | 1,000 traces | 10 tool calls, 21 events | multi-step validation and comparison |

The generator is in `src/agent_regression/performance.py`. It has no third-
party runtime dependency and never reads credentials.

## Run

```bash
agent-regression performance run --out work/performance-baseline.json
# after reviewing a stable run, commit it as the comparison reference
mkdir -p performance
cp work/performance-baseline.json performance/reference.json
```

For a pull-request smoke check:

```bash
agent-regression performance run \
  --small-count 100 \
  --medium-count 20 \
  --medium-tool-calls 10 \
  --out work/performance-smoke.json
```

The report records elapsed seconds, traces per second, Python version, OS,
machine, CPU count and peak RSS when the host exposes it. Results are
hardware- and interpreter-dependent; compare like-for-like environments.

## Gate against a stored baseline

```bash
agent-regression performance gate \
  --current work/performance-baseline.json \
  --baseline performance/reference.json \
  --out work/performance-gate.json
```

The default policy reports a warning above 20% elapsed-time regression and
blocks above 40%. A warning keeps `passed=true`; a block returns exit code 1.
Missing workloads and malformed timing fields fail closed. The current release
does not claim a universal SLA or compare results from unrelated hardware.

## CI policy

`.github/workflows/performance.yml` runs a small smoke workload on pull
requests and a full workload weekly or manually. The artifact is evidence for
release review, not a replacement for application-level latency tests.

## 名词解释

- **吞吐（throughput）**：单位时间完成的 Trace 数，不代表模型每秒输出 token。
- **峰值 RSS**：进程曾占用的最大常驻内存；不同操作系统的统计口径可能不同。
- **性能回退（regression）**：相对同一机器、同一 Python 版本的历史基线变慢或变大。
- **smoke**：小规模快速检查，用来发现明显错误；不能替代完整基线。
