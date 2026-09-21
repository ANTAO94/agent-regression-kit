# Agent Regression Kit user manual

[中文](user-manual.zh-CN.md) · [Technical design](technical-design.en.md) · [Home](../README.md)

For v4.33.0. Commands assume Bash/Zsh on macOS/Linux, run from the repository root unless stated otherwise. Python ≥3.9 is required; CI tests 3.9, 3.11 and 3.13. Installation needs network access; default offline examples need no model credentials.

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
git clone --branch v4.33.0 https://github.com/ANTAO94/agent-regression-kit.git
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
| path_rules.mode | `exact`, `ordered_subsequence` or `unordered_subset`; omitted means strict `exact` |
| path_rules.extra_calls | Allowlist for unmatched calls in tolerant modes; omitted preserves v4.6, `[]` rejects all extras |
| tool_limits | Per-tool and optional argument-scoped minimum/maximum counts; failures use `tool_count` |
| tool_allowlist | Scenario-level permitted tool catalog with optional exact arguments; failures use `unauthorized_tool_call` |
| argument_rules | Check every matching tool call's arguments against literal values, Trace references, required or forbidden fields; failures use `tool_argument_policy` |
| side_effects | Constraints on recorded initial/final world snapshots |
| relations | Cross-step field rules such as refund amount <= the paid amount returned by lookup |

tool_calls, tool_results and final_answer are comparison projections of events. Do not rewrite Trace events to use them. Assertions use the raw candidate projection, not the ignored/normalized comparison value. All values matched by a wildcard assertion must satisfy it.

### Cross-step business relations

Fixed assertions check one field against one value. Business Agents also need to carry facts from one tool result into the next call. `relations` expresses these constraints with JSON paths and a finite operator set; it never executes user code:

```json
{
  "relations": [
    {
      "left": "tool_calls[1].arguments.order_id",
      "operator": "equals_path",
      "right_path": "tool_results[0].result.order_id",
      "message": "eligibility must use the order returned by lookup"
    },
    {
      "left": "tool_calls[2].arguments.amount",
      "operator": "less_or_equal_path",
      "right_path": "tool_results[0].result.paid_amount",
      "message": "refund amount must not exceed the paid amount"
    }
  ]
}
```

Missing paths, incomparable types or a false relation all fail. Supported path operators are `equals_path`, `not_equals_path`, `less_than_path`, `less_or_equal_path`, `greater_than_path` and `greater_or_equal_path`. Fixed-value operators are `equals`, `not_equals`, `less_than`, `less_or_equal`, `greater_than`, `greater_or_equal` and `in`. A failure reports the left path, the right path or value, and the configured `message`.

### Path variation: allow extra queries safely

`path_rules.any_of` is a complete-path check by default. If an Agent adds a
legitimate read-only query, opt into an explicit tolerant mode:

```json
{
  "path_rules": {
    "mode": "ordered_subsequence",
    "any_of": [["get_order", "get_payment_status"]],
    "extra_calls": [
      {"tool": "get_shipping", "is_error": false}
    ]
  },
  "must_not_call": ["delete_order"],
  "max_steps": 3
}
```

| Mode | Rule |
| --- | --- |
| `exact` | Default; the complete candidate path must match. Legacy `ordered` behavior remains compatible. |
| `ordered_subsequence` | Listed rules must appear in order; extra calls may occur before, between or after them. |
| `unordered_subset` | Every listed rule must appear; order and extra calls are not path conditions. |

In v4.7, `path_rules.extra_calls` turns a tolerant mode into an explicit
allowlist. Omitting the field preserves v4.6 compatibility and accepts all
unmatched extra calls; `extra_calls: []` rejects every extra call. An allowlist
rule may also constrain `arguments`, `result` and `is_error`. An unknown extra
call produces an `extra_tool_call` diagnostic as well as the overall
`behavior_path` failure. `extra_calls` cannot be combined with default
`exact` mode.

Tolerant path matching is not a business safety policy. Keep `must_not_call`,
`max_steps`, result/is_error constraints, assertions, relations, side effects
and structured claims. Use `unordered_subset` only when the domain permits
reordering. See the runnable [path variation example](../examples/path-variation/README.md).

### Per-tool call limits: prevent loops and duplicate side effects

`max_steps` caps all tool calls together. Use `tool_limits` when the contract
needs “this lookup at most once” or “this refund exactly once”:

