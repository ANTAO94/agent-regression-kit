from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any, Dict

from .coverage import path_to_string
from .guidance import next_actions_for_differences


def _markdown_value(value: Any) -> str:
    """Render a compact, escaped value for a human-readable report."""
    if value is None:
        rendered = "null"
    else:
        try:
            rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            rendered = str(value)
    rendered = rendered.replace("|", "\\|").replace("\n", " ")
    if len(rendered) > 320:
        rendered = rendered[:317] + "..."
    return f"`{rendered}`"


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
    differences = report.get("differences", [])
    actions = report.get("next_actions") or next_actions_for_differences(differences)
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
        "## Next actions",
        "",
    ]
    lines.extend(f"- {action}" for action in actions)
    lines.extend(
        [
            "",
        "## Differences",
        "",
        ]
    )
    if not differences:
        lines.append("No differences detected.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "| Status | Category | Path | Diagnostic | Expected | Actual |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for difference in differences:
        difference_status = "allowed" if difference.get("allowed") else "blocking"
        category = str(difference.get("category", "")).replace("|", "\\|")
        path = str(difference.get("path", "")).replace("|", "\\|")
        diagnostic = str(
            difference.get("message", "observed difference")
        ).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {difference_status} | `{category}` | `{path}` | {diagnostic} | "
            f"{_markdown_value(difference.get('baseline'))} | "
            f"{_markdown_value(difference.get('candidate'))} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def render_report_index_markdown(report: Dict[str, Any]) -> str:
    """Render the report index as a compact CI/navigation summary."""
    status = "PASS" if report.get("passed") else "FAIL"
    lines = [
        "# Agent Regression Report Index",
        "",
        f"**Status:** `{status}`",
        "",
        f"- Reports: `{report.get('report_count', 0)}`",
        f"- Passed: `{report.get('passed_count', 0)}`",
        f"- Failed: `{report.get('failed_count', 0)}`",
        f"- Missing required: `{len(report.get('missing_reports', []))}`",
        f"- Skipped: `{len(report.get('skipped', []))}`",
        "",
        "| Status | Type | Label | Relative path |",
        "| --- | --- | --- | --- |",
    ]
    for entry in report.get("entries", []):
        status_text = "passed" if entry.get("passed") else "failed"
        report_type = str(entry.get("report_type", "")).replace("|", "\\|")
        label = str(entry.get("label", "")).replace("|", "\\|")
        source = str(entry.get("source", "")).replace("|", "\\|")
        lines.append(f"| {status_text} | `{report_type}` | `{label}` | `{source}` |")
    if report.get("missing_reports"):
        lines.extend(["", "## Missing required reports", ""])
        for source in report["missing_reports"]:
            lines.append(f"- `{source}`")
    if report.get("skipped"):
        lines.extend(["", "## Skipped", ""])
        for item in report["skipped"]:
            lines.append(f"- `{item.get('source')}`: {item.get('reason')}")
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


def _format_interval(report: Dict[str, Any], metric: str) -> str:
    interval = (report.get("uncertainty") or {}).get(metric)
    if not isinstance(interval, dict):
        return "n/a"
    low = interval.get("low")
    high = interval.get("high")
    if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
        return "n/a"
    return f"{low:.1%}–{high:.1%}"


def render_stability_markdown(report: Dict[str, Any]) -> str:
    """Render repeated-run stability metrics for a CI summary."""
    status = "PASS" if report.get("passed") else "FAIL"
    lines = [
        "# Agent Stability Evaluation",
        "",
        f"**Status:** `{status}`",
        "",
        f"- Baseline: `{report.get('baseline_run_id')}`",
        f"- Runs: `{report.get('run_count', 0)}`",
        f"- Pass rate: `{report.get('pass_rate', 0.0):.1%}`",
        f"- Claims match rate: `{report.get('claims_match_rate', 0.0):.1%}`",
        f"- Tool error rate: `{report.get('tool_error_rate', 0.0):.1%}`",
        f"- Path variants: `{report.get('path_variant_count', 0)}`",
        f"- Pass rate 95% interval: `{_format_interval(report, 'pass_rate')}`",
        f"- Claims match 95% interval: `{_format_interval(report, 'claims_match_rate')}`",
        f"- Tool error 95% interval: `{_format_interval(report, 'tool_error_rate')}`",
        "",
    ]
    sample_size = report.get("sample_size") or {}
    if sample_size.get("small_sample_warning"):
        lines.extend(
            [
                "> Warning: this is a small finite sample; collect at least "
                f"{sample_size.get('recommended_minimum_runs', 30)} runs before "
                "interpreting the interval as a useful sampling estimate.",
                "",
            ]
        )
    lines.extend(
        [
            "| Status | Run | Path | Errors | Blocking differences |",
            "| --- | --- | --- | ---: | ---: |",
        ]
    )
    for run in report.get("runs", []):
        run_status = "passed" if run.get("passed") else "failed"
        path = " -> ".join(run.get("tool_path", [])) or "(no tools)"
        lines.append(
            f"| {run_status} | `{run.get('run_id')}` | `{path}` | "
            f"{run.get('tool_error_count', 0)} | {run.get('blocking_difference_count', 0)} |"
        )
        if run.get("error"):
            lines.append(f"| error | `{run.get('run_id')}` | `{run.get('error')}` | - | - |")
    return "\n".join(lines) + "\n"


def render_stability_junit(report: Dict[str, Any]) -> str:
    """Render one JUnit testcase per repeated stability run."""
    runs = report.get("runs", [])
    failures = sum(1 for run in runs if not run.get("passed"))
    suite = ET.Element(
        "testsuite",
        {
            "name": "agent-regression-stability",
            "tests": str(len(runs)),
            "failures": str(failures),
            "errors": "0",
        },
    )
    for run in runs:
        testcase = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": "agent_regression.stability",
                "name": str(run.get("run_id")),
            },
        )
        if not run.get("passed"):
            failure = ET.SubElement(
                testcase,
                "failure",
                {"type": "AgentStabilityFailure"},
            )
            failure.text = json.dumps(run, ensure_ascii=False, indent=2)
    properties = ET.SubElement(suite, "properties")
    for key in ("pass_rate", "claims_match_rate", "tool_error_rate", "path_variant_count"):
        ET.SubElement(properties, "property", {"name": key, "value": str(report.get(key, 0))})
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def render_async_markdown(trace: Dict[str, Any]) -> str:
    """Render the execution groups of an async Agent Trace."""
    execution = trace.get("metadata", {}).get("execution", {})
    groups = execution.get("parallel_groups", [])
    lines = [
        "# Agent Async Trace",
        "",
        "**Status:** `VALID`",
        "",
        f"- Run: `{trace.get('run_id')}`",
        f"- Execution mode: `{execution.get('mode', 'unknown')}`",
        f"- Events: `{len(trace.get('events', []))}`",
        f"- Parallel groups: `{len(groups)}`",
        "",
        "| Group | Calls | Call IDs |",
        "| --- | ---: | --- |",
    ]
    for group in groups:
        lines.append(
            f"| `{group.get('group_id')}` | {group.get('call_count', 0)} | "
            f"`{', '.join(group.get('call_ids', []))}` |"
        )
    if not groups:
        lines.append("| (none) | 0 | (no parallel groups) |")
    return "\n".join(lines) + "\n"


