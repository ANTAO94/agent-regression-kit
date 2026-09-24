# Reviewed regression cases (development source)

This guide describes the v4.40.0 source lifecycle, including the previously unreleased v4.39 work. These commands are not part of the older v4.38.1 wheel. Install the current checkout while release validation is in progress. See the [Chinese guide](case-lifecycle.zh-CN.md) for the same workflow.

## What the five objects mean

An **Incident** records the failure and its redacted Trace and comparison report. An **EvaluationCase** points to a reviewed good baseline and comparison policy. Its `expected_behavior` explains the business rule to a reviewer; the executable checks live in the policy's Contract. A **CaseRun** records one comparison of an approved case against a new candidate Trace. A Trace is one Agent execution with tool calls, tool results, and a final answer.

The runner compares evidence produced by your existing Agent script. It does not launch arbitrary commands or infer the right business answer. `execution_mode` is `evidence_compare`; `agent_revision` is copied from the candidate Trace when present, otherwise `unknown`. A passing comparison without a new candidate run does not establish that a code fix was executed.

An **ExecutionRecord** binds one callback invocation to its output Trace, timing, code revision, and input/environment digests. An **IncidentResolution** links the original failure, unchanged reviewed rules, a new passing execution, and a reviewer's reason. A passing comparison alone does not close an incident.

## Bundle layout and setup

Install this source checkout in a virtual environment with `python -m pip install -e .`. Use one bundle directory. All path arguments below except `--root` are relative to that root. Absolute paths, `..`, and symlink escape are rejected by the new lifecycle commands.

```text
bundle/
  baseline.trace.json     # reviewed good run
  policy.json             # comparison policy and business Contract
  failed.trace.json       # observed failing run
  failed.compare.json     # existing agent_compare report
  normal.trace.json       # known good sample for approval
  incident.json
  cases/refund.json
  candidate.trace.json    # freshly recorded Agent run in CI
  suite.json
```

The policy uses the existing comparison configuration fields, for example:

```json
{
  "final_answer_mode": "claims-only",
  "contract": {
    "required_claims": ["final_answer.claims.refund_issued"],
    "assertions": [{"path": "final_answer.claims.refund_issued", "equals": true}]
  },
  "evidence_requirements": [{"path": "metadata.fixture_version", "exists": true, "type": "string"}]
}
```

Contract fields express a **known violation** and can fail the gate. `evidence_requirements` express whether enough evidence was collected; a missing requirement gives `inconclusive`. Do not declare the same path in both places. Noise allowances use `allow_categories`, `allow_paths`, `final_answer_mode`, and Contract normalizers exactly as in the existing compare command. The runner ignores the old config's `baseline`, `candidate`, and `report` path fields; the reviewed case and explicit candidate argument control those inputs.

## From one failure to a reviewed case

First run your own Agent and create `failed.trace.json`; generate a report with the existing `agent-regression compare` command. Then, from a directory containing all these files:

```bash
agent-regression incident import --root bundle \
  --trace failed.trace.json --report failed.compare.json \
  --out incident.json --source-kind injected

agent-regression case draft --root bundle --incident incident.json \
  --baseline baseline.trace.json --policy policy.json \
  --expected-behavior "The reply follows the observed refund result" \
  --out cases/refund.json

agent-regression case validate --root bundle --case cases/refund.json

agent-regression case approve --root bundle --case cases/refund.json \
  --positive normal.trace.json --negative failed.trace.json \
  --reviewer antao --reason "A wrong refund conclusion must be caught"

agent-regression case compare --root bundle --case cases/refund.json \
  --candidate candidate.trace.json --out candidate.case-run.json
```

The incident import redacts sensitive keys and optional `--secret-value` strings before saving evidence. Inspect the redacted copy if those fields are needed by your Contract. Approval is refused unless the good sample passes and the known bad sample fails. A draft cannot be used as a CI gate. The approval SHA-256 binds the case definition to the hashes of its baseline, policy, and optional input/environment files; changes invalidate approval. Use `case revise` to create a new draft revision while preserving the old approved definition:

```bash
agent-regression case revise --root bundle --case cases/refund.json \
  --policy policy-v2.json --out cases/refund-r2.json
```

The new revision must pass validation and approval again. The identity string in `--reviewer` is a local declaration; Git review provides team provenance.

Gates also revalidate both approval samples and reports: files, hashes, run IDs, and recomputed outcomes. Deleting an approval sample or editing `outcome` invalidates the approval. For older cases lacking evidence, use `case upgrade --root bundle --case cases/refund.json --out cases/refund-r2.json`, then approve the new draft again. Upgrade does not manufacture historical evidence.

`case compare` writes both `candidate.case-run.json` and `candidate.case-run.compare.json`. The CaseRun file stores the report reference and SHA-256, evidence reference, and case revision. The separate comparison report retains the original differences or evidence gaps; the suite report embeds each case's comparison report. Exit codes are `0` pass, `1` definite regression, and `2` incomplete evidence or error. The legacy compare commands keep their existing behavior.

## CI suite

Each case has an explicit candidate mapping. For example, `bundle/suite.json`:

```json
{"schema_version":"0.1","cases":[
  {"case":"cases/refund.json","candidate":"candidate.trace.json"}
]}
```

Run your Agent recording script first, then:

