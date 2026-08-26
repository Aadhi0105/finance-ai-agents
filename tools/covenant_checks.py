"""
Covenant check tools for Agent 2 (monitoring).

This checkpoint: `threshold_check` only — the deterministic binary test "is the
covenant crossed?". Per spec §3.3 MCP boundary, threshold_check is
covenant-specific and stays LOCAL (never lifted to the shared MCP server). The
statistical checks that DO get extracted — anomaly_significance_check,
drift_check, breach_probability — arrive at later checkpoints.

Governing principle carries from Agent 1: the LLM never does the math. The breach
decision is pure Python; the model only triages the flags afterward.
"""

from __future__ import annotations


def threshold_check(value: float, threshold: float, direction: str) -> dict:
    """
    Deterministic covenant test.

    direction "below": covenant requires value to stay BELOW threshold
                       -> breached when value > threshold.
    direction "above": covenant requires value to stay ABOVE threshold
                       -> breached when value < threshold.

    `margin` is signed so it is comparable across cycles:
      > 0  => in breach, by this much (used to detect WIDENING vs IMPROVING)
      <= 0 => headroom (not breached)
    """
    if direction == "below":
        margin = value - threshold
        breached = value > threshold
    elif direction == "above":
        margin = threshold - value
        breached = value < threshold
    else:
        return {"error": f"unknown direction '{direction}'", "breached": None}

    return {
        "breached": breached,
        "margin": round(margin, 6),
        "value": value,
        "threshold": threshold,
        "direction": direction,
        "computed_by": "threshold_check (python, local)",
    }