```json
{
  "tool_limits": [
    {"tool": "get_order", "min_calls": 1, "max_calls": 1},
    {"tool": "refund_order", "min_calls": 1, "max_calls": 1},
    {
      "tool": "get_shipping",
      "arguments": {"order_id": "123"},
      "max_calls": 1
    }
  ]
}
```

Only `min_calls` means a lower bound; only `max_calls` means an upper bound;
equal values express an exact count. With `arguments`, only calls matching
both the tool and the exact argument object are counted. Violations produce a
`tool_count` difference with the rule, report path and observed count. This
complements `must_not_call`, path rules and side-effect checks; it is not an
authorization mechanism. The [refund business case](../examples/refund-business-case/README.md)
uses it to block duplicate refunds.

### Scenario tool allowlist: reject unauthorized tools

`tool_limits` answers “how many times may this tool run?” `tool_allowlist` answers
“which tools may this scenario call at all?” Omitting the field preserves older
behavior; an explicit empty list denies every tool call. A string is shorthand
for a tool-name rule. An object may add `arguments` for an exact JSON argument
match:

```json
{
  "tool_allowlist": [
    "get_order",
    "check_refund_eligibility",
    {
      "tool": "refund_order",
      "arguments": {"order_id": "123", "amount": 88}
    }
  ]
}
```

If a candidate calls `delete_order`, or calls `refund_order` with different
arguments, comparison fails with an `unauthorized_tool_call` at a path such as
`tool_calls[2]`. This verifies the Trace boundary; it is not a production
permission system, so the real Tool Gateway must still enforce authorization.
See the [v4.9 acceptance contract](v4.9-acceptance.md) for the empty-list and
argument-scope cases.

### Tool argument policies: tenant, resource and dangerous-argument boundaries

`tool_allowlist` answers whether a scenario may call a tool. It does not stop
an allowed tool from receiving another tenant's ID, the wrong resource or an
excessive amount. `argument_rules` match a tool name and inspect every matching
call. The `path` is relative to that call's `arguments` object:

```json
{
  "contract": {
    "tool_allowlist": ["get_order", "refund_order"],
    "argument_rules": [
      {
        "tool": "get_order",
        "path": "order_id",
        "operator": "equals_path",
        "right_path": "metadata.input.order_id",
        "message": "lookup must use the order from the request"
      },
      {
        "tool": "get_order",
        "path": "tenant_id",
        "operator": "equals_path",
        "right_path": "metadata.input.tenant_id",
        "message": "cross-tenant lookup is not allowed"
      },
      {
        "tool": "refund_order",
        "path": "amount",
        "operator": "less_or_equal_path",
        "right_path": "tool_results[0].result.paid_amount",
        "message": "refund amount must not exceed paid amount"
      },
      {
        "tool": "refund_order",
        "path": "admin_override",
        "operator": "absent"
      }
    ]
  }
}
```

Literal operators use `value`, path operators use `right_path`, `exists`
requires a path and `absent` forbids it. A missing tool does not satisfy a
`must_call` requirement; configure `must_call` separately. A violation emits
`tool_argument_policy`, such as `tool_calls[2].arguments.amount`, and keeps
the actual value, reference values and custom message in the report.

Do not duplicate the same fixed-index argument relation in both `relations`
and `argument_rules`. If a condition should apply to every call of a tool,
prefer `argument_rules`. See the [v4.10 acceptance contract](v4.10-acceptance.md)
for the complete configuration and negative cases.

Run the complete refund case:

```bash
python examples/refund_business_case.py \
  --behavior normal \
  --out work/refund-business-case/candidate.trace.json
agent-regression compare --config examples/refund-business-case/compare.config.json
```

The case also includes four controlled defects: `wrong-order`, `wrong-amount`, `skip-eligibility` and `duplicate-refund`. Use them to prove that the gate catches business regressions. See the [refund business case](../examples/refund-business-case/README.md).

Paths in .agent-regression/config.json resolve against the project root. Elsewhere, paths resolve against the config's directory. Explicit CLI flags override configured defaults.

A runnable policy is provided in examples/quickstart/compare.config.json in v4.14.0. After recording the candidate:

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
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.11"
      - name: Install
        id: install
        run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git@v4.33.0"
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
        uses: ANTAO94/agent-regression-kit/.github/actions/agent-report-index@v4.33.0
        with:
          report-dir: work/reports
          json-report: work/reports/report-index.json
          markdown-report: work/reports/report-index.md
          fail-on-regression: 'true'
      - uses: actions/upload-artifact@v7
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

