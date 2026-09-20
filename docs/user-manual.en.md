# Agent Regression Kit user manual

[中文](user-manual.zh-CN.md) · [Technical design](technical-design.en.md) · [Home](../README.md)

For v4.4.0. Commands assume Bash/Zsh on macOS/Linux, run from the repository root unless stated otherwise. Python ≥3.9 is required; CI tests 3.9, 3.11 and 3.13. Installation needs network access; default offline examples need no model credentials.

## 1. What is being tested?

For “look up order 123,” require get_order with order_id=123, a not_shipped result, and a matching structured conclusion. After an Agent change, run it again and compare its recorded behavior against reviewed evidence.

| Term | Meaning |
| --- | --- |
| Agent | Program that selects tools and produces an answer |
| Tool | Callable capability such as get_order |
| Fixture | Controlled test data or service |
| Trace | JSON evidence containing calls, results and the final answer |
| Baseline | Reviewed expected evidence |
| Candidate | Evidence from the changed Agent |
| Claims | Explicit structured conclusions supplied by the integration |
| Adapter | Code connecting an Agent to the recording context |
| Contract | Assertions and behavioral constraints |
| CI gate | A check whose failing exit code blocks a change |

Claims are not extracted from prose automatically. Instrument the conclusion or business state you need to verify.

## 2. Run a passing and a failing comparison


```bash
git clone --branch v4.4.0 https://github.com/ANTAO94/agent-regression-kit.git
cd agent-regression-kit
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
agent-regression --version

agent-regression record \
  --scenario examples/order-123/candidate-ok.scenario.json \
  --out work/candidate.trace.json
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/candidate.trace.json \
  --out work/reports/compare.json
```

Expected: exit 0, passed=true and blocking_difference_count=0. Activate the virtual environment before running the CLI. Git installation avoids assuming availability on PyPI.

Now deliberately introduce a regression:

```bash
agent-regression record \
  --scenario examples/order-123/candidate-regression.scenario.json \
  --out work/bad.trace.json
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/bad.trace.json \
  --out work/reports/regression.json
```

Expected: exit 1 and blocking differences such as changed tool arguments. Run echo $? immediately to inspect the exit code. This failure is intentional; do not accept it as a new baseline.

| Exit | Meaning | Action |
| --- | --- | --- |
| 0 | Check passed | Review and continue |
| 1 | Regression or failed threshold | Fix behavior or review an intentional change |
| 2 | Invalid input, file or Trace | Correct paths, config or schema |

These are comparison/check conventions. report-index is non-gating by default; add --fail-on-regression to gate.

## 3. Inspect evidence


```bash
agent-regression replay --trace work/candidate.trace.json
agent-regression report-index --report-dir work/reports --out work/reports/report-index.json
agent-regression ui
```

Open http://127.0.0.1:8765/index.html and select baseline, candidate and comparison JSON. Select the index on reports.html; generate config on config.html. Ctrl-C stops the local service.

**replay validates and presents existing evidence. It does not rerun an Agent, model or tool.** Generate a new candidate to test changed code. When Agent logic must run without touching live tools, use `replay_agent_run` or `CassetteToolExecutor.from_trace()`; the strict cassette checks tool names, arguments, extra calls and unconsumed calls. Live tool behavior still needs a new recording in an isolated environment.

To review the local evidence workspace without mutating a baseline:

```bash
agent-regression workspace manifest --directory . --out work/workspace-manifest.json
agent-regression baseline review \
  --baseline baselines/order-123.trace.json \
  --candidate work/candidate.trace.json \
  --format markdown --out outputs/baseline-review.md
```

The manifest contains relative paths, sizes and SHA-256 fingerprints only. A
baseline changes only after an explicit `baseline accept` and normal Git review.

The Viewer reads explicitly selected files. Save exported config yourself; the page does not execute Agents, save project files or approve baselines. The index does not automatically load adjacent source reports. GitHub HTML links display source; start ui locally to use the interface.

## 4. Configure assertions and noise filtering

Store expected evidence in baseline files and policy in a separate config. Example .agent-regression/config.json:

```json
{
  "baseline": "baselines/my-agent.trace.json",
  "candidate": "work/my-agent.trace.json",
  "report": "work/reports/compare.json",
  "format": "json",
  "final_answer_mode": "claims-only",
  "contract": {
    "assertions": [
      {
        "path": "final_answer.claims.order_status",
        "equals": "not_shipped"
      },
      {
        "path": "tool_results[*].is_error",
        "equals": false
      }
    ],
    "must_call": [
      {
        "tool": "get_order",
        "arguments": {
          "order_id": "123"
        }
      }
    ],
    "must_not_call": [
      "cancel_order",
      "refund"
    ],
    "max_steps": 1,
    "required_claims": [
      "final_answer.claims.order_status"
    ],
    "path_rules": {
      "any_of": [[
        {
          "tool": "get_order",
          "result": {"status": "not_shipped"},
          "is_error": false
        }
      ]]
    },
    "ignore_paths": [
      "tool_results[*].result.request_id"
    ],
    "normalizers": [
      {
        "path": "tool_results[*].result.updated_at",
        "type": "timestamp"
      }
    ]
  }
}
```


