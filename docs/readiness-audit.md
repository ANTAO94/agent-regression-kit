# Readiness audit / 最终成熟度审计

`agent-regression readiness` turns the maturity plan's final acceptance
conditions into a machine-readable, fail-closed audit. It is a release
readiness report, not a replacement for reviewing the Agent, Contract or
dataset.

`readiness` 把成熟度方案中的最终验收条件变成可机器执行、默认不放宽的审计。它是发布准备度报告，
不是对 Agent、Contract 或数据集进行业务正确性审查的替代品。

## What it checks / 它检查什么

The `final-v4` profile checks these quantitative gates:

| Gate | Default threshold |
| --- | ---: |
| Held-out evaluated samples | at least 300 |
| Held-out failure samples | at least 50 |
| Failure recall | at least 99% |
| False-alarm rate | at most 5% |
| Small-trace performance sample | at least 10,000 traces |
| Small-trace elapsed time | at most 60 seconds |
| Peak RSS | below 512 MiB |

The thresholds can only be made stricter in the `final-v4` profile. A
manifest that tries to lower the sample count or loosen a rate is rejected
before any readiness result is emitted.

The audit also supports two evidence-only kinds:

- `evidence`: verify one or more files and their SHA-256 values;
- `external`: record an independently produced result such as a human
  usability study or a truly unseen-task evaluation. `pending` remains
  pending; it is never silently counted as passed.

`final-v4` 的默认门槛不能被调低：样本不足、失败样本不足或指标不达标时，报告不会给出“成熟度通过”。
真实用户研究和真正未见任务评测属于 `external` evidence；没有独立记录时必须保持 `pending`。

## Manifest / 清单

Paths are relative to the manifest and every referenced file must have the
exact SHA-256 digest. The report contains paths and digests, not the contents
of the evidence files.

路径必须相对于 manifest，所有引用文件都必须给出精确 SHA-256。报告只保存路径和摘要，不复制证据文件内容。

```json
{
  "schema_version": "0.1",
  "profile": "final-v4",
  "target_version": "4.36.1",
  "checks": [
    {
      "id": "heldout-quality",
      "kind": "benchmark",
      "report": {
        "path": "work/heldout-score.json",
        "sha256": "<sha256>"
      }
    },
    {
      "id": "framework-performance",
      "kind": "performance",
      "report": {
        "path": "work/performance.json",
        "sha256": "<sha256>"
      }
    },
    {
      "id": "consumer-ci",
      "kind": "evidence",
      "files": [
        {
          "path": "work/consumer-ci.txt",
          "sha256": "<sha256>"
        }
      ]
    },
    {
      "id": "first-user-study",
      "kind": "external",
      "status": "pending",
      "reason": "requires a participant who did not implement the core framework",
      "evidence": []
    },
    {
      "id": "unseen-task-domain",
      "kind": "external",
      "status": "pending",
      "reason": "requires a genuinely independent task source and frozen rules",
      "evidence": []
    }
  ]
}
```

`benchmark` 报告必须是 `benchmark_score`，`performance` 报告必须是
`agent_performance`。这两个报告的结构化字段由框架重新读取，不接受只写在说明文字里的数字。

## Run it / 执行审计

```bash
agent-regression readiness \
  --manifest work/readiness.json \
  --format markdown \
  --out work/readiness.md
```

Exit codes are stable:

- `0`: every required check passed;
- `1`: the manifest was valid, but a required check is failed or pending;
- `2`: input, path, JSON or SHA-256 verification failed.

Markdown is for reviewers; JSON is for CI and release automation. A pending
human study therefore makes the command return `1`, which is intentional.

## Producing an external evidence record / 生成外部证据

The framework cannot perform an honest independent-user study on behalf of
the maintainer. Use a clean checkout and provide only the README and release
package to the participant. Record:

1. time to run the normal example and the injected failure;
2. time to connect a custom Agent whose claims come from its real output;
3. time to review the baseline and add CI;
4. every question or repair, classified as documentation, error message,
   template or public API;
5. a redacted observation file and its SHA-256.

Once the participant record has been reviewed, change only that external
check to `"status": "passed"` and reference the immutable observation file.
Do not mark it passed because the maintainer was able to run the example.

真正的未见任务也必须在规则冻结后准备，决策阶段不能读取 oracle/reward；先生成 decisions，再单独读取标签评分。
如果数据量小于最终门槛，报告应保留原始计数并保持 `pending` 或 `failed`，不能仅凭百分比宣称成熟。

## Boundary / 边界

This command verifies declared bytes, report shape and thresholds. It does
not prove that a provider, model, dataset, participant or business claim is
truthful. It is specifically designed to expose the remaining external work
instead of hiding it behind a green local test suite.

该命令证明的是“声明的证据文件没有被替换、报告字段满足门槛”，不证明供应商、模型、数据集、参与者或业务结论本身真实。
它的作用正是把仍需外部完成的工作显式暴露出来，而不是用本地测试全绿掩盖缺口。