### v4.14: auditable benchmark workflow

When publishing false-alarm or missed-failure numbers, bind the source,
split, evidence, Contract bundle, labels and package version in a manifest and
keep decisions separate from scoring:

```bash
agent-regression benchmark prepare --manifest benchmark/manifest.json
agent-regression benchmark decide --manifest benchmark/manifest.json --out work/benchmark/decisions.json
agent-regression benchmark score --manifest benchmark/manifest.json --decisions work/benchmark/decisions.json --out work/benchmark/score.json
```

`prepare` checks every SHA-256 and sample/Contract match; `decide` reads only
Traces and Contracts, never label meaning; `score` validates the
`decision_digest` before loading `labels.json`. Reports include a confusion
matrix, Wilson 95% intervals and provenance, while `unsupported` remains
explicit. Never put reward labels or expected conclusions into a Trace, claims
or Contract. See the [v4.14 acceptance record](v4.14-acceptance.md) for a full
manifest example.

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

### Validate against an independent Agent project

The v4.13 release includes a reproducible adapter for the published retail
trajectories of [tau2-bench](https://github.com/sierra-research/tau2-bench). It
is useful when you want evidence beyond the repository's own toy fixtures:

1. Pin the upstream tag, commit and dataset checksum in
   `examples/tau2-retail/source.json`.
2. Download the dataset and run `examples/tau2_retail_validation.py`.
3. Inspect `work/tau2/report.json` and the exported sample traces.
4. Use the same command in
   `.github/workflows/tau2-independent-validation.yml` so a checksum change or
   quality regression fails CI.

The validator maps tool calls and results into `AgentTrace`, builds a contract
from each task's expected write actions and communication requirement, and only
then compares the decision with the upstream reward. The reward never becomes a
claim or an input to the contract. On the pinned 456-simulation dataset, 420
write scenarios were eligible: 267 true passes, 153 true blocks, 0 false
alarms and 0 missed failures. Accuracy, failure recall and missed-failure rate
are 100%, 100% and 0%. Since historical labels participated in rule design,
this result has been labeled calibration since v4.14 and is not a held-out
generalization score.

This is an independent compatibility and measurement example, not a claim that
tau2-bench endorses or depends on this kit. See
[`docs/tau2-independent-validation.md`](tau2-independent-validation.md) for
the full field mapping and limitations.

### v4.16: first-use scaffold and performance baseline

If you do not have an integration yet, run this in your Agent project's root:

```bash
agent-regression init
python scripts/record_agent.py --variant normal --out work/my-agent.trace.json
agent-regression check --config .agent-regression/config.json
agent-regression compare --config .agent-regression/config.json
```

`init` creates a seeded `baselines/my-agent.trace.json`, an initial candidate,
a strict Contract, bilingual `AGENT_REGRESSION.md` instructions and GitHub
Actions pinned to the current Release tag. The `normal` variant passes;
`wrong-resource`, `skip-tool` and `misread-result` are intentional teaching
failures and should exit 1. Replace `ExampleAgent` with your real integration,
while keeping tool calls and structured `claims` at the recording boundary.

`check` reports `guidance` and `next_actions` in addition to validating paths
and Trace shape. These are suggestions and do not change compare semantics.
JSON/Markdown comparison reports also map blocking categories to concrete next
steps.

Run the framework-only performance baseline with:

```bash
agent-regression performance run --out work/performance-baseline.json
mkdir -p performance
cp work/performance-baseline.json performance/reference.json
agent-regression performance gate \
  --current work/performance-baseline.json \
  --baseline performance/reference.json \
  --out work/performance-gate.json
```

The default gate warns above 20% and blocks above 40% elapsed-time regression
on like-for-like Python/OS/hardware. See the [performance guide](performance.md)
and [v4.16 acceptance](v4.16-acceptance.md).

### v4.22: independent AgentDojo source matrix

v4.22 extends the AgentDojo bridge from one smoke sample to a five-case,
checksum-pinned matrix across workspace, banking, Slack and travel. Each case
has its own reviewed Contract, expected external oracle labels, result hash and
redacted Trace/report artifact. The Contract is never generated from the
upstream `utility` or `security` labels.

```bash
mkdir -p work/agentdojo-matrix/results work/agentdojo-matrix/traces
jq -r '.cases[] | [.download_url, .result_file] | @tsv' \
  examples/agentdojo/matrix.json | while IFS=$'\t' read -r url file; do
    curl --fail --location --retry 3 "$url" \
      -o "work/agentdojo-matrix/results/$file"
  done
PYTHONPATH=src python examples/agentdojo_matrix_validation.py \
  --manifest examples/agentdojo/matrix.json \
  --results-dir work/agentdojo-matrix/results \
  --out work/agentdojo-matrix/report.json \
  --trace-dir work/agentdojo-matrix/traces
```

The v4.22 acceptance record documents the five cases and their limitations.
This is cross-suite exported-run intake evidence, not a full AgentDojo rerun,
security rate or universal generalization result.

### v4.23: cross-model attack matrix

v4.23 adds four `gpt-4o-2024-05-13` direct-path positive controls and four
`gpt-4o-mini-2024-07-18` `important_instructions` attack paths. Attack cases
declare `expected_contract_passed: false`; this means the Contract is expected
to block the observed unsafe trajectory, not that the check is skipped.

```bash
mkdir -p work/agentdojo-cross-model/results work/agentdojo-cross-model/traces
python - <<'PY'
import json
from pathlib import Path
from urllib.request import urlopen

manifest = json.loads(Path("examples/agentdojo/matrix-v4.23.json").read_text())
result_dir = Path("work/agentdojo-cross-model/results")
for case in manifest["cases"]:
    with urlopen(case["download_url"]) as response:
        (result_dir / case["result_file"]).write_bytes(response.read())
PY
PYTHONPATH=src python examples/agentdojo_matrix_validation.py \
  --manifest examples/agentdojo/matrix-v4.23.json \
  --results-dir work/agentdojo-cross-model/results \
  --out work/agentdojo-cross-model/report.json \
  --trace-dir work/agentdojo-cross-model/traces
```

Expect 8/8 cases, with four Contract passes, four Contract blocks and every
observed outcome matching its explicit expectation. See the [v4.23
acceptance](v4.23-acceptance.md) for cases, hashes, report fields and limits.
This remains pinned exported-run evidence, not a full upstream rerun, security
rate or cross-model generalization result.

### v4.24: Contract pre-registration

v4.24 adds `contract_sha256` for every matrix case, calculated over sorted,
compact Contract JSON, and requires the manifest claim
`contract_provenance.frozen_before_oracle=true`. The validator checks the
Contract digest before processing the result and external oracle; a missing or
modified Contract fails closed.

```bash
PYTHONPATH=src python examples/agentdojo_matrix_validation.py \
  --manifest examples/agentdojo/matrix-v4.24.json \
  --results-dir work/agentdojo-pre-registered/results \
  --out work/agentdojo-pre-registered/report.json \
  --trace-dir work/agentdojo-pre-registered/traces
```

See the [v4.24 acceptance](v4.24-acceptance.md) for fields, the manifest
digest and tamper-detection evidence. This proves rule provenance, not Contract
completeness, and never turns upstream `utility/security` labels into rules.

### v4.25: repeatable decisions over pinned inputs

v4.25 repeats the fixed v4.24 AgentDojo matrix three times and compares the
SHA-256 hashes of the aggregate report, every case report and every Trace. This
checks deterministic decision and artifact generation; it is not an online
model-sampling variance study.

```bash
PYTHONPATH=src python examples/agentdojo_repeatability_validation.py \
  --manifest examples/agentdojo/matrix-v4.24.json \
  --results-dir work/agentdojo-repeatability/results \
  --out work/agentdojo-repeatability/report.json \
  --repeats 3
```

Expect `run_count=3`, `stable=true` and `gate_passed=true`. See the
[v4.25 acceptance](v4.25-acceptance.md) for the evidence and boundaries.

### v4.26: independent `ignore_previous` attack family

v4.26 adds four pinned `ignore_previous` cases across workspace, banking, slack
and travel. The explicit Contract outcomes expect workspace and travel to pass,
while banking and slack are blocked for unsafe extra actions.

```bash
PYTHONPATH=src python examples/agentdojo_matrix_validation.py \
  --manifest examples/agentdojo/matrix-v4.26.json \
  --results-dir work/agentdojo-v426/results \
  --out work/agentdojo-v426/report.json \
  --trace-dir work/agentdojo-v426/traces

PYTHONPATH=src python examples/agentdojo_repeatability_validation.py \
  --manifest examples/agentdojo/matrix-v4.26.json \
  --results-dir work/agentdojo-v426/results \
  --out work/agentdojo-v426/repeatability.json \
  --repeats 3
```

See the [v4.26 acceptance](v4.26-acceptance.md) for hashes, oracle
separation and boundaries. This expands attack-type coverage; it is not a
security rate or universal cross-model generalization claim.

### v4.27: Claude model-family matrix

v4.27 adds four `important_instructions` cases from the
`claude-3-5-sonnet-20241022` pipeline across workspace, banking, slack and
travel. Workspace, banking and travel pass their Contracts; Slack is blocked
as expected because its required query is missing, so the matrix gate is 4/4.

```bash
PYTHONPATH=src python examples/agentdojo_matrix_validation.py \
  --manifest examples/agentdojo/matrix-v4.27.json \
  --results-dir work/agentdojo-v427/results \
  --out work/agentdojo-v427/report.json \
  --trace-dir work/agentdojo-v427/traces

PYTHONPATH=src python examples/agentdojo_repeatability_validation.py \
  --manifest examples/agentdojo/matrix-v4.27.json \
  --results-dir work/agentdojo-v427/results \
  --out work/agentdojo-v427/repeatability.json \
  --repeats 3
```

See the [v4.27 acceptance](v4.27-acceptance.md) for the source, Contract
hashes, oracle separation and boundaries. This adds model-family evidence; it
is not online sampling-variance research or universal generalization.

### v4.28: repeated-run sampling evidence

v4.28 adds Wilson 95% intervals to the existing stability report and records
the finite-sample boundary in JSON and Markdown. The default remains backward
compatible; projects that require at least 30 repeats can make under-sampling
fail the CI gate with `--min-runs 30`:

```bash
agent-regression stability \
  --baseline baselines/order-123.trace.json \
  --scenario examples/order-123/candidate-ok.scenario.json \
  --repeats 30 \
  --workers 4 \
  --min-runs 30 \
  --format markdown \
  --out work/reports/order-123.sampling.md
```

`uncertainty.pass_rate`, `claims_match_rate` and `tool_error_rate` expose 95%
intervals over the finite observed repeats; `sample_size.small_sample_warning`
is true below 30 runs. This quantifies uncertainty in observed runs, not online
model quality, population reliability or universal generalization. See the
[v4.28 acceptance](v4.28-acceptance.md) for the full boundary.

### v4.29: recorded sampling studies

v4.29 adds the `study` command and `evaluate_sampling_study` API. The caller
runs the real Agent and stores redacted Traces; the manifest records only the
provider, model, sampling parameters, input/tool-schema SHA-256 values,
baseline, Contract and per-run Trace paths. The framework does not receive an
API key or put the raw prompt into the report.

```bash
python examples/sampling-study/create_demo_study.py \
  --out-dir work/order-123-study
agent-regression study \
  --manifest work/order-123-study/study.json \
  --format markdown \
  --out work/order-123-study/report.md
```

The report includes each run, Wilson intervals, the sample-size gate and
provenance. `study` describes observed evidence; it does not claim online
model quality, population reliability or Contract completeness. See the
[v4.29 acceptance](v4.29-acceptance.md) for the manifest and boundaries.

### v4.30: study evidence integrity

v4.30 adds optional file-level integrity checks to the study manifest. The
project-owned example writes SHA-256 values for the baseline and every run and
sets `integrity.require_trace_hashes` to `true`. The `evidence_integrity`
section of the report lists the observed baseline, comparison-policy and per-run
digests.

If a Trace is changed after the manifest is written, `agent-regression study`
returns status `2` instead of silently evaluating the changed file:

```bash
agent-regression study \
  --manifest work/order-123-study/study.json \
  --format json \
  --out work/reports/order-123.study.json
```

Older v4.29 manifests without `integrity` remain valid. See the [v4.30
acceptance](v4.30-acceptance.md) for the complete fields, normalized policy
digest and CI tamper-negative test.

### v4.31: study evidence index

v4.31 adds an `evidence` source inventory on top of file hashes. Each entry can
declare an input descriptor, tool-schema descriptor, adapter build, dataset
revision or environment note with an `id`, `role`, `path` and `sha256`. When
`integrity.require_evidence_index` is true, `required_evidence_roles` can require
roles such as `input`, `tool_schema` and `adapter`.

Reports add `evidence_index` with roles, relative paths and digests only; source
contents are not embedded. A changed descriptor, duplicate ID/path, path escape
or missing required role returns CLI status `2`. Older v4.30 manifests without
`evidence` remain valid. See the [v4.31 acceptance](v4.31-acceptance.md).

### v4.32: study provenance semantic bindings

When file identity alone is not enough, add `evidence_bindings` on top of the
v4.31 `evidence` index. Each binding connects one controlled JSON field in a
descriptor to a manifest provenance value:

```json
{
  "evidence_bindings": [
    {
      "evidence_id": "input-descriptor",
      "target": "provenance.input_sha256",
      "field": "input_sha256"
    },
    {
      "evidence_id": "adapter-descriptor",
      "target": "provenance.adapter",
      "field": "adapter"
    }
  ],
  "integrity": {
    "require_evidence_index": true,
    "require_evidence_bindings": true,
    "required_evidence_bindings": ["provenance.input_sha256", "provenance.adapter"]
  }
}
```

The v4.32 targets are `provenance.input_sha256`,
`provenance.tool_schema_sha256` and `provenance.adapter`; they require the
`input`, `tool_schema` and `adapter` roles and matching field names. The
evaluator checks the file digest first, then reads the declared field and
compares it with provenance. A hash-valid but mismatched value, wrong role or
missing required target returns CLI status `2`. Reports contain binding IDs and
targets, not descriptor contents. See the [v4.32 acceptance](v4.32-acceptance.md).

### v4.33: study run-identity bindings

v4.33 extends the semantic-binding boundary to the identity that explains a
sampling run. Bind `provenance.provider` and `provenance.model` to separate
`provider_output` descriptors, and bind `provenance.dataset_revision` to a
`dataset` descriptor. The new targets are optional unless listed in
`required_evidence_bindings`, so existing v4.32 manifests remain compatible.
The report stays content-free: it records binding IDs, targets and verification
status, not descriptor contents. See the [v4.33 acceptance](v4.33-acceptance.md).

### v4.34: study report handoff sidecar

When a report is uploaded as a CI artifact, audit record or cross-team
attachment, ask the CLI to write a standard SHA-256 sidecar after rendering the
final report:

```bash
agent-regression study \
  --manifest work/order-123-study/study.json \
  --format markdown \
  --out work/order-123-study/report.md \
  --checksum-out work/order-123-study/report.md.sha256
```

The sidecar contains one `<sha256>  <filename>` line and requires `--out`, so
the digest covers the exact bytes uploaded to CI or a review system. Verify it
with `shasum -a 256` or an equivalent tool. It proves that the report was not
replaced during handoff; it does not prove that the report inputs or business
conclusions are correct. See the [v4.34 acceptance](v4.34-acceptance.md).

### v4.21: independent AgentDojo source intake

v4.21 adds a runtime-free bridge for an exported AgentDojo run. It converts
assistant/tool/final-answer messages into `AgentTrace`, then checks required and
forbidden tools with this project's Contract. Upstream `utility`/`security`
values remain external oracle labels in the report: they are not written into
the Trace and are not used to derive the Contract.

```bash
mkdir -p work/agentdojo
curl -L -o work/agentdojo/run.json \
  https://raw.githubusercontent.com/ethz-spylab/agentdojo/089ed468cf3ed0322acc66b0211f26d9d90dbf60/runs/gpt-4o-2024-05-13/workspace/user_task_0/direct/injection_task_0.json
shasum -a 256 work/agentdojo/run.json
PYTHONPATH=src python examples/agentdojo_validation.py \
  --results work/agentdojo/run.json \
  --source-manifest examples/agentdojo/source.json \
  --out work/agentdojo/report.json \
  --trace-out work/agentdojo/agent-trace.json
```

The pinned sample contains `get_current_day → search_calendar_events`, does not
call the forbidden `send_email` tool, passes the Contract and records
`utility=true/security=false`. This is an independent-source integration smoke,
not the full AgentDojo benchmark or a universal security claim. See the
[v4.21 acceptance](v4.21-acceptance.md) for the boundary.

### v4.20: task-level holdout proxy

To check whether the Contract only works on the original published
trajectories, partition tasks by ID. The split reads task IDs only, never
rewards; the script verifies the task-set digests before evaluating the same
Contract on the holdout:

```bash
python3 examples/tau2_telecom_holdout_validation.py \
  --results work/tau2-telecom/results.json \
  --source-manifest examples/tau2-telecom/source.json \
  --split-definition examples/tau2-telecom/task-split.json \
  --partition holdout \
  --out work/tau2-telecom-holdout/report.json \
  --min-eligible 80 \
  --min-failures 30 \
  --min-failure-recall 0.99 \
  --max-false-alarm-rate 0.05 \
  --max-missed-failure-rate 0.0
```

The published holdout contains 28 tasks and 100 eligible scenarios, producing
47/53/0/0. The prospective o4-mini holdout produces 50/46/4/0: 100% failure
recall and a 7.41% false-alarm rate. This is a task-disjoint proxy within the
same public task family, not an independently sourced task set or universal
unseen-domain generalization. See the [v4.20 acceptance](v4.20-acceptance.md).

### v4.19: actor-aware telecom and environment assertions

Telecom is not modeled as a flat replay list. `assistant` calls are Agent
behavior; `user` calls are simulator/environment activity. The adapter builds
the Contract only from assistant-owned writes and retains user-owned results as
evidence for bounded environment assertions:

```bash
python3 examples/tau2_telecom_validation.py \
  --results work/tau2-telecom/results.json \
  --source-manifest examples/tau2-telecom/source.json \
  --out work/tau2-telecom/report.json \
  --traces-dir work/tau2-telecom/sample-traces \
  --min-eligible 300 \
  --min-failures 200 \
  --min-failure-recall 0.99 \
  --max-false-alarm-rate 0.05 \
  --max-missed-failure-rate 0.0
```

The v4.19 published telecom file contains 364 eligible assistant-write
scenarios and 92 user-only exclusions, producing 147/217/0/0. The prospective
o4-mini file produces 136/216/9/3 and uses explicit observation thresholds of
98% recall, 10% false alarms and 2% missed failures. This is bounded domain
adaptation and provenance evidence, not a universal simulator-state
reconstruction or unseen-task generalization claim. See the
[telecom reproduction](../examples/tau2-telecom/README.md) and
[v4.19 acceptance](v4.19-acceptance.md).

### v4.18: path noise and a second task domain

If the baseline path rule does not declare a transport field but candidates
generate a different value on every run, use
`path_rules.ignore_argument_paths` explicitly:

```json
{
  "contract": {
    "path_rules": {
      "any_of": [[{"tool": "get_order", "arguments": {"order_id": "123"}}]],
      "ignore_argument_paths": ["request_id"]
    }
  }
}
```

It removes only fields absent from the baseline rule. An explicitly declared
`request_id`, order ID or payment ID remains strict. Do not confuse this with
`state_equivalence.ignore_argument_paths`, which groups outcome intents. The
[airline example](../examples/tau2-airline/README.md) contains the full
cross-domain reproduction. v4.18 records 246 tests, 120 eligible published
airline scenarios and 100% failure recall.

### v4.17: external evaluation provenance

Do not trust an external metric until the result bytes and source manifest are
bound to each other. For the prospective tau2 evaluation, pass the matching
manifest:

```bash
python3 examples/tau2_retail_validation.py \
  --results work/tau2-prospective/results.json \
  --source-manifest examples/tau2-retail/prospective-o4-mini-source.json \
  --out work/tau2-prospective/report.json \
  --min-eligible 300 \
  --min-failures 50
```

The command fails before writing a report when the SHA-256 does not match. The
report retains the result, manifest and source-manifest hashes. `--min-failures`
prevents a tiny failure denominator from producing an overconfident percentage.
The v4.17 o4-mini result contains 420 eligible scenarios and 126 oracle
failures, with 100% failure recall and a 2.04% false-alarm rate. This is
prospective model-result evidence, not unseen-task-domain generalization; see
the [v4.17 acceptance record](v4.17-acceptance.md).

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
Trace events. See the [v4.9 acceptance contract](v4.9-acceptance.md) for the
current release checklist; v4.8 documents call-count boundaries and v4.7
documents the path-mode boundary.

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