| Setting | Meaning and boundary |
| --- | --- |
| exact | Default; compare answer text and claims |
| claims-only | Allow wording changes; still compare claims, calls and results |
| assertions | One of equals, contains or exists; checks candidate |
| ignore_paths | Remove volatile fields during comparison; supports [*] |
| normalizers | timestamp uses a fixed marker; sort orders by repr; no custom expressions |
| must_call / must_not_call | Required/forbidden tools, optionally constrained by arguments |
| max_steps | Maximum tool calls, not tokens or internal reasoning steps |
| allow_paths | Permit exact reported difference paths; not wildcard filtering |
| path_rules.any_of | Explicit alternatives for allowed tool sequences |
| side_effects | Constraints on recorded initial/final world snapshots |

tool_calls, tool_results and final_answer are comparison projections of events. Do not rewrite Trace events to use them. Assertions use the raw candidate projection, not the ignored/normalized comparison value. All values matched by a wildcard assertion must satisfy it.

Paths in .agent-regression/config.json resolve against the project root. Elsewhere, paths resolve against the config's directory. Explicit CLI flags override configured defaults.

A runnable policy is provided in examples/quickstart/compare.config.json in v4.4.0. After recording the candidate:

```bash
agent-regression config validate --config examples/quickstart/compare.config.json --kind single
agent-regression check --config examples/quickstart/compare.config.json --kind single
agent-regression compare --config examples/quickstart/compare.config.json
```

config validate checks shape. check reads and validates Trace inputs and batch symmetry. compare applies behavioral checks.

## 5. Integrate your own Agent

In your application repository, with the kit installed:

```bash
agent-regression init
python scripts/record_agent.py --out work/my-agent.trace.json
agent-regression validate --trace work/my-agent.trace.json
```

init creates a recording script, config, baseline instructions and CI templates. It preserves existing files by default and does not create an approved baseline. Review the initial run, then accept it explicitly:

```bash
agent-regression baseline accept --trace work/my-agent.trace.json --out baselines/my-agent.trace.json
agent-regression check --config .agent-regression/config.json --kind single
agent-regression compare --config .agent-regression/config.json
```

baseline accept writes the destination and can replace it. Commit only reviewed baselines and policy.

Replace the sample Agent in scripts/record_agent.py. Every tool request must go through context.call_tool(name, arguments). End with context.final_answer(text, claims), deriving claims from actual results. A minimal Python integration:

```python
import json
from pathlib import Path
from agent_regression import CallableAgentAdapter, FixtureTools, record_run

def invoke(request, context):
    order = context.call_tool("get_order", {"order_id": request["order_id"]})
    context.final_answer("Order status: " + order["status"],
                         {"order_status": order["status"]})

trace = record_run(
    CallableAgentAdapter({"name": "my-agent", "version": "1.0"}, invoke),
    {"order_id": "123"},
    FixtureTools({"get_order": {"status": "not_shipped"}}),
    run_id="order-123",
)
Path("work").mkdir(exist_ok=True)
Path("work/my-agent.trace.json").write_text(
    json.dumps(trace.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
)
```

This is a deterministic callback. Connect the real framework's tool dispatcher to the same context; wrapping an opaque completed invoke call cannot capture hidden internal calls.

FixtureTools matches tool names, not arguments. Comparison/contracts detect wrong arguments. Implement ToolExecutor.call or use StatefulFixtureTools for argument-dependent behavior.

The SDK is Python. Java/Spring AI and TypeScript systems need instrumentation emitting the documented JSON schema or a custom bridge; there is no bundled Java/TypeScript SDK. An MCP server provides tools and is not itself an Agent framework.

Generate a sync/async adapter template:

```bash
agent-regression adapter-init --directory my-adapter --name my-agent --mode both
cd my-adapter
PYTHONPATH=. python -m unittest discover -s tests -v
```

For optional LangChain Core verification, return to the repository root, install examples/optional-requirements.txt and run examples/langchain_core_callback_example.py. It checks a RunnableLambda boundary without model keys, not every production Agent lifecycle.

## 6. Use the same policy in CI

Save the following as .github/workflows/agent-regression.yml in your application. Commit the recording script, reviewed baseline and .agent-regression/config.json first, and verify the local comparison.

