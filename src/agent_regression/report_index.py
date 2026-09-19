"""Build a safe, relative-path index for local regression reports."""

from __future__ import annotations

import json
import fnmatch
from pathlib import Path
from typing import Any, Dict, Sequence

from .history import _classify, _label, _metrics
from .model import SUPPORTED_SCHEMA_VERSION
from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


_SUMMARY_FIELDS = (
    "difference_count",
    "blocking_difference_count",
    "case_count",
    "passed_case_count",
    "failed_case_count",
    "coverage_percent",
    "business_branch_coverage_percent",
    "latest_label",
)


def build_report_index(
    report_dir: str | Path,
    *,
    pattern: str = "*.json",
    required_reports: Sequence[str] = (),
    redaction_policy: RedactionPolicy | None = None,
) -> Dict[str, Any]:
    """Index recognized JSON reports without embedding report contents.

    The index is intentionally presentation-oriented: it keeps only relative
    paths, status, report type, labels, and numeric summaries. The Viewer can
    use it to navigate a report directory without receiving secrets or
    duplicating the Python comparison logic.
    """
    root = Path(report_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"report directory not found: {report_dir}")
    normalized_required = []
    for required in required_reports:
        if not isinstance(required, str) or not required.strip():
            raise ValueError("required report paths must be non-empty strings")
        required_path = Path(required)
        if required_path.is_absolute() or ".." in required_path.parts:
            raise ValueError("required report paths must stay inside report-dir")
        normalized_required.append(required.replace("\\", "/"))
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    entries = []
    skipped = []
    invalid_report_count = 0
    for path in sorted(root.rglob(pattern)):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            skipped.append(
                {
                    "source": relative,
                    "reason": f"invalid JSON at line {exc.lineno}, column {exc.colno}",
                }
            )
            continue
        except (OSError, UnicodeError) as exc:
            skipped.append(
                {
                    "source": relative,
                    "reason": active_redaction.redact(
                        f"unable to read report ({type(exc).__name__})"
                    ),
                }
            )
            continue
        if not isinstance(value, dict):
            skipped.append({"source": relative, "reason": "report must be a JSON object"})
            continue
        if value.get("report_type") == "agent_report_index":
            # The generated index may live in the same output directory. It is
            # an inventory, not another regression result, so do not surface
            # it as a skipped report when the command is run twice (JSON + MD).
            continue
        if (
            value.get("schema_version") == SUPPORTED_SCHEMA_VERSION
            and isinstance(value.get("events"), list)
            and isinstance(value.get("run_id"), str)
        ):
            # Raw AgentTrace inputs are evidence sources, not derived reports.
            # They commonly sit beside compare output in a CI artifact folder.
            continue
        # History is a derived report rather than an input point, so it is
        # intentionally not part of history._classify(). It is still a
        # first-class CI artifact and should appear in the handoff index.
        if value.get("report_type") == "agent_history":
            report_type = "agent_history"
        else:
            report_type = _classify(value)
        if report_type is None:
            skipped.append({"source": relative, "reason": "unrecognized regression report"})
            continue
        if not isinstance(value.get("passed"), bool):
            invalid_report_count += 1
            skipped.append(
                {
                    "source": relative,
                    "reason": "recognized report passed must be a boolean",
                }
            )
            continue
        if report_type == "agent_history":
            metrics = {
                key: value[key]
                for key in ("point_count", "passed_point_count", "failed_point_count", "regression_count")
                if isinstance(value.get(key), (int, float)) and not isinstance(value.get(key), bool)
            }
        else:
            metrics = _metrics(value, report_type)
        summary = {
            key: value[key]
            for key in _SUMMARY_FIELDS
            if key in value and isinstance(value[key], (str, int, float, bool))
        }
        entries.append(
            {
                "source": relative,
                "label": active_redaction.redact(_label(value, path)),
                "report_type": report_type,
                "passed": value["passed"],
                "metrics": metrics,
                "summary": summary,
            }
        )
    missing_reports = [
        required
        for required in normalized_required
        if not any(fnmatch.fnmatch(entry["source"], required) for entry in entries)
    ]
    return {
        "schema_version": "0.1",
        "report_type": "agent_report_index",
        # Do not put an absolute local path into a CI artifact. The Viewer
        # only needs a human-readable directory name; every navigable source
        # remains relative to this directory.
        "source_dir": root.name or ".",
        "pattern": active_redaction.redact(pattern),
        "passed": (
            bool(entries)
            and invalid_report_count == 0
            and all(entry["passed"] for entry in entries)
            and not missing_reports
        ),
        "required_reports": normalized_required,
        "missing_reports": missing_reports,
        "report_count": len(entries),
        "passed_count": sum(1 for entry in entries if entry["passed"]),
        "failed_count": sum(1 for entry in entries if not entry["passed"]),
        "entries": entries,
        "skipped": skipped,
    }
