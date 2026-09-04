"""
Materiality / significance layer (Agent 4) — the 2x2 that makes Agent 4 speak a
controller's language.

Two DISTINCT axes, deliberately not conflated:

  MATERIALITY (relative size) — is the variance big enough to matter? A DUAL
    threshold, both named in the output:
      - absolute floor, scaled to the total (big money matters regardless of %),
      - relative %, gated by a small absolute minimum (so 40% off on a tiny line
        doesn't scream, but 2% off on a huge base does).

  SIGNIFICANCE (statistical) — is the variance beyond this line's OWN historical
    noise band? Tested on the line's VARIANCE SERIES (not raw actuals): a line
    that is reliably EUR30k over budget has a stable variance, and this month's
    EUR32k is not a break; a line that never moved more than EUR5k IS broken at
    EUR40k. This reuses anomaly_significance_check — the THIRD independent
    consumer of the shared significance library (after covenant drift and
    event-study CAAR), which is the platform thesis at work.

Crossed, they give the 2x2:
  material + significant     -> TOP_PRIORITY      (look now)
  material + not significant -> EXPECTED_VOLATILITY (big, but this line always swings)
  immaterial + significant   -> EARLY_WARNING      (small money, but a real break from
                                                    pattern — the leading indicator naive
                                                    tools miss; a first-class output here)
  immaterial + not significant -> NOISE

Seasonality: significance is period-aware WHEN same-period history allows (this
December vs. past Decembers); otherwise it degrades honestly to a full-history
test (labelled) or to "not computable" — never a false alarm on a seasonal peak.

Multiple testing: scanning many lines inflates false positives, so the
significance threshold tightens with the number of lines scanned (mirrors Agent 3).
"""

from __future__ import annotations

import math
import os

if os.environ.get("AGENT_STATS_VIA_MCP") == "1":
    from mcp_server.client import anomaly_significance_check
else:
    from tools.statistical_checks import anomaly_significance_check

# Default thresholds (named in output so a reviewer sees them).
_REL_PCT = 0.10                # 10% of the line's own budget
_ABS_FLOOR_FRAC = 0.005        # 0.5% of total budget = "big money" floor
_ABS_MIN_FRAC = 0.0005         # 0.05% of total budget = "not trivial" floor for the rel path
_MIN_OBS = 6                   # significance needs at least this many prior points
_BASE_Z = 3.5                  # base modified-z flag


def _is_material(variance_cents: int, line_budget_cents: int, total_budget_cents: int,
                 rel_pct=_REL_PCT, abs_floor_frac=_ABS_FLOOR_FRAC,
                 abs_min_frac=_ABS_MIN_FRAC) -> dict:
    """Dual-threshold materiality. Material if it is big money OR (proportionally
    big AND not trivially small). Returns the decision plus the gates it cleared."""
    v = abs(variance_cents)
    abs_floor = abs(int(abs_floor_frac * total_budget_cents))
    abs_min = abs(int(abs_min_frac * total_budget_cents))
    rel = (v / abs(line_budget_cents)) if line_budget_cents else 0.0

    clears_big_money = v >= abs_floor
    clears_relative = (rel >= rel_pct) and (v >= abs_min)
    material = clears_big_money or clears_relative

    return {
        "material": material,
        "relative_pct": round(rel * 100, 2),
        "abs_floor_cents": abs_floor, "abs_min_cents": abs_min,
        "cleared": ("big-money (abs floor)" if clears_big_money
                    else "relative % (non-trivial)" if clears_relative
                    else "none"),
        "thresholds": {"rel_pct": rel_pct, "abs_floor_frac": abs_floor_frac,
                       "abs_min_frac": abs_min_frac},
    }


def _significance(variance_history_cents: list[int], this_variance_cents: int,
                  period=None, period_history: list[tuple] | None = None,
                  n_lines_scanned: int = 1) -> dict:
    """
    Is this period's variance a break from the line's own variance pattern?
    Tests the VARIANCE series via the shared anomaly_significance_check.

    period_history: optional list of (period_key, variance_cents) so we can build a
    SAME-PERIOD series (past Decembers) when `period` is given — period-aware.
    Falls back to full history, then to "not computable", honestly labelled.
    """
    # multiple-testing: tighten the z flag as more lines are scanned (Bonferroni-ish
    # on the tail — add ~the normal quantile growth). Simple, documented, monotone.
    z_flag = _BASE_Z + (math.log(max(1, n_lines_scanned)) if n_lines_scanned > 1 else 0.0)

    # Build the series to test against, preferring same-period history.
    series = None
    period_aware = False
    if period is not None and period_history:
        same = [v for (pk, v) in period_history if pk == period]
        if len(same) >= _MIN_OBS:
            series = same + [this_variance_cents]
            period_aware = True
    if series is None:
        if len(variance_history_cents) >= _MIN_OBS:
            series = list(variance_history_cents) + [this_variance_cents]
        else:
            return {"significant": None, "period_aware": False,
                    "reason": f"insufficient history (<{_MIN_OBS} prior points) — "
                              f"significance not computable",
                    "z_flag": round(z_flag, 3)}

    res = anomaly_significance_check([float(x) for x in series], min_obs=_MIN_OBS,
                                     z_flag=z_flag)
    return {
        "significant": res.get("significant"),
        "modified_z": res.get("modified_z"),
        "z_flag": round(z_flag, 3),
        "period_aware": period_aware,
        "basis": ("same-period (seasonal)" if period_aware else "full history"),
        "n_lines_scanned": n_lines_scanned,
    }


def classify_variance(line_result: dict, line_budget_cents: int,
                      total_budget_cents: int,
                      variance_history_cents: list[int] | None = None,
                      period=None, period_history: list[tuple] | None = None,
                      n_lines_scanned: int = 1) -> dict:
    """
    Place one decomposed line into the materiality x significance 2x2.

    line_result: the dict from decompose_line (needs total_variance_cents, name).
    Returns the quadrant, both axes' detail, and a one-line triage reason.
    """
    variance = line_result["total_variance_cents"]
    mat = _is_material(variance, line_budget_cents, total_budget_cents)
    sig = _significance(variance_history_cents or [], variance,
                        period=period, period_history=period_history,
                        n_lines_scanned=n_lines_scanned)

    material = mat["material"]
    significant = sig["significant"]

    if significant is None:
        # significance not computable -> materiality-only, labelled honestly
        quadrant = "MATERIAL_SIG_NC" if material else "IMMATERIAL_SIG_NC"
        reason = ("material by size; significance not computable "
                  f"({sig.get('reason','')})" if material
                  else "immaterial; significance not computable")
    elif material and significant:
        quadrant = "TOP_PRIORITY"
        reason = "material AND a significant break from this line's pattern — look now"
    elif material and not significant:
        quadrant = "EXPECTED_VOLATILITY"
        reason = "material in size, but within this line's normal swing — expected volatility"
    elif not material and significant:
        quadrant = "EARLY_WARNING"
        reason = ("immaterial in euros, but a significant break from pattern — "
                  "leading indicator, watch this")
    else:
        quadrant = "NOISE"
        reason = "neither material nor a break from pattern"

    return {
        "name": line_result.get("name"),
        "total_variance_cents": variance,
        "favourable": line_result.get("favourable"),
        "quadrant": quadrant,
        "reason": reason,
        "materiality": mat,
        "significance": sig,
        "computed_by": "classify_variance (python; significance via shared library)",
    }
