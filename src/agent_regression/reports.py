from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any, Dict

from .coverage import path_to_string


def render_junit(report: Dict[str, Any]) -> str:
    """Render one comparison report as a portable JUnit XML suite."""
    passed = bool(report.get("passed"))
    suite = ET.Element(
        "testsuite",
        {
            "name": "agent-regression",
            "tests": "1",
            "failures": "0" if passed else "1",
            "errors": "0",
        },
    )
    case = ET.SubElement(
        suite,
        "testcase",
        {
            "classname": "agent_regression.compare",
            "name": f"{report.get('baseline_run_id')} -> {report.get('candidate_run_id')}",
        },
    )
    if not passed:
        blocking = [item for item in report.get("differences", []) if not item.get("allowed", False)]
        failure = ET.SubElement(
            case,
            "failure",
            {
                "message": f"{len(blocking)} blocking agent regression difference(s)",
                "type": "AgentRegressionFailure",
            },
        )
        failure.text = json.dumps(blocking, ensure_ascii=False, indent=2)
    properties = ET.SubElement(suite, "properties")
    ET.SubElement(
        properties,
        "property",
        {"name": "difference_count", "value": str(report.get("difference_count", 0))},
    )
    ET.SubElement(
        properties,
        "property",
        {
            "name": "blocking_difference_count",
            "value": str(report.get("blocking_difference_count", 0)),
        },
    )
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def render_markdown(report: Dict[str, Any]) -> str:
    """Render a compact human-readable comparison summary."""
    passed = bool(report.get("passed"))
    status = "PASS" if passed else "FAIL"
    lines = [
        "# Agent Regression",
        "",
        f"**Status:** `{status}`",
        "",
        f"- Baseline: `{report.get('baseline_run_id')}`",
        f"- Candidate: `{report.get('candidate_run_id')}`",
        f"- Differences: `{report.get('difference_count', 0)}`",
        f"- Blocking differences: `{report.get('blocking_difference_count', 0)}`",
        "",
        "## Differences",
        "",
    ]
    differences = report.get("differences", [])
    if not differences:
        lines.append("No differences detected.")
        return "\n".join(lines) + "\n"
    lines.extend(["| Status | Category | Path |", "| --- | --- | --- |"])
    for difference in differences:
        difference_status = "allowed" if difference.get("allowed") else "blocking"
        category = str(difference.get("category", "")).replace("|", "\\|")
        path = str(difference.get("path", "")).replace("|", "\\|")
        lines.append(f"| {difference_status} | `{category}` | `{path}` |")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_batch_markdown(report: Dict[str, Any]) -> str:
    """Render a batch comparison summary."""
    status = "PASS" if report.get("passed") else "FAIL"
    lines = [
        "# Agent Regression Batch",
        "",
        f"**Status:** `{status}`",
        "",
        f"- Cases: `{report.get('case_count', 0)}`",
        f"- Passed: `{report.get('passed_case_count', 0)}`",
        f"- Failed: `{report.get('failed_case_count', 0)}`",
        "",
        "| Status | Case | Blocking differences |",
        "| --- | --- | ---: |",
    ]
    for case in report.get("cases", []):
        case_status = "passed" if case.get("passed") else "failed"
        blocking = case.get("blocking_difference_count", 0)
        if "reason" in case:
            blocking = case["reason"]
        lines.append(f"| {case_status} | `{case.get('case')}` | `{blocking}` |")
    return "\n".join(lines) + "\n"


