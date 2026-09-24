"""Reproduce a historical defect in this repository's HelpPilot trace adapter.

This is an isolated adapter fixture, not a HelpPilot production run or an
upstream HelpPilot business defect. No external project code is executed.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

from agent_regression import (
    AgentTrace, ComparisonPolicy, ContractPolicy, approve_case, compare_case,
    compare_traces, create_case_draft, validate_case,
)


FIX_COMMIT = "e917b6eaf31cc4a81e3b1f603a306e89e706d55d"
ADAPTER_PATH = "examples/external-pilot/helppilot/record_trace.py"
BASELINE_PATH = "examples/external-pilot/helppilot/baseline.trace.json"
ACTUAL_REPLY = "Order ORD-5001 is delivered. Your refund was denied."
EXPECTED_REPLY = "Order ORD-5001 is lost. Your refund was denied."
TRACKED_ACTIONS = frozenset({
    "get_order", "get_tracking", "check_refund_policy", "create_refund_draft", "issue_refund",
})
CONTRACT = {"assertions": [{"path": "final_answer.claims.order_status", "equals": "lost"}]}


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _save(root: Path, name: str, value: object) -> str:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    data = _json_bytes(value)
    target.write_bytes(data)
    return _sha(data)


def _source(repo: Path, revision: str) -> tuple[str, bytes]:
    try:
        commit = _git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()
        return commit, _git(repo, "show", f"{commit}:{ADAPTER_PATH}")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"historical adapter source unavailable at {revision}; "
            "fetch the full Git history (git fetch --unshallow for a shallow clone) "
            "and retry. This reproduction requires the exact fix and parent commits."
        ) from exc


def _load_adapter(source: bytes, path: Path, name: str):
    path.write_bytes(source)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load historical adapter {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows_from_baseline(baseline: dict) -> list[dict]:
    calls = {}
    rows = []
    for event in baseline["events"]:
        if event["type"] == "tool_call" and event["tool"] in TRACKED_ACTIONS:
            calls[event["call_id"]] = {"action": event["tool"], "payload": deepcopy(event["arguments"])}
        elif event["type"] == "tool_result" and event["call_id"] in calls:
            row = calls.pop(event["call_id"])
            row["result"] = deepcopy(event["result"])
            rows.append(row)
    if calls or {row["action"] for row in rows} != TRACKED_ACTIONS or len(rows) != len(TRACKED_ACTIONS):
        raise ValueError("current baseline does not contain the expected five complete action rows")
    return rows


def _trace(module, rows: list[dict], reply: str) -> AgentTrace:
    # Both historical functions receive the same action-log rows and state.
    module._action_rows = lambda _db, _thread_id: deepcopy(rows)
    return module._trace_from_run(
        db=None,
        first={"status": "interrupted"},
        final={"state": {
            "route": "use_tools", "approval_decision": "approved",
            "review": {"grounded": True}, "citations": ["refund-policy"],
            "final_reply": reply,
        }},
        thread_id="historical-adapter-fixture",
        source_commit="fixture-from-current-baseline",
        mutation="none",
    )


def reproduce(out: Path, *, repo: Path | None = None) -> dict:
    repo = repo or Path(__file__).resolve().parents[1]
    out = out.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"output directory must be empty: {out}")
    out.mkdir(parents=True, exist_ok=True)

    old_commit, old_source = _source(repo, FIX_COMMIT + "^")
    fixed_commit, fixed_source = _source(repo, FIX_COMMIT)
    baseline_bytes = (repo / BASELINE_PATH).read_bytes()
    rows = _rows_from_baseline(json.loads(baseline_bytes))
    scenario = {"rows": rows, "first_status": "interrupted", "route": "use_tools",
                "approval_decision": "approved", "grounded": True,
                "citations": ["refund-policy"], "actual_reply": ACTUAL_REPLY,
                "mutation": "none"}
    policy_data = {"final_answer_mode": "claims-only", "contract": CONTRACT}
    input_sha = _save(out, "input.json", scenario)
    policy_sha = _save(out, "policy.json", policy_data)

    with tempfile.TemporaryDirectory(prefix="helppilot-adapter-history-") as temp:
        temp_path = Path(temp)
        old = _load_adapter(old_source, temp_path / "old_adapter.py", "helppilot_old_adapter")
        fixed = _load_adapter(fixed_source, temp_path / "fixed_adapter.py", "helppilot_fixed_adapter")
        reference = _trace(old, rows, EXPECTED_REPLY)
        before = _trace(old, rows, ACTUAL_REPLY)
        after = _trace(fixed, rows, ACTUAL_REPLY)

    assert before.events[-1]["text"] == after.events[-1]["text"] == ACTUAL_REPLY
    assert before.events[-1]["claims"]["order_status"] == "lost"
    assert after.events[-1]["claims"]["order_status"] == "delivered"
    for name, trace in (("reference", reference), ("before", before), ("after", after)):
        _save(out, f"{name}.trace.json", trace.to_dict())

    policy = ComparisonPolicy(final_answer_mode="claims-only", contract=ContractPolicy.from_dict(CONTRACT))
    old_report = compare_traces(reference, before, policy)
    fixed_report = compare_traces(reference, after, policy)
    if not old_report["passed"] or fixed_report["passed"]:
        raise AssertionError("historical false-negative behavior did not reproduce")
    if not any("order_status" in item["path"] and not item["allowed"]
               for item in fixed_report["differences"]):
        raise AssertionError("fixed adapter was not rejected for order_status")
    _save(out, "before.compare.json", old_report)
    _save(out, "after.compare.json", fixed_report)

    # Exercise the existing Case lifecycle with reviewed positive/negative samples.
    draft = create_case_draft(
        root=out, baseline_path="reference.trace.json", policy_path="policy.json",
        input_path="input.json", case_id="case-helppilot-adapter-history", revision=1,
        title="Historical HelpPilot adapter claim extraction",
        expected_behavior="The final reply's order status must be lost for this fixture",
        tags=["framework-adapter", "historical-defect"],
    )
    approved = approve_case(
        draft, root=out, positive_path="reference.trace.json", negative_path="after.trace.json",
        reviewer="fixture-maintainer", reason="Known expected reply and known inconsistent reply",
    )
    _save(out, "case.json", approved.to_dict())
    validate_case(approved, out, require_approved=True)
    before_run, before_code = compare_case(
        approved, root=out, candidate_path="before.trace.json",
        agent_revision=old_commit, out_path="before.case-run.json",
    )
    after_run, after_code = compare_case(
        approved, root=out, candidate_path="after.trace.json",
        agent_revision=fixed_commit, out_path="after.case-run.json",
    )
    if (before_code, after_code) != (0, 1):
        raise AssertionError("Case comparison did not reproduce pass-before/fail-after")

    manifest = {
        "scope": "framework HelpPilot adapter historical defect; synthetic fixture, not upstream or production evidence",
        "fix_commit": FIX_COMMIT,
        "adapter_path": ADAPTER_PATH,
        "versions": {
            "before": {
                "commit": old_commit,
                "git_blob_sha": _git(repo, "rev-parse", f"{old_commit}:{ADAPTER_PATH}").decode().strip(),
                "source_sha256": _sha(old_source),
            },
            "after": {
                "commit": fixed_commit,
                "git_blob_sha": _git(repo, "rev-parse", f"{fixed_commit}:{ADAPTER_PATH}").decode().strip(),
                "source_sha256": _sha(fixed_source),
            },
        },
        "current_baseline_sha256": _sha(baseline_bytes),
        "same_input_sha256": input_sha,
        "same_policy_sha256": policy_sha,
        "claims": {"before": "lost", "after": "delivered"},
        "comparison": {
            "before": {"passed": old_report["passed"], "blocking_difference_count": old_report["blocking_difference_count"]},
            "after": {"passed": fixed_report["passed"], "blocking_difference_count": fixed_report["blocking_difference_count"]},
        },
        "case": {"case_id": approved.case_id, "revision": approved.revision,
                 "definition_sha256": approved.review["definition_sha256"],
                 "before_outcome": before_run["outcome"], "after_outcome": after_run["outcome"]},
        "execution_provenance": "evidence_compare only; no fresh HelpPilot execution or ExecutionRecord",
    }
    _save(out, "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new or empty evidence directory")
    args = parser.parse_args()
    try:
        result = reproduce(args.out)
    except RuntimeError as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
