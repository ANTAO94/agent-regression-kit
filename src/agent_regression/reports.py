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
