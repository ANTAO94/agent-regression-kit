"""Serve the bundled local Trace Inspector and configuration viewer."""

from __future__ import annotations

from functools import partial
import http.server
from pathlib import Path
import socketserver
import sys
import webbrowser


class ViewerNotFoundError(ValueError):
    """Raised when the static viewer assets are not available."""


def find_viewer_directory(directory: str | Path | None = None) -> Path:
    """Resolve viewer assets for a checkout, editable install, or wheel."""
    if directory is not None:
        # An explicit path is a user decision. Do not silently serve a
        # different checkout or installed copy when it is misspelled.
        candidates = [Path(directory).expanduser()]
    else:
        package_root = Path(__file__).resolve().parents[2]
        candidates = [
            package_root / "viewer",
            Path.cwd() / "viewer",
            Path(sys.prefix) / "share" / "agent-regression-kit" / "viewer",
        ]
        if sys.base_prefix != sys.prefix:
            candidates.append(
                Path(sys.base_prefix) / "share" / "agent-regression-kit" / "viewer"
            )

    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if all((resolved / asset).is_file() for asset in ("index.html", "config.html", "reports.html")):
            return resolved

    searched = ", ".join(str(path.resolve()) for path in candidates)
    raise ViewerNotFoundError(
        "viewer assets were not found; searched: " + searched
    )


def serve_viewer(
    directory: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
) -> str:
    """Serve the static viewer until interrupted and return its URL.

    The default bind address is loopback so the viewer is not exposed on a
    network interface by accident. ``port=0`` is supported for tests and
    embedded tooling that need an ephemeral port.
    """
    if not 0 <= port <= 65535:
        raise ValueError("viewer port must be between 0 and 65535")
    root = find_viewer_directory(directory)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(root))

    class ViewerServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    with ViewerServer((host, port), handler) as server:
        actual_port = int(server.server_address[1])
        url = f"http://{host}:{actual_port}/index.html"
        print(f"Agent Regression Kit viewer: {url}", flush=True)
        print("Press Ctrl-C to stop.", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nViewer stopped.", flush=True)
    return url