def render_batch_junit(report: Dict[str, Any]) -> str:
    """Render one JUnit testcase per batch case."""
    cases = report.get("cases", [])
    suite = ET.Element(
        "testsuite",
        {
            "name": "agent-regression-batch",
            "tests": str(len(cases)),
            "failures": str(report.get("failed_case_count", 0)),
            "errors": "0",
        },
    )
    for case in cases:
        testcase = ET.SubElement(
            suite,
            "testcase",
            {"classname": "agent_regression.batch", "name": str(case.get("case"))},
        )
        if not case.get("passed"):
            failure = ET.SubElement(testcase, "failure", {"type": "AgentRegressionFailure"})
            failure.text = json.dumps(case, ensure_ascii=False, indent=2)
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def render_scenario_batch_markdown(report: Dict[str, Any]) -> str:
    """Render a parallel scenario-recording summary."""
    status = "PASS" if report.get("passed") else "FAIL"
    lines = [
        "# Agent Scenario Batch Recording",
        "",
        f"**Status:** `{status}`",
        "",
        f"- Cases: `{report.get('case_count', 0)}`",
        f"- Passed: `{report.get('passed_case_count', 0)}`",
        f"- Failed: `{report.get('failed_case_count', 0)}`",
        f"- Max workers: `{report.get('max_workers', 0)}`",
        "",
        "| Status | Case | Run | Events / Error |",
        "| --- | --- | --- | --- |",
    ]
    for case in report.get("cases", []):
        case_status = "passed" if case.get("passed") else "failed"
        detail = case.get("event_count", case.get("error", ""))
        lines.append(
            f"| {case_status} | `{case.get('case_id')}` | `{case.get('run_id')}` | `{detail}` |"
        )
    return "\n".join(lines) + "\n"


