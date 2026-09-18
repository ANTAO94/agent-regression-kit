"""Safe local workspace manifests and explicit baseline review helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict


_ROOTS = (".agent-regression", "baselines", "work", "outputs")
_IGNORED_PARTS = {".git", ".venv", "__pycache__", "build", "dist"}


def _is_ignored(parts: tuple[str, ...]) -> bool:
    """Skip repository-generated environments and build trees."""

    return any(
        part in _IGNORED_PARTS
        or part == "venv"
        or part.endswith("-venv")
        or part.endswith(".venv")
        for part in parts
    )


def _role(relative: str) -> str:
    first = relative.split("/", 1)[0]
    if first == ".agent-regression":
        return "policy"
    if first == "baselines":
        return "baseline"
    if first == "work":
        return "candidate-or-run"
    if first == "outputs":
        return "report"
    return "artifact"


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_workspace_manifest(directory: str | Path = ".") -> Dict[str, Any]:
    """Inventory evidence/config files without embedding their contents.

    Only the conventional policy, baseline, work and output roots are
    included. Paths stay relative to the selected workspace and the manifest
    contains file size and SHA-256 only, so the local Viewer can review
    provenance without automatically reading Trace payloads.
    """

    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"workspace directory not found: {directory}")
    files = []
    skipped = []
    for top_level in _ROOTS:
        base = root / top_level
        if not base.exists():
            continue
        if not base.is_dir():
            skipped.append({"source": top_level, "reason": "not a directory"})
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if _is_ignored(path.relative_to(root).parts):
                continue
            try:
                files.append(
                    {
                        "source": relative,
                        "role": _role(relative),
                        "size": path.stat().st_size,
                        "sha256": _digest(path),
                    }
                )
            except (OSError, UnicodeError) as exc:
                skipped.append(
                    {"source": relative, "reason": f"unable to fingerprint ({type(exc).__name__})"}
                )
    return {
        "schema_version": "0.1",
        "report_type": "agent_workspace_manifest",
        "workspace_name": root.name or ".",
        "roots": list(_ROOTS),
        "file_count": len(files),
        "files": files,
        "skipped": skipped,
    }
