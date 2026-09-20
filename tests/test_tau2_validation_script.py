import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "tau2_retail_validation.py"
SPEC = importlib.util.spec_from_file_location("tau2_retail_validation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
TELECOM_SCRIPT = ROOT / "examples" / "tau2_telecom_validation.py"
TELECOM_SPEC = importlib.util.spec_from_file_location("tau2_telecom_validation", TELECOM_SCRIPT)
assert TELECOM_SPEC is not None and TELECOM_SPEC.loader is not None
TELECOM_MODULE = importlib.util.module_from_spec(TELECOM_SPEC)
TELECOM_SPEC.loader.exec_module(TELECOM_MODULE)


class Tau2ValidationScriptTests(unittest.TestCase):
    def test_results_are_bound_to_the_source_manifest_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results.json"
            results.write_text('{"model":"o4-mini"}\n', encoding="utf-8")
            observed = MODULE.sha256_file(results)
            bound = MODULE.bind_results_to_source(results, {"sha256": observed})
            self.assertEqual(observed, bound["results_sha256"])
            with self.assertRaisesRegex(ValueError, "does not match source manifest"):
                MODULE.bind_results_to_source(results, {"sha256": "0" * 64})

    def test_unpinned_source_can_be_used_for_in_memory_fixture_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "fixture.json"
            results.write_text("{}", encoding="utf-8")
            bound = MODULE.bind_results_to_source(results, {"tag": "fixture"})
            self.assertIsNone(bound["manifest_sha256"])
            self.assertEqual(64, len(bound["results_sha256"]))

    def test_telecom_validator_rejects_a_mismatched_result_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "telecom.json"
            results.write_text('{"domain":"telecom"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match source manifest"):
                TELECOM_MODULE.bind_results_to_source(results, {"sha256": "0" * 64})


if __name__ == "__main__":
    unittest.main()