def render_scenario_batch_junit(report: Dict[str, Any]) -> str:
    """Render one JUnit testcase per parallel recording case."""
    cases = report.get("cases", [])
    suite = ET.Element(
        "testsuite",
        {
            "name": "agent-regression-scenario-recording",
            "tests": str(len(cases)),
            "failures": str(report.get("failed_case_count", 0)),
            "errors": "0",
        },
    )
    for case in cases:
        testcase = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": "agent_regression.scenario_batch",
                "name": str(case.get("case_id")),
            },
        )
        if not case.get("passed"):
            failure = ET.SubElement(
                testcase,
                "failure",
                {"type": "AgentScenarioRecordingFailure"},
            )
            failure.text = str(case.get("error", "scenario recording failed"))
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def render_coverage_markdown(report: Dict[str, Any]) -> str:
    """Render a scenario path-coverage summary for a CI job summary."""
    status = "PASS" if report.get("passed") else "FAIL"
    lines = [
        "# Agent Scenario Coverage",
        "",
        f"**Status:** `{status}`",
        "",
        f"- Cases: `{report.get('case_count', 0)}`",
        f"- Unique tool paths: `{report.get('unique_path_count', 0)}`",
        f"- Expected paths covered: `{report.get('covered_expected_path_count', 0)}/{report.get('expected_path_count', 0)}`",
        f"- Coverage: `{report.get('coverage_percent', 100.0)}%`",
        f"- Business branches covered: `{report.get('covered_expected_branch_count', 0)}/{report.get('expected_branch_count', 0)}`",
        f"- Business branch coverage: `{report.get('business_branch_coverage_percent', 100.0)}%`",
        "",
        "## Observed paths",
        "",
        "| Status | Tool path | Cases |",
        "| --- | --- | ---: |",
    ]
    expected = {
        tuple(path): True for path in report.get("expected_paths", [])
    }
    for entry in report.get("paths", []):
        signature = tuple(entry.get("path", []))
        lines.append(
            f"| covered | `{entry.get('signature')}` | {entry.get('case_count', 0)} |"
        )
        expected.pop(signature, None)
    for path in report.get("missing_paths", []):
        lines.append(f"| missing | `{ ' -> '.join(path) }` | 0 |")
    for branch in report.get("missing_branches", []):
        branch_text = json.dumps(branch, ensure_ascii=False, sort_keys=True)
        lines.append(f"| missing business branch | `{branch_text}` | 0 |")
    if not report.get("paths") and not report.get("missing_paths"):
        lines.append("| none | No recorded paths | 0 |")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_coverage_junit(report: Dict[str, Any]) -> str:
    """Render each expected path as a JUnit test case."""
    expected = report.get("expected_paths", [])
    missing = {tuple(path) for path in report.get("missing_paths", [])}
    expected_branches = report.get("expected_branches", [])
    missing_branches = [
        json.dumps(branch, ensure_ascii=False, sort_keys=True)
        for branch in report.get("missing_branches", [])
    ]
    tests = len(expected) + len(expected_branches)
    if not tests:
        tests = len(report.get("paths", [])) + len(report.get("business_branches", [])) or 1
    failures = len(missing) + len(missing_branches)
    suite = ET.Element(
        "testsuite",
        {
            "name": "agent-regression-coverage",
            "tests": str(tests),
            "failures": str(failures),
            "errors": "0",
        },
    )
    paths = expected or [entry.get("path", []) for entry in report.get("paths", [])]
    for path in paths:
        signature = path_to_string(path)
        testcase = ET.SubElement(
            suite,
            "testcase",
            {"classname": "agent_regression.coverage", "name": signature},
        )
        if tuple(path) in missing:
            failure = ET.SubElement(
                testcase,
                "failure",
                {"type": "AgentCoverageFailure", "message": "expected tool path was not observed"},
            )
            failure.text = signature
    for branch in expected_branches:
        branch_signature = json.dumps(branch, ensure_ascii=False, sort_keys=True)
        testcase = ET.SubElement(
            suite,
            "testcase",
            {"classname": "agent_regression.coverage", "name": f"branch-{branch_signature}"},
        )
        if branch_signature in missing_branches:
            failure = ET.SubElement(
                testcase,
                "failure",
                {"type": "AgentCoverageFailure", "message": "expected business branch was not observed"},
            )
            failure.text = branch_signature
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def render_session_markdown(report: Dict[str, Any]) -> str:
    """Render a multi-turn session comparison."""
    status = "PASS" if report.get("passed") else "FAIL"
    lines = [
        "# Agent Regression Session",
        "",
        f"**Status:** `{status}`",
        "",
        f"- Baseline session: `{report.get('baseline_session_id')}`",
        f"- Candidate session: `{report.get('candidate_session_id')}`",
        f"- Turns compared: `{report.get('turn_count', 0)}`",
        f"- Blocking differences: `{report.get('blocking_difference_count', 0)}`",
        f"- Candidate state continuity: `{'PASS' if report.get('state_continuity', {}).get('candidate_passed', True) else 'FAIL'}`",
        "",
        "| Status | Turn | Differences |",
        "| --- | ---: | ---: |",
    ]
    for turn in report.get("turns", []):
        turn_status = "passed" if turn.get("passed") else "failed"
        lines.append(
            f"| {turn_status} | {turn.get('turn')} | {turn.get('blocking_difference_count', 0)} |"
        )
    if not report.get("turns"):
        lines.append("| failed | session | turn count mismatch |")
    return "\n".join(lines) + "\n"


def render_session_junit(report: Dict[str, Any]) -> str:
    """Render one JUnit testcase per compared session turn."""
    turns = report.get("turns", [])
    failures = sum(1 for turn in turns if not turn.get("passed"))
    if report.get("difference_count") and not turns:
        failures = 1
    suite = ET.Element(
        "testsuite",
        {
            "name": "agent-regression-session",
            "tests": str(len(turns) or 1),
            "failures": str(failures),
            "errors": "0",
        },
    )
    for turn in turns:
        testcase = ET.SubElement(
            suite,
            "testcase",
            {"classname": "agent_regression.session", "name": f"turn-{turn.get('turn')}"},
        )
        if not turn.get("passed"):
            failure = ET.SubElement(testcase, "failure", {"type": "AgentSessionFailure"})
            failure.text = json.dumps(turn.get("differences", []), ensure_ascii=False, indent=2)
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"
