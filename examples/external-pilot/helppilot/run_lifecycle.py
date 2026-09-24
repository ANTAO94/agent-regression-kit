"""Run the installed kit against the pinned HelpPilot graph and retain a closure bundle.

All defects here are explicitly injected. No model or payment credentials are used.
Run with the Python environment that has HelpPilot and the kit wheel installed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from agent_regression import (
    AgentTrace, ComparisonPolicy, ContractPolicy, approve_case, compare_case,
    compare_case_suite, compare_traces, create_case_draft, import_incident,
    resolve_incident, render_incident_report, save_case, validate_resolution,
)


PILOT = Path(__file__).resolve().parent
PIN = "3767824fb90b89a8b19fc4169d912645aaf6fe0b"
MUTATIONS = {
    "wrong-resource": "tool_argument_policy", "skip-tool": "required_tool",
    "misread-result": "contract_assertion", "extra-write": "unauthorized_tool_call",
    "corrupt-policy": "tool_result",
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    commit = subprocess.check_output(
        ["git", "-C", str(args.project_dir), "rev-parse", "HEAD"], text=True,
    ).strip()
    if commit != PIN:
        parser.error("HelpPilot checkout does not match the pinned commit")
    root = args.root.resolve()
    if root.exists() and any(root.iterdir()):
        parser.error("bundle root must be empty; use a new directory for each run")
    root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    shutil.copyfile(PILOT / "baseline.trace.json", root / "baseline.trace.json")
    shutil.copyfile(PILOT / "compare.config.json", root / "policy.json")
    config = json.loads((root / "policy.json").read_text())
    policy = ComparisonPolicy(final_answer_mode=config["final_answer_mode"],
                              contract=ContractPolicy.from_dict(config["contract"]))

    def record(name, mutation="none"):
        subprocess.run([
            sys.executable, str(PILOT / "record_trace.py"),
            "--project-dir", str(args.project_dir), "--bundle-root", str(root),
            "--out", f"{name}.trace.json", "--execution-out", f"{name}.execution.json",
            "--mutation", mutation,
        ], check=True)

    record("normal")
    record("failed", "misread-result")
    baseline = AgentTrace.from_dict(json.loads((root / "baseline.trace.json").read_text()))
    failed = AgentTrace.from_dict(json.loads((root / "failed.trace.json").read_text()))
    failure_report = compare_traces(baseline, failed, policy)
    if failure_report["passed"]:
        raise RuntimeError("the injected failure unexpectedly passed")
    write(root / "failed.compare.json", failure_report)
    incident = import_incident(root=root, trace_path="failed.trace.json",
                               report_path="failed.compare.json", out_path="incident.json",
                               source_kind="injected")
    case = create_case_draft(
        root=root, baseline_path="baseline.trace.json", policy_path="policy.json",
        title="HelpPilot refund response", expected_behavior="Reply follows actual tool evidence",
        incident_refs=[incident.incident_id],
    )
    save_case(case, root=root, out_path="cases/refund.json")
    approve_case(root=root, case_path="cases/refund.json", positive_path="normal.trace.json",
                 negative_path="failed.trace.json", reviewer="fixture-reviewer",
                 reason="Normal output passes and the observed misread result is rejected")
    _, code = compare_case(root=root, case_path="cases/refund.json",
                           candidate_path="failed.trace.json", execution_path="failed.execution.json",
                           out_path="before.case-run.json")
    if code != 1:
        raise RuntimeError("known failure must return 1")
    outcomes = {}
    for mutation, category in MUTATIONS.items():
        name = "failed" if mutation == "misread-result" else mutation
        if name != "failed":
            record(name, mutation)
        run, code = compare_case(root=root, case_path="cases/refund.json",
                                 candidate_path=f"{name}.trace.json", execution_path=f"{name}.execution.json",
                                 out_path=f"checks/{mutation}.case-run.json")
        report = json.loads((root / run["report_ref"]["path"]).read_text())
        categories = sorted({item["category"] for item in report["differences"]})
        if code != 1 or category not in categories:
            raise RuntimeError(f"{mutation}: expected exit 1 and {category}; got {code}, {categories}")
        outcomes[mutation] = {"exit_code": code, "categories": categories}
    # This is explicitly an evidence-only noise fixture, not another Agent run.
    noise = deepcopy(json.loads((root / "normal.trace.json").read_text()))
    noise["events"][-1]["text"] += " Thank you."
    noise["metadata"]["presentation_fixture"] = "evidence-only wording change"
    write(root / "wording.trace.json", noise)
    _, code = compare_case(root=root, case_path="cases/refund.json", candidate_path="wording.trace.json",
                           out_path="checks/wording.case-run.json")
    if code != 0:
        raise RuntimeError("claims-only wording fixture should pass")
    record("recovered")
    _, code = compare_case(root=root, case_path="cases/refund.json", candidate_path="recovered.trace.json",
                           execution_path="recovered.execution.json", out_path="after.case-run.json")
    if code != 0:
        raise RuntimeError("fresh recovered run must pass")
    resolve_incident(root=root, incident_path="incident.json", case_path="cases/refund.json",
                     before_path="before.case-run.json", after_path="after.case-run.json",
                     kind="injected_recovery", reviewer="fixture-reviewer",
                     reason="A fresh graph run recovered under the unchanged reviewed definition",
                     out_path="resolutions/refund.json")
    validate_resolution(root=root, resolution_path="resolutions/refund.json")
    (root / "closure.md").write_text(render_incident_report(
        root=root, incident_path="incident.json", resolution_path="resolutions/refund.json",
    ), encoding="utf-8")
    write(root / "suite.json", {"schema_version": "0.1", "cases": [
        {"case": "cases/refund.json", "candidate": "recovered.trace.json", "execution": "recovered.execution.json"},
    ]})
    _, code = compare_case_suite(root=root, manifest_path="suite.json", out_path="suite.report.json")
    if code:
        raise RuntimeError("recovered suite must pass")
    summary = {"source_kind": "injected", "source_commit": commit, "outcomes": outcomes,
               "wording_exit_code": 0, "recovered_exit_code": code,
               "elapsed_seconds": round(time.monotonic() - started, 3),
               "independent_adoption": False, "closure": "resolutions/refund.json"}
    write(root / "verification.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
