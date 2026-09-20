import unittest
import xml.etree.ElementTree as ET

from agent_regression import render_junit, render_markdown


class ReportTests(unittest.TestCase):
    def test_markdown_report_shows_blocking_and_allowed_differences(self):
        markdown = render_markdown(
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
        self.assertIn("**Status:** `FAIL`", markdown)
        self.assertIn("| allowed | `final_answer` | `final_answer.text` |", markdown)
        self.assertIn("| blocking | `tool_arguments` | `tool_calls[0].arguments` |", markdown)

    def test_markdown_report_for_match_is_concise(self):
        markdown = render_markdown(
            {
                "passed": True,
                "baseline_run_id": "base",
                "candidate_run_id": "candidate",
                "difference_count": 0,
                "blocking_difference_count": 0,
                "differences": [],
            }
        )
        self.assertIn("**Status:** `PASS`", markdown)
        self.assertIn("No differences detected.", markdown)

    def test_markdown_report_exposes_diagnostic_expected_and_actual_values(self):
        markdown = render_markdown(
            {
                "passed": False,
                "baseline_run_id": "base",
                "candidate_run_id": "candidate",
                "difference_count": 1,
                "blocking_difference_count": 1,
                "differences": [
                    {
                        "category": "contract_relation",
                        "path": "tool_calls[2].arguments.amount",
                        "message": "refund amount must not exceed paid amount",
                        "baseline": {"operator": "less_or_equal_path"},
                        "candidate": {"left_values": [880], "right_values": [88]},
                        "allowed": False,
                    }
                ],
            }
        )
        self.assertIn("refund amount must not exceed paid amount", markdown)
        self.assertIn('`{"operator":"less_or_equal_path"}`', markdown)
        self.assertIn('`{"left_values":[880],"right_values":[88]}`', markdown)

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
