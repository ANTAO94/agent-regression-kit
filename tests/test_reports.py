import unittest
import xml.etree.ElementTree as ET

from agent_regression import render_junit


class ReportTests(unittest.TestCase):
    def test_failed_comparison_renders_junit_failure(self):
        xml = render_junit(
            {
                "passed": False,
                "baseline_run_id": "base",
                "candidate_run_id": "candidate",
                "difference_count": 2,
                "blocking_difference_count": 1,
                "differences": [
                    {"category": "final_answer", "path": "final_answer.text", "allowed": True},
                    {"category": "tool_arguments", "path": "tool_calls[0].arguments", "allowed": False},
                ],
            }
        )
        root = ET.fromstring(xml)
        self.assertEqual("1", root.attrib["failures"])
        failure = root.find("./testcase/failure")
        self.assertIsNotNone(failure)
        self.assertIn("tool_arguments", failure.text)
        self.assertNotIn("final_answer", failure.text)

    def test_passed_comparison_has_no_failure(self):
        xml = render_junit(
            {
                "passed": True,
                "baseline_run_id": "base",
                "candidate_run_id": "candidate",
                "difference_count": 0,
                "blocking_difference_count": 0,
                "differences": [],
            }
        )
        root = ET.fromstring(xml)
        self.assertEqual("0", root.attrib["failures"])
        self.assertIsNone(root.find("./testcase/failure"))


if __name__ == "__main__":
    unittest.main()
