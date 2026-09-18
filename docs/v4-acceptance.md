# Agent Regression Kit v4.0 Acceptance / v4.0 验收说明

This document defines what “v4.0 stable” means for the local and CI core. It
is an acceptance contract, not a promise that every Agent framework is
automatically supported.

本文定义本地核心与 CI 核心达到 v4.0 的条件。它是可执行的验收契约，
不是“任意 Agent 框架都能自动接入”的承诺。

## 1. Stable boundaries / 稳定边界

| Boundary / 边界 | v4.0 contract / v4.0 契约 | Migration rule / 迁移规则 |
| --- | --- | --- |
| Public Python API | `PUBLIC_API_VERSION=4`; documented imports are `agent_regression.__all__` | v3 is readable as deprecated; update before the next major release |
| AgentTrace | schema `0.1` | v4 does not reinterpret existing fields; use `migrate trace` for canonical output |
| AgentSession | schema `0.1` | validate before comparison; no silent turn reshaping |
| Contract/config | schema `0.1` implicit for existing configs | unknown semantics must be rejected or explicitly documented |
| Reports | schema `0.1`; every report has `report_type` and `schema_version` | report consumers must reject unsupported schemas |
| Package | Python `>=3.9`; source distribution and wheel | clean virtual environment is the install authority |

The package version, public API generation and evidence schema are independent:
changing one does not silently change the others.

产品版本、公共 API 代际和证据 schema 是三个独立概念；升级其中一个，不会
悄悄改写另外两个。

## 2. Compatibility check / 兼容性检查

The command is read-only. It validates the declared API generation and any
documents supplied to it:

```bash
agent-regression compatibility \
  --public-api-version 4 \
  --trace baselines/order-123.trace.json \
  --config .agent-regression/config.json \
  --report outputs/compare.json \
  --out outputs/compatibility.json
```

Exit codes:

- `0`: all supplied documents are valid and supported;
- `1`: a document or declared API generation is unsupported;
- `2`: the command input is missing, malformed JSON, or cannot be read.

`public_api_version=3` returns a passing readability check with
`migration_required=true` and `status=deprecated`. This is deliberate: teams
can stage an upgrade without being told that an old integration is current.

`compatibility` 不修改 Trace、baseline 或配置。v3 公共 API 会被标记为
deprecated，而不是假装已经是 v4；这样可以先检查再安排升级。

## 3. Explicit Trace migration / 显式 Trace 迁移

Trace schema `0.1` is unchanged in v4. The migration command nevertheless
provides one stable, non-destructive entry point for future schema changes:

```bash
agent-regression migrate trace \
  --trace baselines/order-123.trace.json \
  --out work/order-123.v4.trace.json \
  --report outputs/order-123.migration.json

agent-regression validate --trace work/order-123.v4.trace.json
```

The source file is never overwritten. The output is a canonical validated
Trace; the migration report contains status and schema versions but does not
copy Trace events or sensitive payloads.

源文件不会被覆盖。输出文件是经过校验的规范化 Trace；迁移报告只记录状态
和 schema 版本，不复制事件内容或敏感数据。

## 4. Release gate / 发布门禁

Every v4 release must pass all of these checks:

1. Full offline unit/integration tests, including the project-owned MCP stdio
   and Streamable HTTP fixtures.
2. Framework event ingestion tests and the optional LangChain Core example.
3. Compatibility checks for Trace, Session, Contract/config and Report JSON.
4. A wheel and source distribution build.
5. A clean virtual-environment install using the built wheel.
6. CLI checks for `--version`, `ui --help`, `compatibility`, `migrate trace`,
   `validate` and `workspace manifest`.
7. Viewer asset and local-link checks.
8. Redaction, loopback-default and no-baseline-mutation tests.

The release workflow is the executable version of this list. A local green
test run is useful evidence, but it does not replace the clean-install gate.

每个 v4 版本都必须通过全量离线测试、真实框架事件示例、四类文档兼容检查、
源码包/wheel 构建、干净环境安装、CLI、Viewer、脱敏、loopback 和 baseline
不自动覆盖检查。发布工作流是这份清单的可执行实现。

## 5. Security boundary / 安全边界

- Viewer remains a local static, read-only file viewer and binds to loopback by
  default.
- `workspace manifest` records relative paths, byte sizes and SHA-256 only.
- `baseline review` compares evidence but never accepts or overwrites a
  baseline.
- `migrate trace` writes only the explicit output path.
- Redaction is applied to CLI reports; filenames and external logs may still be
  sensitive and must be reviewed before upload.
- MCP subprocesses and real framework callbacks run with the caller's
  permissions; isolation and test data ownership remain integration concerns.

## 6. Service layer decision / 是否服务化

v4.0 deliberately keeps the core local/CI-first. A hosted service should be a
separate product layer only after real teams demonstrate a repeated need for:

- durable report storage and search;
- project/user/role/audit management;
- webhook, remote runner and notification orchestration;
- tenant isolation and server-side secret management.

Those features must consume the versioned Trace/Contract/Report boundaries;
they must not move business policy into an opaque server or make the local CLI
unusable.

v4.0 有意保持本地/CI 优先。只有真实团队持续需要报告存储、权限审计、远程
Runner 或多租户密钥管理时，才评估独立服务层；服务层必须消费版本化边界，
不能反过来污染核心 API。
