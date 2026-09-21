# Recorded sampling study / 记录式采样研究

This example demonstrates the v4.33 `study` evidence-index, provenance-binding and run-identity boundary. A real Agent is run by
the caller, its redacted Trace files are stored beside a manifest, and the
framework evaluates the repeated evidence without receiving an API key or
the raw prompt.

这个示例演示 v4.33 的 `study` evidence index、provenance 绑定和运行身份绑定边界：真实 Agent 由接入方运行，脱敏后的 Trace 和
manifest 放在同一个目录，框架只读取公开 provenance、Trace 和 Contract，不接收 API Key，
也不会把原始 Prompt 写入研究报告。

## Run the deterministic example / 运行确定性示例

```bash
python examples/sampling-study/create_demo_study.py \
  --out-dir work/order-123-study

agent-regression study \
  --manifest work/order-123-study/study.json \
  --format markdown \
  --out work/order-123-study/report.md \
  --checksum-out work/order-123-study/report.md.sha256
```

The report contains the provider/model identifiers, input and tool-schema
hashes, manifest hash, evidence-integrity hashes, the evidence index, Wilson
interval and one row per recorded run. The fixture is deterministic; it is an onboarding check,
not an online model quality result.

报告包含 provider/model 标识、输入和工具 schema 哈希、manifest 哈希、证据完整性哈希、来源
清单、六个语义绑定以及每次运行的一行证据。这里使用确定性 Fixture，只用于验证接入流程，不代表在线模型质量。

## Use with a real Agent / 接入真实 Agent

1. Run the Agent outside the framework with the provider SDK or your own
   framework adapter.
2. Store only redacted `AgentTrace` JSON files. Use stable run IDs and do not
   put API keys, Authorization headers, raw prompts or full provider responses
   in the manifest.
3. Compute `input_sha256` and, when applicable, `tool_schema_sha256` with
   `agent_regression.canonical_sha256` over the canonical input/schema object.
4. Compute a file SHA-256 for the baseline and every run with
   `agent_regression.sha256_file`, put the values in `integrity` and each run,
   and set `require_trace_hashes` to `true`.
5. Create a manifest following the generated `study.json` shape, set the
   reviewed baseline and Contract policy, then run `agent-regression study`.
6. Upload the JSON/Markdown report as CI evidence. A non-zero exit code blocks
   when the Contract, stability policy or minimum sample gate fails.

1. 在框架外使用供应商 SDK 或自己的框架 Adapter 运行 Agent。
2. 只保存脱敏后的 `AgentTrace` JSON，使用稳定的 run ID；不要把 API Key、Authorization
   header、原始 Prompt 或完整供应商响应写入 manifest。
3. 使用 `agent_regression.canonical_sha256` 对规范化输入/schema 对象计算
   `input_sha256` 和（适用时）`tool_schema_sha256`。
4. 使用 `agent_regression.sha256_file` 对 baseline 和每个 run 文件计算 SHA-256，把结果写入
   `integrity` 和每个 run，并将 `require_trace_hashes` 设置为 `true`。
5. 按生成的 `study.json` 结构创建 manifest，写入经过审核的 baseline 和 Contract 策略，
   再执行 `agent-regression study`。
6. 把 JSON/Markdown 报告作为 CI 证据上传；Contract、稳定性策略或最低样本门禁失败时，
   命令返回非零退出码并阻断 CI。

7. For v4.31, add non-secret descriptor files to `evidence` with a role and
   SHA-256, set `integrity.require_evidence_index` to `true`, and list roles
   such as `input`, `tool_schema` and `adapter` in `required_evidence_roles`.
   The report records paths and digests, never descriptor contents.

7. v4.31 中，将非敏感描述文件以 role 和 SHA-256 写入 `evidence`，设置
   `integrity.require_evidence_index` 为 `true`，并在 `required_evidence_roles` 中列出
   `input`、`tool_schema`、`adapter` 等角色。报告只记录路径和摘要，不记录描述文件原文。

8. For v4.32, add `evidence_bindings` entries that bind the descriptor field
   `input_sha256`, `tool_schema_sha256` or `adapter` to the matching
   `provenance.*` target. Set `integrity.require_evidence_bindings` to `true`
   and list mandatory targets in `required_evidence_bindings` when needed.
   The evaluator first checks the file hash, then checks the declared JSON
   value; a hash-valid but semantically mismatched descriptor returns status 2.

8. v4.32 中，增加 `evidence_bindings`，把描述文件中的 `input_sha256`、`tool_schema_sha256` 或
   `adapter` 字段绑定到对应的 `provenance.*` target。需要强制所有绑定存在时，设置
   `integrity.require_evidence_bindings: true`，并在 `required_evidence_bindings` 列出目标。
评估器先校验文件摘要，再校验声明的 JSON 值；即使文件摘要更新正确但语义绑定错误，也会返回状态 2。

9. For v4.33, bind `provenance.provider` and `provenance.model` to separate
   `provider_output` descriptors, and bind `provenance.dataset_revision` to a
   `dataset` descriptor. Add those three targets to
   `required_evidence_bindings` when run attribution is mandatory. The demo
   creates six bindings in total: input, tool schema, adapter, provider,
   model and dataset revision.

9. v4.33 中，将 `provenance.provider` 和 `provenance.model` 分别绑定到两个
   `provider_output` 描述文件，将 `provenance.dataset_revision` 绑定到 `dataset` 描述文件。
   如果运行归因是强制要求，就把三个 target 加入 `required_evidence_bindings`。示例总共创建六个
   绑定：input、tool schema、adapter、provider、model 和 dataset revision。

If a Trace is changed after the manifest is written, the command returns
status `2` with a SHA-256 mismatch instead of evaluating stale evidence.

如果 manifest 写入后 Trace 被修改，命令会返回状态 `2` 并报告 SHA-256 mismatch，而不是继续
评估过期证据。

The report intentionally does not claim a population reliability rate. It
describes the observed sample and its uncertainty; provider sampling design,
account isolation and correctness of the Contract remain the integrator's
responsibility.

报告不会宣称总体可靠率，只描述观察到的样本及其不确定性；供应商采样设计、账号隔离以及
Contract 本身是否正确，仍由接入方负责。

The optional checksum sidecar is over the final report bytes. It makes CI or
audit handoff verifiable, but it is not a signature or a correctness proof.

可选的 checksum sidecar 针对最终报告字节生成，让 CI 或审计交接可以复核；它不是签名，也不是结论正确性证明。
