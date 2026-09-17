from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any, Dict


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
