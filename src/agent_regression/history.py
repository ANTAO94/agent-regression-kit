"""Long-term Agent regression history and trend aggregation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .redaction import DEFAULT_REDACTION_POLICY, RedactionPolicy


TREND_METRICS = (
    "pass_rate",
    "claims_match_rate",
    "tool_error_rate",
    "path_variant_count",
    "coverage_percent",
    "difference_count",
    "blocking_difference_count",
)


def _number(value: Any) -> float | int | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _classify(report: Mapping[str, Any]) -> str | None:
    explicit = report.get("report_type")
    if explicit in {"agent_stability", "agent_compare", "agent_batch", "agent_coverage"}:
        return str(explicit)
    if "pass_rate" in report and "claims_match_rate" in report:
        return "agent_stability"
    if "candidate_run_id" in report and "blocking_difference_count" in report:
        return "agent_compare"
    if "passed_case_count" in report and "case_count" in report:
        return "agent_batch"
    if "coverage_percent" in report and "unique_path_count" in report:
        return "agent_coverage"
    return None


def _label(report: Mapping[str, Any], source: Path) -> str:
    for key in ("label", "history_label", "run_id", "candidate_run_id", "baseline_run_id"):
        value = report.get(key)
        if isinstance(value, str) and value:
            return value
    metadata = report.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("history_label"), str):
        return metadata["history_label"]
    return source.stem


def _metrics(report: Mapping[str, Any], report_type: str) -> Dict[str, float | int]:
    result: Dict[str, float | int] = {}
    if report_type == "agent_stability":
        keys = (
            "pass_rate",
            "claims_match_rate",
            "tool_error_rate",
            "path_variant_count",
        )
    elif report_type == "agent_compare":
        keys = ("difference_count", "blocking_difference_count")
    elif report_type == "agent_batch":
        keys = ("difference_count", "blocking_difference_count")
        case_count = report.get("case_count", 0)
        passed_cases = report.get("passed_case_count", 0)
        if isinstance(case_count, int) and case_count > 0 and isinstance(passed_cases, int):
            result["pass_rate"] = round(passed_cases / case_count, 6)
        result["difference_count"] = sum(
            int(case.get("blocking_difference_count", 0))
            for case in report.get("cases", [])
            if isinstance(case, dict)
        ) or int(report.get("failed_case_count", 0))
        result["blocking_difference_count"] = result["difference_count"]
        keys = ()
    elif report_type == "agent_coverage":
        keys = ("coverage_percent", "business_branch_coverage_percent")
    else:
        keys = ()
    for key in keys:
        value = _number(report.get(key))
        if value is not None:
            result[key] = value
    if report_type == "agent_compare" and "pass_rate" not in result:
        result["pass_rate"] = 1.0 if report.get("passed") else 0.0
    return result


@dataclass(frozen=True)
class HistoryPoint:
    """One normalized historical report."""

    ordinal: int
    label: str
    source: str
    report_type: str
    passed: bool
    metrics: Dict[str, float | int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "label": self.label,
            "source": self.source,
            "report_type": self.report_type,
            "passed": self.passed,
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class HistoryReport:
    """Aggregate report for a directory of versioned regression evidence."""

    source_dir: str
    points: List[HistoryPoint]
    skipped: List[Dict[str, str]]

    @property
    def point_count(self) -> int:
        return len(self.points)

    @property
    def passed_point_count(self) -> int:
        return sum(1 for point in self.points if point.passed)

    @property
    def failed_point_count(self) -> int:
        return self.point_count - self.passed_point_count

    @property
    def latest(self) -> HistoryPoint | None:
        return self.points[-1] if self.points else None

    @property
    def regression_count(self) -> int:
        return self.failed_point_count

    @property
    def passed(self) -> bool:
        # The history command is a current-state gate: old failures stay
        # visible in the report, while the exit code follows the latest point.
        return bool(self.latest and self.latest.passed)

    @property
    def metric_trends(self) -> Dict[str, Dict[str, float | int]]:
        trends: Dict[str, Dict[str, float | int]] = {}
        for metric in TREND_METRICS:
            values = [point.metrics[metric] for point in self.points if metric in point.metrics]
            if not values:
                continue
            first = values[0]
            latest = values[-1]
            trends[metric] = {
                "first": first,
                "latest": latest,
                "delta": round(latest - first, 6),
                "min": min(values),
                "max": max(values),
            }
        return trends

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "0.1",
            "report_type": "agent_history",
            "passed": self.passed,
            "source_dir": self.source_dir,
            "point_count": self.point_count,
            "passed_point_count": self.passed_point_count,
            "failed_point_count": self.failed_point_count,
            "regression_count": self.regression_count,
            "latest_label": self.latest.label if self.latest else None,
            "points": [point.to_dict() for point in self.points],
            "metric_trends": self.metric_trends,
            "skipped": list(self.skipped),
        }


def build_history_report(
    report_dir: str | Path,
    *,
    pattern: str = "*.json",
    redaction_policy: RedactionPolicy | None = None,
) -> HistoryReport:
    """Load recognized reports in stable path order and aggregate their trends."""
    root = Path(report_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"history report directory not found: {report_dir}")
    points: List[HistoryPoint] = []
    skipped: List[Dict[str, str]] = []
    active_redaction = redaction_policy or DEFAULT_REDACTION_POLICY
    for path in sorted(root.rglob(pattern)):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            skipped.append({"source": relative, "reason": active_redaction.redact(str(exc))})
            continue
        if not isinstance(value, dict):
            skipped.append({"source": relative, "reason": "report must be a JSON object"})
            continue
        report_type = _classify(value)
        if report_type is None:
            skipped.append({"source": relative, "reason": "unrecognized regression report"})
            continue
        points.append(
            HistoryPoint(
                ordinal=len(points) + 1,
                label=_label(value, path),
                source=relative,
                report_type=report_type,
                passed=bool(value.get("passed")),
                metrics=_metrics(value, report_type),
            )
        )
    if not points:
        raise ValueError(f"history directory contains no recognized reports: {report_dir}")
    return HistoryReport(
        source_dir=str(root),
        points=points,
        skipped=skipped,
    )