def render_history_markdown(report: Dict[str, Any]) -> str:
    """Render a long-term regression history and metric trend summary."""
    status = "PASS" if report.get("passed") else "FAIL"
    lines = [
        "# Agent Regression History",
        "",
        f"**Latest status:** `{status}`",
        "",
        f"- Points: `{report.get('point_count', 0)}`",
        f"- Passed points: `{report.get('passed_point_count', 0)}`",
        f"- Historical regressions: `{report.get('regression_count', 0)}`",
        f"- Latest: `{report.get('latest_label')}`",
        "",
        "## Metric trends",
        "",
        "| Metric | First | Latest | Delta | Min | Max |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for metric, values in report.get("metric_trends", {}).items():
        lines.append(
            f"| `{metric}` | {values.get('first')} | {values.get('latest')} | "
            f"{values.get('delta')} | {values.get('min')} | {values.get('max')} |"
        )
    if not report.get("metric_trends"):
        lines.append("| (none) | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Points",
            "",
            "| # | Status | Label | Type | Pass rate | Claims | Tool errors | Paths | Blocking |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for point in report.get("points", []):
        metrics = point.get("metrics", {})
        lines.append(
            f"| {point.get('ordinal')} | {'passed' if point.get('passed') else 'failed'} | "
            f"`{point.get('label')}` | `{point.get('report_type')}` | "
            f"{metrics.get('pass_rate', '-')} | {metrics.get('claims_match_rate', '-')} | "
            f"{metrics.get('tool_error_rate', '-')} | {metrics.get('path_variant_count', '-')} | "
            f"{metrics.get('blocking_difference_count', '-')} |"
        )
    skipped = report.get("skipped", [])
    if skipped:
        lines.extend(["", "## Skipped files", ""])
        for item in skipped:
            lines.append(f"- `{item.get('source')}`: {item.get('reason')}")
    return "\n".join(lines) + "\n"


def render_history_junit(report: Dict[str, Any]) -> str:
    """Render one JUnit testcase per historical report point."""
    points = report.get("points", [])
    failures = sum(1 for point in points if not point.get("passed"))
    suite = ET.Element(
        "testsuite",
        {
            "name": "agent-regression-history",
            "tests": str(len(points)),
            "failures": str(failures),
            "errors": "0",
        },
    )
    for point in points:
        testcase = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": "agent_regression.history",
                "name": str(point.get("label")),
            },
        )
        if not point.get("passed"):
            failure = ET.SubElement(testcase, "failure", {"type": "AgentHistoryRegression"})
            failure.text = json.dumps(point, ensure_ascii=False, indent=2)
    properties = ET.SubElement(suite, "properties")
    for key in ("point_count", "passed_point_count", "failed_point_count", "regression_count"):
        ET.SubElement(properties, "property", {"name": key, "value": str(report.get(key, 0))})
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