```yaml
name: Agent regression
on: [push, pull_request]
permissions:
  contents: read
jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        id: install
        run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git@v4.4.0"
      - name: Record candidate
        run: python scripts/record_agent.py --out work/my-agent.trace.json
      - name: Validate inputs
        run: agent-regression check --config .agent-regression/config.json --kind single
      - name: Compare with project policy
        shell: bash
        run: |
          set +e
          agent-regression compare --config .agent-regression/config.json --format json --out work/reports/compare.json
          json_status=$?
          agent-regression compare --config .agent-regression/config.json --format markdown --out work/reports/compare.md
          markdown_status=$?
          agent-regression compare --config .agent-regression/config.json --format junit --out work/reports/compare.xml
          junit_status=$?
          if [ -f work/reports/compare.md ]; then
            cat work/reports/compare.md >> "$GITHUB_STEP_SUMMARY"
          fi
          if [ "$json_status" -ne 0 ]; then exit "$json_status"; fi
          if [ "$markdown_status" -ne 0 ]; then exit "$markdown_status"; fi
          exit "$junit_status"
      - name: Index reports
        if: always() && steps.install.outcome == 'success'
        uses: ANTAO94/agent-regression-kit/.github/actions/agent-report-index@v4.4.0
        with:
          report-dir: work/reports
          json-report: work/reports/report-index.json
          markdown-report: work/reports/report-index.md
          fail-on-regression: 'true'
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: agent-regression-report
          path: work/reports/
```

Use `compare --config` for custom contracts. Since v3.5, the
agent-regression composite Action also accepts a `config` input; legacy
baseline/candidate, allow-path, allow-category and final-answer-mode inputs
remain compatible. Pass `required-reports: compare.json,coverage.json` to the
Report Index Action when missing artifacts must fail the job.

The example generates JSON, Markdown and JUnit even on a regression and preserves failing exit codes. It appends Markdown to Job Summary and uploads artifacts; uploading JUnit does not automatically create per-test GitHub Checks annotations. Keep each CI report directory separate from old or deliberately failing fixtures. The index supplements command failures; it cannot replace them.

## 7. Advanced usage

| Requirement | Entry point | Boundary |
| --- | --- | --- |
| Multiple cases | batch-record / batch-compare | Match relative Trace filenames; missing files fail |
| MCP | mcp-record / record_mcp_run / mcp-http-record | Use controlled test servers |
| Conversations | session-record / session-compare | Independent turn traces, shared Agent/tool state |
| Parallel tools | async_record_run | await plus explicit parallel_group |
| State cleanup | isolated_record_run / SnapshotBackend | Restore only state covered by your backend |
| Nondeterminism | record_stability | Fresh factories per repeat; CLI uses scripted cases, real models use API |
| Coverage | coverage | Tool paths and claims branches, not code coverage |
| Trends | history | Filename order; compare like-for-like cases/metrics across runs |
| Navigation | report-index | compare, batch, stability, coverage, history; optional gating |

See the [advanced guide](usage-guide.en.md) and [API reference](api.md).
history follows the last recognized point's status; report-index requires all indexed reports to pass.

## 8. v4 compatibility and migration

v4 makes upgrade checks executable instead of relying only on release notes. The
command checks the public Python API generation and the independent Trace,
Session, Contract/config and Report schema boundaries:

```bash
agent-regression compatibility \
  --public-api-version 4 \
  --trace baselines/order-123.trace.json \
  --config .agent-regression/config.json \
  --report outputs/compare.json \
  --out outputs/compatibility.json
```

Exit `0` means the supplied inputs are compatible, `1` means an unsupported
generation/schema, and `2` means an unreadable or malformed input. A v3 public
API declaration is returned as `status=deprecated` with
`migration_required=true`, rather than being silently treated as current.

Trace schema 0.1 is unchanged in v4, but an explicit non-destructive migration
entry point is available for future schema changes:

```bash
agent-regression migrate trace \
  --trace baselines/order-123.trace.json \
  --out work/order-123.v4.trace.json \
  --report outputs/order-123.migration.json
agent-regression validate --trace work/order-123.v4.trace.json
```

The migration report contains status and schema versions only; it does not copy
Trace events. See the [v4.4 acceptance contract](v4.4-acceptance.md) for the
complete release checklist.

## 9. Troubleshooting and maintenance

| Symptom | Check |
| --- | --- |
| Command not found | Activate .venv or call .venv/bin/agent-regression |
| Valid config, failed check | Generate inputs and verify relative path rules |
| Correct-looking answer fails | exact checks prose; use claims-only with meaningful assertions when appropriate |
| Wrong arguments return valid fixture data | Name-based FixtureTools; inspect argument differences/contracts |
| Custom CI policy ignored | Use compare --config, not an Action lacking config input |
| Many diffs after a model change | Review evidence before changing noise rules or accepting baseline |
| Sensitive values in artifacts | Review recording, reporting and upload boundaries; default redaction is not exhaustive |

The synchronous RunContext returns redacted tool results to the Agent. Evaluate the effect if those fields participate in business decisions. Model/tool execution can incur costs and side effects; use isolated test environments.

Pin model/Prompt/tool schema, record, review behavior and contracts, explicitly accept, then review in Git. On framework upgrades, test old baselines first. See [CHANGELOG](../CHANGELOG.md) and [UPGRADING](../UPGRADING.md).
