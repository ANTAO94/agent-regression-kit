# Recorded sampling study / 记录式采样研究

This example demonstrates the v4.29 `study` boundary. A real Agent is run by
the caller, its redacted Trace files are stored beside a manifest, and the
framework evaluates the repeated evidence without receiving an API key or
the raw prompt.

这个示例演示 v4.29 的 `study` 边界：真实 Agent 由接入方运行，脱敏后的 Trace 和
manifest 放在同一个目录，框架只读取公开 provenance、Trace 和 Contract，不接收 API Key，
也不会把原始 Prompt 写入研究报告。

## Run the deterministic example / 运行确定性示例

```bash
python examples/sampling-study/create_demo_study.py \
  --out-dir work/order-123-study

agent-regression study \
  --manifest work/order-123-study/study.json \
  --format markdown \
  --out work/order-123-study/report.md
```

The report contains the provider/model identifiers, input and tool-schema
hashes, manifest hash, Wilson interval and one row per recorded run. The
fixture is deterministic; it is an onboarding check, not an online model
quality result.

报告包含 provider/model 标识、输入和工具 schema 哈希、manifest 哈希、Wilson 区间以及每次
运行的一行证据。这里使用确定性 Fixture，只用于验证接入流程，不代表在线模型质量。

## Use with a real Agent / 接入真实 Agent

1. Run the Agent outside the framework with the provider SDK or your own
   framework adapter.
2. Store only redacted `AgentTrace` JSON files. Use stable run IDs and do not
   put API keys, Authorization headers, raw prompts or full provider responses
   in the manifest.
3. Compute `input_sha256` and, when applicable, `tool_schema_sha256` with
   `agent_regression.canonical_sha256` over the canonical input/schema object.
4. Create a manifest following the generated `study.json` shape, set the
   reviewed baseline and Contract policy, then run `agent-regression study`.
5. Upload the JSON/Markdown report as CI evidence. A non-zero exit code blocks
   when the Contract, stability policy or minimum sample gate fails.

1. 在框架外使用供应商 SDK 或自己的框架 Adapter 运行 Agent。
2. 只保存脱敏后的 `AgentTrace` JSON，使用稳定的 run ID；不要把 API Key、Authorization
   header、原始 Prompt 或完整供应商响应写入 manifest。
3. 使用 `agent_regression.canonical_sha256` 对规范化输入/schema 对象计算
   `input_sha256` 和（适用时）`tool_schema_sha256`。
4. 按生成的 `study.json` 结构创建 manifest，写入经过审核的 baseline 和 Contract 策略，
   再执行 `agent-regression study`。
5. 把 JSON/Markdown 报告作为 CI 证据上传；Contract、稳定性策略或最低样本门禁失败时，
   命令返回非零退出码并阻断 CI。

The report intentionally does not claim a population reliability rate. It
describes the observed sample and its uncertainty; provider sampling design,
account isolation and correctness of the Contract remain the integrator's
responsibility.

报告不会宣称总体可靠率，只描述观察到的样本及其不确定性；供应商采样设计、账号隔离以及
Contract 本身是否正确，仍由接入方负责。
