# Agent Regression Kit

[![CI](https://github.com/ANTAO94/agent-regression-kit/actions/workflows/regression.yml/badge.svg)](https://github.com/ANTAO94/agent-regression-kit/actions/workflows/regression.yml)
[![Release](https://img.shields.io/github/v/release/ANTAO94/agent-regression-kit)](https://github.com/ANTAO94/agent-regression-kit/releases)
[MIT](LICENSE)

**Regression tests for AI Agents: catch wrong tools, changed arguments and incorrect business conclusions after changing a prompt, model or code.**

[中文](README.md) · [User manual](docs/user-manual.en.md) · [Technical design](docs/technical-design.en.md)

Python ≥3.9 · Release v4.15.0 · No required third-party core runtime dependencies.

## 1. What does it check?

For “look up order 123”, a reviewed run calls `get_order(order_id="123")` and concludes that the order has not shipped. A changed Agent might query another order, choose a wrong tool or claim that it has shipped.

Provide a reviewed reference run, a fresh run and optional business rules. The kit compares the evidence, evaluates the rules and returns a report and CI exit code.

| Term | Meaning | Example |
| --- | --- | --- |
| Trace | Recorded tool calls, arguments, results and final answer | `*.trace.json` |
| Baseline | A Trace you reviewed as correct | `baselines/order-123.trace.json` |
| Candidate | A fresh Trace from the changed Agent | `work/candidate.trace.json` |
| Contract | Business requirements to check | The `contract` object in a config file |

You own the expected business behavior and baseline review.

## 2. Run a passing and a failing example

Run these commands in order in one Bash/Zsh terminal on macOS/Linux, or WSL on Windows. Installation needs network access. The examples use scripted behavior and fixed local tool responses: **no API key or model calls are needed**.

### Install

```bash
git clone --branch v4.15.0 https://github.com/ANTAO94/agent-regression-kit.git
cd agent-regression-kit
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
agent-regression --version
```

Expect `agent-regression 4.15.0`. Keep the environment active and run subsequent commands from the repository root.

### Record and compare a passing candidate

An example baseline is included:

```bash
agent-regression record \
  --scenario examples/order-123/candidate-ok.scenario.json \
  --out work/candidate.trace.json
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/candidate.trace.json \
  --out work/reports/compare.json
```

Expect `"passed": true`, `"blocking_difference_count": 0` and exit code **0**. The report is written to `work/reports/compare.json`.

### Introduce a regression

```bash
agent-regression record \
  --scenario examples/order-123/candidate-regression.scenario.json \
  --out work/bad.trace.json
agent-regression compare \
  --baseline baselines/order-123.trace.json \
  --candidate work/bad.trace.json \
  --out work/reports/regression.json
```

This fixture changes the tool to `lookup_order`, the order ID from a string to a number, and incorrectly reports that the order has shipped.

Expect `"passed": false` and exit code **1**: the regression was detected. Inspect `differences` in `work/reports/regression.json`:

| Field | Meaning |
| --- | --- |
| `category` | Kind of difference |
| `path` | Affected field |
| `baseline` / `candidate` | Expected and observed values |
| `allowed` | Whether policy explicitly permits the difference |

### View results locally

```bash
agent-regression ui
```

Open the printed address and select a local Trace or comparison report. The configuration page exports JSON for you to save and use with the CLI. It does not run Agents, automatically save configuration or accept baselines.

## 3. Configure assertions and noise filtering

**The baseline stores reference evidence; the config stores checking rules.** Defaults compare calls, arguments, results and the final answer. Add configuration to permit wording changes, filter noise or assert business requirements.

Create `.agent-regression/config.json` under the repository root:

```json
{
  "baseline": "baselines/order-123.trace.json",
  "candidate": "work/candidate.trace.json",
  "report": "work/reports/compare.json",
  "final_answer_mode": "claims-only",
  "contract": {
    "required_claims": [
      "final_answer.claims.order_status"
    ],
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
    "ignore_paths": [
      "tool_results[*].result.request_id"
    ]
  }
}
```

Use the passing candidate recorded in section 2:

```bash
agent-regression compare --config .agent-regression/config.json
```

This requires an `order_status` claim equal to `not_shipped`, rejects tool errors, requires `get_order` with string ID `"123"`, and forbids cancellation/refund tools. Dynamic `request_id` values are ignored when present. `claims-only` permits answer wording changes while still comparing structured conclusions, arguments and results.

**Claims are business facts extracted from the Agent's actual output**, such as `{"order_status": "not_shipped"}`. Your integration supplies them. Hardcoding expected claims hides errors; keep default exact answer comparison until you have meaningful claims.

Paths in a config under `.agent-regression/` resolve relative to the project root. Elsewhere they resolve relative to the config directory. Explicit CLI paths resolve relative to the working directory.

See the [configuration manual](docs/user-manual.en.md), [path variation example](examples/path-variation/README.md) and [state equivalence guide](docs/state-equivalence.md) for additional rules. When relaxing comparisons, also constrain identifiers, amounts and forbidden side effects.

### v4.13 safety policy: failed attempts and undeclared state

A failed write followed by no successful retry must not pass merely because its
tool name and arguments match. Ordinary application regressions use the strict
default. If a business explicitly permits a failed attempt before a retry,
declare the policy:

```json
{
  "state_equivalence": {
    "mode": "outcome",
    "paths": ["world_state.final.orders.123.status"],
    "state_scope": "declared_and_unchanged_rest",
    "attempt_policy": {
      "require_success": true,
      "allow_failed_before_success": true,
      "max_failed_attempts": 1
    }
  }
}
```

This requires a successful action, permits at most one failed attempt, requires
the declared order status to exist and match, and reports other non-ignored
world-state changes as `unexpected_state_change`. Existing
`allow_failed_expected` configs still work, but `agent-regression check
--config ...` emits a migration diagnostic instead of silently changing their
meaning. See the [v4.13 acceptance record](docs/v4.13-acceptance.md) and the
[maturity evolution plan](docs/maturity-evolution-plan.zh-CN.md).

## 4. How to make external evaluation auditable

If you publish a number about how many regressions the framework catches, do not
put labels into the Trace being tested. v4.14 provides a three-step workflow:

```bash
agent-regression benchmark prepare --manifest benchmark/manifest.json
agent-regression benchmark decide \
  --manifest benchmark/manifest.json \
  --out work/benchmark/decisions.json
agent-regression benchmark score \
  --manifest benchmark/manifest.json \
  --decisions work/benchmark/decisions.json \
  --out work/benchmark/score.json
```

`prepare` checks the immutable revision, SHA-256 values for data/split/
Contract/evidence/labels and exact sample coverage. `decide` reads only Traces
and rules; it does not read label meaning. `score` validates the decision digest
before loading labels, then reports true pass, true block, false alarm, missed
failure and Wilson 95% intervals. `unsupported` samples stay explicit instead
of silently disappearing. See the [v4.14 acceptance record](docs/v4.14-acceptance.md)
for the manifest schema and boundaries.

## 5. Connect your own Agent

The earlier `record --scenario` commands execute scripted examples. For your project, actually run the Agent and record its tool calls, results and final output.

| Integration | Entry point |
| --- | --- |
| PydanticAI, OpenAI Agents SDK, LangGraph | [Framework result converters](docs/framework-integrations.md); optional dependencies have their own Python requirements |
| Custom Python Agent | [Callback example](examples/framework_callback_example.py) |
| Existing tool start/end callbacks | [Event ingestion example](examples/langchain_core_event_example.py) |
| MCP tool interaction | [MCP example](examples/mcp_record_example.py); protocol checks and full Agent regression have different scopes |

Run the callback example:

```bash
python examples/framework_callback_example.py
agent-regression validate --trace work/framework-callback.trace.json
```

Review the arguments, results and conclusions in `work/framework-callback.trace.json`. **For the first reviewed run**, save a baseline:

```bash
agent-regression baseline accept \
  --trace work/framework-callback.trace.json \
  --out baselines/my-agent.trace.json
```

After changing the Agent, regenerate the candidate and compare:

```bash
python examples/framework_callback_example.py
agent-regression compare \
  --baseline baselines/my-agent.trace.json \
  --candidate work/framework-callback.trace.json \
  --out work/reports/my-agent.json
```

Adapt these parts of the [callback example](examples/framework_callback_example.py):

| Code | Your responsibility |
| --- | --- |
| `invoke_framework(request, context)` | Your Agent execution |
| `context.call_tool(...)` | Record tool execution; existing frameworks can use event callbacks |
| `context.final_answer(text, claims)` | Record the actual answer and extracted business conclusions |
| `FixtureTools` | Fixed responses for offline tests; supply another tool executor when needed |

The example builds an answer from tool results. With a model Agent, capture its actual answer; constructing a separate correct answer from tool data would hide interpretation failures.

**baseline accept validates and stores a file; it does not review business correctness.** Review first and commit the baseline to Git. Subsequent runs regenerate only the candidate. Do not automatically overwrite the baseline in CI. Intentionally break an argument once to verify the gate detects it.

## 6. Run in CI

Prepare these files in your own repository:

| File | Responsibility |
| --- | --- |
| `scripts/record_agent.py` | Your Agent entry point, producing a fresh candidate each run |
| `baselines/order-123.trace.json` | Reviewed baseline committed to Git |
| `.agent-regression/config.json` | Policy from section 3, adapted to your paths and business rules |

The workflow assumes your script writes `work/candidate.trace.json`. **The kit does not automatically create `scripts/record_agent.py`.** Adapt section 4's example and install your Agent's additional dependencies.

Save as `.github/workflows/agent-regression.yml`:

```yaml
name: Agent regression
on: [push, pull_request]

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.11"
      - name: Install regression kit
        run: python -m pip install "git+https://github.com/ANTAO94/agent-regression-kit.git@v4.15.0"
      - name: Run your Agent and record its trace
        run: python scripts/record_agent.py
      - name: Compare with the reviewed baseline
        run: agent-regression compare --config .agent-regression/config.json
      - name: Upload report even after failure
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: agent-regression-report
          path: work/reports/
          if-no-files-found: error
```

Exit codes: **0 = pass, 1 = regression, 2 = invalid input/configuration**. Nonzero exits fail the job; reports are uploaded even after failure. Do not suppress the comparison exit code with `|| true` or `continue-on-error`.

Run the same commands locally first. Store model credentials in GitHub Secrets and configure redaction at recording time. See the [manual](docs/user-manual.en.md) for JUnit, Markdown and reusable Action examples.

## 7. Evidence and current limits

Suitable for local development and team CI pilots. The v4.15 release records **235 passing tests**, package builds, clean-environment installation and an independent consumer-repository check.

| Evidence | Result and scope |
| --- | --- |
| [Framework compatibility CI](https://github.com/ANTAO94/agent-regression-kit/actions/workflows/framework-compatibility.yml) | Real PydanticAI, OpenAI Agents, LangGraph and LangChain Core runtimes with deterministic model/tool behavior; validates integration |
| [Hosted DeepSeek runs](docs/deepseek-live.md) | Actual single-tool and two-step model runs; tool order is constrained by test policy |
| [Published τ²-bench retail trajectories](docs/tau2-independent-validation.md) | 420 eligible scenarios: 267 true passes, 153 true blocks, 0 false alarms and 0 missed failures |
| [Independent consumer pilot](docs/consumer-pilot.md) | Normal run exits 0; wrong resource, skipped tool and result misread each exit 1 |

τ² equivalence rules were adjusted using errors from this dataset, then retested on the same data. **These are not held-out generalization results.** This integration imports published trajectories; it does not run the upstream simulator or imply upstream adoption.

The kit checks recorded evidence and configured rules. You supply state snapshots where needed. Hidden side effects, free-form factual correctness and production authorization are not automatically guaranteed by Trace comparison. See [limitations](docs/limitations.md).

## 8. Troubleshooting and reference

| Symptom | Check |
| --- | --- |
| Command not found | Activate `.venv`, then install with its `python -m pip install .` |
| Trace/example not found | Run from the repository root and record before comparing |
| Exit 1 | Inspect the report; the failing example should return 1 |
| Exit 2 | Inspect terminal errors, JSON, paths and Trace validation |
| Wording changes fail | Extract actual claims and use `claims-only` with business assertions |
| A valid new path fails | Review its safety, then explicitly configure allowed paths and extra calls |

[Manual](docs/user-manual.en.md) · [Technical design](docs/technical-design.en.md) · [API](docs/api.md) · [Independent consumer pilot](docs/consumer-pilot.md) · [Refund example](examples/refund-business-case/README.md) · [Upgrading](UPGRADING.md) · [Changelog](CHANGELOG.md) · [v4.15 acceptance](docs/v4.15-acceptance.md) · [v4.14 acceptance](docs/v4.14-acceptance.md) · [v4.13 acceptance](docs/v4.13-acceptance.md) · [v4.12 acceptance](docs/v4.12-acceptance.md) · [Supply chain](docs/supply-chain.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)
