import configparser
import unittest
from pathlib import Path

from agent_regression import __version__
from agent_regression.cli import VERSION


ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_public_and_cli_versions_share_one_value(self):
        self.assertEqual(VERSION, __version__)
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_setup_metadata_reads_the_single_version_source(self):
        parser = configparser.ConfigParser()
        parser.read(ROOT / "setup.cfg", encoding="utf-8")
        self.assertEqual(
            parser.get("metadata", "version"),
            "attr: agent_regression.version.__version__",
        )