```bash
agent-regression case suite compare --root bundle \
  --manifest suite.json --out suite.report.json
```

The suite retains every case result. Any `error` or `inconclusive` returns `2`; otherwise any `fail` returns `1`; all passes return `0`. An empty suite, duplicate case ID, missing candidate, or unsafe path returns `2`. CI should upload the candidate Traces and case reports as artifacts. See [the fixed HelpPilot workflow](../.github/workflows/case-lifecycle.yml) and its [independent Agent example](../examples/external-pilot/helppilot/README.md).

## Current scope

This lifecycle supports single Traces. `kind: session` is rejected explicitly; the existing `session-compare` command remains separate. The HelpPilot mutation is a controlled fault injection, not evidence of an upstream production defect or real money movement. The schema files are under [`schema/`](../schema/). See [v4.40 acceptance](v4.40-acceptance.md) for tests, build results and hosted release status.

## Capture a new execution, not a new timestamp on an old file

Wrap your existing Agent invocation in the recording script:

```python
from agent_regression import record_execution

# run_agent executes your Agent and returns an AgentTrace.
# Construct FrameworkTraceRecorder INSIDE that callback and capture actual outputs.
record_execution(
    root="bundle", trace_path="candidate.trace.json",
    out_path="candidate.execution.json", invoke=run_agent,
    agent_revision=git_commit, dirty=False,
    input_data=request, environment={"fixture": "refund-v1"},
)
```

This is an integration snippet, not a standalone script: your application supplies `run_agent`, `git_commit`, and `request`. `FrameworkTraceRecorder` picks up the active execution ID inside the callback. A custom Trace adapter must read `agent_regression.execution_records.current_execution_id()` there and populate `metadata.execution_id`. A Trace prepared outside the callback is rejected. The API takes a synchronous callback, not a coroutine.

The recorder saves a redacted Trace and input/environment digests. Keep credentials out of environment manifests. ExecutionRecord timings measure the Agent callback; CaseRun timings measure comparison work. With an execution record attached, CaseRun uses its code revision and checks the Trace's `source_commit` for consistency.

These are integrity checks, not signatures: a malicious caller can still fabricate a callback and files. Local records have `declared` provenance. Complete CI producer metadata (`runner`, `repository`, `commit`, `job_id`, `run_id`) allows `ci_correlated`, which is still not authentication. Producer commit must identify the executed Agent revision, not accidentally the toolkit repository revision.

## Close the original incident

Assume `before.case-run.json` was generated from the original failure and the positive/negative samples have been approved:

```bash
agent-regression execution validate --root bundle \
  --record candidate.execution.json --candidate candidate.trace.json --require-recorded
agent-regression case validate --root bundle --case cases/refund.json --review-evidence
agent-regression case compare --root bundle --case cases/refund.json \
  --candidate candidate.trace.json --execution candidate.execution.json --out after.case-run.json
agent-regression incident resolve --root bundle --incident incident.json \
  --case cases/refund.json --before before.case-run.json --after after.case-run.json \
  --kind injected_recovery --reviewer antao --reason "Fresh execution recovers under unchanged rules" \
  --out resolutions/refund.json
agent-regression incident report --root bundle --incident incident.json \
  --resolution resolutions/refund.json --format markdown
```

Closure verifies that before belongs to the imported incident, both runs use the same Case ID/revision/definition hash, before fails, and after passes when recomputed. After needs a fresh Trace/run ID and valid execution record. Evidence-only candidates can still be compared but cannot establish strict closure. Changing fixed inputs or environment must not masquerade as recovery under unchanged conditions.

When before has an execution record, both input/environment digests must be present and unchanged. For a historical failure without one, the Case must fix `input_ref` and `environment_ref`, which the new record must match. The report explicitly notes that the old runtime conditions were not independently recorded; this compatibility path is not complete provenance.

Resolution files refuse overwrite and do not modify the original Incident. Resolved status is derived from valid closure evidence. Copy the whole bundle when moving it, preserving relative paths. Missing files, altered rules, hash mismatches, or forged reports fail revalidation. Refused closure returns `2` and does not create a successful resolution.

Use `injected_recovery` only for injected incidents. `bug_fix` requires `historical_bug` and a nonempty `--change-ref`. The reviewer must inspect that reference: the framework cannot prove causality merely from a Git URL.

## Run the complete HelpPilot example

Follow the [HelpPilot setup instructions](../examples/external-pilot/helppilot/README.md) for its pinned checkout and environment, install this kit into that environment, then run:

```bash
/path/to/helppilot/.venv/bin/python examples/external-pilot/helppilot/run_lifecycle.py \
  --project-dir /path/to/helppilot --root /tmp/my-new-case-bundle
```

The bundle root must be empty. The script executes normal, five negative, and fresh recovery runs, approval, closure, and a suite. Expected negatives must return exactly `1`; exceptions are not swallowed. Outputs include `verification.json`, `closure.md`, and all referenced evidence. No model credentials or real refunds are involved. This is a real external graph with deterministic model/retrieval substitutes: it demonstrates technical integration and rule closure, not online model quality or independent adoption.

Add `"execution":"candidate.execution.json"` to a suite entry to bind its candidate to an execution record. The example workflow is framework self-validation, not your business gate. Business CI must record its current candidate, compare reviewed cases, and propagate nonzero exits. Configure required repository checks separately to block noncompliant PR merges.
