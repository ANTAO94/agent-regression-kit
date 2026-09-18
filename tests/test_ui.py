import tempfile
import unittest
from pathlib import Path

from agent_regression.cli import build_parser
from agent_regression.ui import ViewerNotFoundError, find_viewer_directory, serve_viewer


ROOT = Path(__file__).resolve().parents[1]


class ViewerTests(unittest.TestCase):
    def test_ui_parser_defaults_to_loopback_viewer_server(self):
        args = build_parser().parse_args(["ui"])
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8765)
        self.assertFalse(args.open_browser)

    def test_finds_viewer_assets_in_the_repository(self):
        self.assertEqual(
            find_viewer_directory(ROOT / "viewer"),
            (ROOT / "viewer").resolve(),
        )
        self.assertTrue((ROOT / "viewer" / "reports.html").is_file())

    def test_missing_viewer_directory_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ViewerNotFoundError, "viewer assets were not found"):
                find_viewer_directory(directory)

    def test_viewer_rejects_invalid_port_before_starting_server(self):
        with self.assertRaisesRegex(ValueError, "between 0 and 65535"):
            serve_viewer(ROOT / "viewer", port=65536)
