"""Small dependency-free statistical helpers for evidence reports."""

from __future__ import annotations

from statistics import NormalDist
from typing import Dict


def wilson_interval(
    successes: int,
    total: int,
    *,
    confidence: float = 0.95,
) -> Dict[str, float] | None:
    """Return a Wilson score interval for a binomial proportion.

    The helper is intentionally small and dependency-free. It is used to
    communicate finite-sample uncertainty; it does not turn repeated Agent
    runs into a population-level reliability guarantee.
    """
    if not isinstance(successes, int) or not isinstance(total, int):
        raise TypeError("successes and total must be integers")
    if successes < 0 or total < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between zero and one")
    if total == 0:
        return None
    z = NormalDist().inv_cdf((1.0 + confidence) / 2.0)
    proportion = successes / total
    denominator = 1.0 + (z * z / total)
    center = (proportion + (z * z / (2.0 * total))) / denominator
    margin = (
        z
        * ((proportion * (1.0 - proportion) / total) + (z * z / (4.0 * total * total)))
        ** 0.5
        / denominator
    )
    return {
        "confidence": confidence,
        "low": max(0.0, center - margin),
        "high": min(1.0, center + margin),
    }


__all__ = ["wilson_interval"]
