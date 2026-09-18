"""Configuration loading for project-level comparison commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .contracts import ContractPolicy

def _relative_to_project(config_path: Path, value: str) -> str:
    """Resolve scaffold paths relative to the project root."""
    project_root = (
        config_path.parent.parent
        if config_path.parent.name == ".agent-regression"
        else config_path.parent
    )
    return str((project_root / value).resolve())


def _load_config(path: str | Path, required_paths: tuple[str, ...]) -> Dict[str, Any]:
    """Load and validate a comparison config with the requested path keys."""
    config_path = Path(path).resolve()
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"config file is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError("config must contain a JSON object")

    result = dict(value)
    for key in required_paths:
        configured = result.get(key)
        if not isinstance(configured, str) or not configured.strip():
            raise ValueError(f"config.{key} must be a non-empty string")
        result[key] = _relative_to_project(config_path, configured)

    if "report" in result:
        if not isinstance(result["report"], str) or not result["report"].strip():
            raise ValueError("config.report must be a non-empty string")
        result["report"] = _relative_to_project(config_path, result["report"])

    if "format" in result and result["format"] not in {"json", "junit", "markdown"}:
        raise ValueError("config.format must be 'json', 'junit', or 'markdown'")
    if "final_answer_mode" in result and result["final_answer_mode"] not in {"exact", "claims-only"}:
        raise ValueError("config.final_answer_mode must be 'exact' or 'claims-only'")
    for key in ("allow_categories", "allow_paths", "secret_values"):
        if key in result and (
            not isinstance(result[key], list)
            or not all(isinstance(item, str) for item in result[key])
        ):
            raise ValueError(f"config.{key} must be an array of strings")
    if "required_reports" in result:
        if (
            not isinstance(result["required_reports"], list)
            or not all(isinstance(item, str) and item.strip() for item in result["required_reports"])
        ):
            raise ValueError("config.required_reports must be an array of non-empty strings")
    if "contract" in result:
        result["contract"] = ContractPolicy.from_dict(result["contract"]).to_dict()
    return result


def load_compare_config(path: str | Path) -> Dict[str, Any]:
    """Load a single-trace compare config file."""
    return _load_config(path, ("baseline", "candidate"))


def load_batch_compare_config(path: str | Path) -> Dict[str, Any]:
    """Load a directory-based batch compare config file."""
    return _load_config(path, ("baseline_dir", "candidate_dir"))
