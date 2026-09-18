# Upgrading Agent Regression Kit

This file records migration actions for released versions. The core rule is:
**upgrade the comparison tool before changing a reviewed baseline**. A package
upgrade must not silently turn a candidate difference into a new baseline.

## v3.1.x → v3.2.0

### What changed

- The package version is read from one source: `agent_regression.__version__`.
- MCP `clientInfo.version` now follows the package version automatically.
- `agent-regression ui` serves the local Trace Inspector and configuration
  center. It binds to loopback by default and is read-only.
- `agent-regression check` validates a comparison config and its referenced
  Trace inputs before `compare` or `batch-compare` runs.
- `check_adapter_contract` and `check_async_adapter_contract` provide
  structured integration diagnostics for framework adapters.
- `PUBLIC_API_VERSION` and `SUPPORTED_TRACE_SCHEMA_VERSIONS` make the public
  compatibility boundaries explicit.
- Viewer assets are included in wheel installations, and the release workflow
  verifies a clean installation.

### Recommended migration

```bash
python -m pip install --upgrade agent-regression-kit==3.2.0
agent-regression --version
agent-regression config validate --config .agent-regression/config.json --kind single
agent-regression check --config .agent-regression/config.json --kind single
agent-regression compare --config .agent-regression/config.json
```

For a batch suite, use `--kind batch`. Keep the existing baseline files and
review the generated diff before accepting any intentional behavior change.

### Compatibility expectations

- AgentTrace `0.1` remains the supported evidence schema; existing v3.1 traces
  are expected to remain readable.
- Existing `record`, `compare`, `batch-compare`, MCP, Contract, stability,
  coverage, session, and history commands keep their documented boundaries.
- The local Viewer does not execute Agents or rewrite baselines. It can be
  removed from a headless deployment without affecting the Python core.
- Optional framework dependencies are not installed by the core package.

### Rollback

If a project integration has not been validated yet, restore the package pin
to the previous version and keep the same baseline files:

```bash
python -m pip install --force-reinstall agent-regression-kit==3.1.0
```

Do not copy a candidate Trace over a baseline as a rollback mechanism.

## v3.2.0 → v3.2.1

This is a patch release. It adds migration/compatibility release material,
Python-version CI coverage, and hardens redaction for the `secret_values`
configuration field. No Trace schema migration is required.

## v3.2.1 → v3.2.2

This is a packaging-only patch release. The wheel now includes the bilingual
getting-started guide, upgrade guide, and compatibility matrix under
`share/agent-regression-kit/docs`. No runtime or Trace schema migration is
required.

## v3.3.0 → v3.3.1

This is a small CI and Viewer handoff patch. The configuration center now links
the generated policy to the Report Index review step, and the core GitHub
workflow appends `report-index.md` to `GITHUB_STEP_SUMMARY` in addition to
uploading the output directory. No Trace schema or configuration migration is
required.

```bash
python -m pip install --upgrade agent-regression-kit==3.3.1
agent-regression --version
```

## v3.3.1 → v3.4.0

This feature release adds the reusable `agent-report-index` GitHub Action. It
generates JSON and Markdown indexes for a shared `outputs/` directory, appends
the Markdown to GitHub Job Summary, and can fail when any recognized report is
failed. The coverage Action now also emits JSON, so compare and coverage
evidence can be reviewed together. No Trace schema migration is required.

```bash
python -m pip install --upgrade agent-regression-kit==3.4.0
agent-regression --version
```

## v3.4.0 → v3.4.1

This patch fixes the core GitHub workflow's release-quality matrix behavior.
It installs explicit build tooling for Python 3.13, isolates generated CI
reports under `work/ci-reports`, and avoids running the report-index Action when
package installation itself failed. No Trace or configuration migration is
required.

```bash
python -m pip install --upgrade agent-regression-kit==3.4.1
agent-regression --version
```

## v3.4.1 → v3.4.2

This patch fixes the tag-triggered release workflow so its source-tree test
suite can import the `src` layout before building and installing the wheel. No
runtime, Trace schema, or configuration migration is required.

```bash
python -m pip install --upgrade agent-regression-kit==3.4.2
agent-regression --version
```

## v3.4.2 → v3.4.3

This feature release completes the unified CI evidence handoff. The main
workflow writes compare, stability, coverage, and history JSON into the same
report directory, and the Report Index includes the history aggregate in the
Job Summary. No Trace schema or configuration migration is required.

```bash
python -m pip install --upgrade agent-regression-kit==3.4.3
agent-regression --version
```

## v3.4.3 → v3.5.0

This feature release hardens CI trust boundaries without changing the
AgentTrace `0.1` schema. Contracts can require structured claim paths, report
indexes can require named reports or globs, and the reusable comparison Action
can load a project `config` containing the contract. Existing
`baseline`/`candidate` Action inputs continue to work.

```bash
python -m pip install --upgrade agent-regression-kit==3.5.0
agent-regression --version
agent-regression config validate --config .agent-regression/config.json
agent-regression compare --config .agent-regression/config.json
agent-regression report-index --report-dir outputs \
  --required-report compare.json --fail-on-regression
```

No Trace schema migration is required. Review existing contracts that use
`claims-only`; add `contract.required_claims` for fields that must not be
silently omitted. In the Report Index Action, use comma-separated
`required-reports` values when missing artifacts should fail the job.

## v3.2.2 → v3.3.0

This is a feature release for team CI handoff. It adds `report-index`, which
recognizes compare, batch, stability, and coverage JSON reports and emits a
safe relative-path inventory for the local Report Index Viewer. The reusable
GitHub Action also writes a machine-readable comparison JSON report, and the
core workflow uploads the JSON and Markdown index alongside JUnit output.

No AgentTrace schema migration is required. Existing baseline and candidate
files remain valid. After upgrading, add the optional index step to a workflow:

```bash
python -m pip install --upgrade agent-regression-kit==3.3.0
agent-regression --version
agent-regression report-index \
  --report-dir outputs \
  --out outputs/report-index.json
```

Use `--fail-on-regression` when the index itself should be a CI gate. The local
Viewer remains read-only and requires an explicit file selection for the index
and original reports.

## English release checklist

For each upgrade, record the package version, Trace schema version, test count,
wheel installation result, framework compatibility result, and MCP smoke
result in the pull request or release notes. The canonical machine-readable
boundaries are returned by `public_api_manifest()`.

## 中文说明

升级原则是：**先升级回归工具，再审核行为差异；不要因为工具升级就自动
覆盖 baseline。** 3.3.0 新增报告索引和 CI 机器可读报告，3.3.1 增加 Job
Summary 和配置中心交接，3.4.0 增加可复用的统一报告 Action，3.4.1 修复
Python matrix 和报告目录隔离，但不会改变
AgentTrace `0.1` 的含义，也不会自动读取或覆盖 baseline。

建议顺序：安装固定版本 → 检查 `--version` → `config validate` → `check` →
运行 compare → 审核报告。回滚时只恢复工具版本，不要把 candidate 复制成
baseline。
