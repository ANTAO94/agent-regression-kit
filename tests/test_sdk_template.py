import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from agent_regression import (
    AdapterSpec,
    AsyncCallableAgentAdapter,
    CallableAgentAdapter,
    initialize_adapter_template,
)
from agent_regression.cli import main


ROOT = Path(__file__).resolve().parents[1]


class AdapterSdkTemplateTests(unittest.TestCase):
    def test_adapter_spec_builds_sync_and_async_adapters_with_one_identity(self):
        spec = AdapterSpec("orders", version="2.0.0", metadata={"team": "eval"})
        sync = spec.build_sync(lambda request, context: context.final_answer(str(request)))

        async def runner(request, context):
            context.final_answer(str(request))

        asynchronous = spec.build_async(runner)
        self.assertIsInstance(sync, CallableAgentAdapter)
        self.assertIsInstance(asynchronous, AsyncCallableAgentAdapter)
        self.assertEqual(sync.identity, asynchronous.identity)
        self.assertEqual("eval", sync.identity["team"])

    def test_adapter_spec_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            AdapterSpec(" ")

    def test_both_template_is_runnable_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = initialize_adapter_template(root, name="orders", mode="both")
            self.assertEqual(["adapter.py", "tests/test_adapter_contract.py", "README.md"], result["created"])
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(ROOT / "src")
            completed = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                cwd=str(root),
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)

    def test_adapter_init_cli_preserves_existing_template_without_force(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    0,
                    main(["adapter-init", "--directory", str(root), "--name", "orders", "--mode", "async"]),
                )
            adapter = root / "adapter.py"
            adapter.write_text("custom\n", encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    0,
                    main(["adapter-init", "--directory", str(root), "--name", "orders", "--mode", "async"]),
                )
            self.assertEqual("custom\n", adapter.read_text(encoding="utf-8"))
            self.assertEqual(
                ["adapter.py", "tests/test_adapter_contract.py", "README.md"],
                json.loads(output.getvalue())["skipped"],
            )

    def test_project_scaffold_includes_trace_preflight_before_compare(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with redirect_stdout(StringIO()):
                self.assertEqual(0, main(["init", "--directory", str(root)]))
            workflow = (root / ".github/workflows/agent-regression.yml").read_text(encoding="utf-8")
            self.assertIn("agent-regression check --config .agent-regression/config.json", workflow)


if __name__ == "__main__":
    unittest.main()
