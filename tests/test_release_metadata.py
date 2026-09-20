import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "generate_release_metadata.py"
SPEC = importlib.util.spec_from_file_location("release_metadata", SCRIPT)
release_metadata = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release_metadata)


class ReleaseMetadataTests(unittest.TestCase):
    def test_generates_checksums_and_spdx_for_release_artifacts_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "agent_regression_kit-4.4.0-py3-none-any.whl").write_bytes(b"wheel")
            (root / "agent_regression_kit-4.4.0.tar.gz").write_bytes(b"source")
            (root / "ignore.txt").write_text("ignore", encoding="utf-8")

            checksums, sbom = release_metadata.write_release_metadata(root, "4.4.0")

            checksum_text = checksums.read_text(encoding="utf-8")
            self.assertIn("agent_regression_kit-4.4.0-py3-none-any.whl", checksum_text)
            self.assertIn("agent_regression_kit-4.4.0.tar.gz", checksum_text)
            self.assertNotIn("ignore.txt", checksum_text)
            document = json.loads(sbom.read_text(encoding="utf-8"))
            self.assertEqual("SPDX-2.3", document["spdxVersion"])
            self.assertEqual("4.4.0", document["packages"][0]["versionInfo"])
            self.assertEqual(2, len(document["files"]))
            self.assertTrue(
                all(file["checksums"][0]["algorithm"] == "SHA256" for file in document["files"])
            )

    def test_rejects_empty_artifact_directory_and_invalid_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "at least one"):
                release_metadata.write_release_metadata(root, "4.4.0")
            artifact = root / "package.whl"
            artifact.write_bytes(b"wheel")
            with self.assertRaisesRegex(ValueError, "version"):
                release_metadata.write_release_metadata(root, "bad version")


if __name__ == "__main__":
    unittest.main()
