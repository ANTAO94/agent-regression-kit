import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CiIntegrationTests(unittest.TestCase):
    def test_reusable_action_exposes_the_comparison_policy_controls(self):
        action = (ROOT / ".github/actions/agent-regression/action.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("final-answer-mode:", action)
        self.assertIn("allow-path:", action)
        self.assertIn('args+=(--final-answer-mode "$FINAL_ANSWER_MODE")', action)
        self.assertIn('args+=(--allow-path "$path")', action)


if __name__ == "__main__":
    unittest.main()
