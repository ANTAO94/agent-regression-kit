import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CiIntegrationTests(unittest.TestCase):
    def test_reusable_action_exposes_the_comparison_policy_controls(self):
        action = (ROOT / ".github/actions/agent-regression/action.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("final-answer-mode:", action)
        self.assertIn("result-alignment:", action)
        self.assertIn("config:", action)
        self.assertIn("allow-path:", action)
        self.assertIn("json-report:", action)
        self.assertIn('agent-regression "${args[@]}" --format json --out "$JSON_REPORT"', action)
        self.assertIn('args+=(--final-answer-mode "$FINAL_ANSWER_MODE")', action)
        self.assertIn('args+=(--allow-path "$path")', action)
        self.assertIn('args+=(--result-alignment "$RESULT_ALIGNMENT")', action)
        self.assertIn('args=(compare --config "$CONFIG")', action)
        coverage_action = (ROOT / ".github/actions/agent-coverage/action.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("json-report:", coverage_action)
        self.assertIn('agent-regression "${args[@]}" --format json --out "$JSON_REPORT"', coverage_action)

    def test_report_index_action_writes_both_formats_and_job_summary(self):
        action = (ROOT / ".github/actions/agent-report-index/action.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("json-report:", action)
        self.assertIn("markdown-report:", action)
        self.assertIn("--format json", action)
        self.assertIn("--format markdown", action)
        self.assertIn("GITHUB_STEP_SUMMARY", action)
        self.assertIn("required-reports:", action)
        self.assertIn("--required-report", action)
        framework_workflow = (ROOT / ".github/workflows/framework-compatibility.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("langchain_core_event_example.py", framework_workflow)
        self.assertIn("langchain-core-events.trace.json", framework_workflow)

    def test_core_workflow_uses_isolated_ci_report_directory(self):
        workflow = (ROOT / ".github/workflows/regression.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -m pip install --upgrade pip setuptools wheel", workflow)
        self.assertIn("id: install", workflow)
        self.assertIn("work/ci-reports", workflow)
        self.assertIn("steps.install.outcome == 'success'", workflow)
        self.assertIn("Record stability evidence", workflow)
        self.assertIn("Record coverage evidence", workflow)
        self.assertIn("Aggregate history evidence", workflow)
        self.assertIn("--out work/ci-reports/history.json", workflow)

    def test_release_workflow_runs_source_tests_with_package_path(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("PYTHONPATH: src", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("agent-regression compatibility", workflow)
        self.assertIn("agent-regression migrate trace", workflow)
        self.assertIn("agent-regression workspace manifest", workflow)
        self.assertIn("v4-acceptance.md", workflow)
        self.assertIn("v4.5-acceptance.md", workflow)
        self.assertIn("v4.6-acceptance.md", workflow)
        self.assertIn("v4.9-acceptance.md", workflow)
        self.assertIn("v4.10-acceptance.md", workflow)
        self.assertIn("v4.11-acceptance.md", workflow)
        self.assertIn("v4.12-acceptance.md", workflow)
        self.assertIn("v4.13-acceptance.md", workflow)
        self.assertIn("v4.14-acceptance.md", workflow)
        self.assertIn("v4.15-acceptance.md", workflow)
        self.assertIn("consumer-pilot.md", workflow)
        self.assertIn("state-equivalence.md", workflow)
        self.assertIn("maturity-evolution-plan.zh-CN.md", workflow)
        self.assertIn("generate_release_metadata.py", workflow)
        self.assertIn("dist/SHA256SUMS", workflow)
        self.assertIn("actions/attest@v4", workflow)
        self.assertIn("steps.release-metadata.outputs.sbom", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)

    def test_workflows_use_node24_official_actions_and_governance_exists(self):
        workflows = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / ".github/workflows").glob("*.yml"))
        )
        self.assertNotIn("actions/checkout@v4", workflows)
        self.assertNotIn("actions/setup-python@v5", workflows)
        self.assertNotIn("actions/upload-artifact@v4", workflows)
        self.assertIn("actions/checkout@v7", workflows)
        self.assertIn("actions/setup-python@v7", workflows)
        self.assertIn("actions/upload-artifact@v7", workflows)
        for path in (
            "SECURITY.md",
            "CODE_OF_CONDUCT.md",
            ".github/dependabot.yml",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/ISSUE_TEMPLATE/config.yml",
        ):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_refund_business_case_workflow_proves_positive_and_negative_paths(self):
        workflow = (ROOT / ".github/workflows/refund-business-case.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("refund_business_case.py", workflow)
        self.assertIn("--behavior normal", workflow)
        for behavior in ("wrong-order", "wrong-tenant", "wrong-amount", "skip-eligibility", "duplicate-refund"):
            self.assertIn(behavior, workflow)
        self.assertIn('test "$exit_code" -eq 1', workflow)
        self.assertIn("refund-business-case-evidence", workflow)

    def test_path_variation_workflow_proves_tolerant_and_strict_paths(self):
        workflow = (ROOT / ".github/workflows/path-variation.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("path_variation_case.py", workflow)
        self.assertIn("extra-query", workflow)
        self.assertIn("reordered", workflow)
        self.assertIn("forbidden", workflow)
        self.assertIn('test "$exit_code" -eq 1', workflow)
        self.assertIn("path-variation-evidence", workflow)

    def test_tau2_workflow_pins_external_data_and_gates_measured_quality(self):
        workflow = (ROOT / ".github/workflows/tau2-independent-validation.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("sierra-research/tau2-bench", workflow)
        self.assertIn("v1.0.1", workflow)
        self.assertIn("6d6badb43b716adca31591b0b40e15fd493b49adddaa8e2c47035bb557549257", workflow)
        self.assertIn('"src/agent_regression/contracts.py"', workflow)
        self.assertIn('"src/agent_regression/compare.py"', workflow)
        self.assertIn("tau2_retail_validation.py", workflow)
        self.assertIn("report.json", workflow)
        self.assertIn("sample-traces", workflow)
        self.assertIn("actions/upload-artifact@v7", workflow)


if __name__ == "__main__":
    unittest.main()
