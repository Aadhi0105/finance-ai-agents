"""
Agent 4 output — the variance waterfall (signature visual, fourth showcase tile)
and the two output modes.

The waterfall bridges Budget -> driver/line steps -> Actual, favourable steps one
colour and adverse another, with any unexplained residual as an explicit bar. It
ALWAYS ties (penny-reconciliation), so the first thing a controller checks is the
one thing guaranteed correct. Rendered as inline SVG (no chart library), matching
the showcase's approach, so it drops straight into the fourth tile.

Two modes, mirroring Agent 2's exception-report + full-state split:
  - board_pack     : full top-down hierarchy + waterfall + commentary (+ reforecast).
  - exception_view : only the lines that are material-and-significant / early-warning.
"""

from __future__ import annotations

from agent4.decomposition import euros
from agent4.commentary import build_registry, compose, reconcile

_FAV = "#2e7d32"      # favourable (green)
_ADV = "#c62828"      # adverse (red)
_ANCHOR = "#455a64"   # budget/actual anchor bars
_RESID = "#f9a825"    # residual (amber) — always shown when non-zero


def _steps_from_tree(tree: dict) -> list[dict]:
    """Top-level children become the waterfall steps, by PROFIT IMPACT (so a cost
    overrun steps profit down). Order: as in the tree."""
    steps = []
    for c in tree.get("children", []):
        steps.append({"name": c["name"], "impact": c["profit_impact_cents"],
                      "favourable": c["favourable"]})
    return steps


def variance_waterfall_svg(tree: dict, width: int = 720, height: int = 360) -> str:
    """Budget -> profit-impact steps -> Actual, as inline SVG. Ties exactly."""
    budget = tree["budget_cents"]
    actual = tree["actual_cents"]
    steps = _steps_from_tree(tree)

    # residual at root level (should be 0 for a clean tree; shown if not)
    resid = tree.get("residual_cents", 0) or 0

    bars = [("Budget", budget, _ANCHOR, "anchor")]
    running = budget
    for s in steps:
        bars.append((s["name"], s["impact"], _FAV if s["favourable"] else _ADV, "step"))
        running += s["impact"]
    if resid:
        bars.append(("Residual", resid, _RESID, "step"))
        running += resid
    bars.append(("Actual", actual, _ANCHOR, "anchor"))

    # scale
    pad_l, pad_r, pad_t, pad_b = 60, 20, 30, 60
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    vals_span = [budget, actual, running]
    cum = budget
    for s in steps:
        vals_span.append(cum + s["impact"]); cum += s["impact"]
    lo = min(0, min(vals_span))
    hi = max(vals_span)
    rng = (hi - lo) or 1

    def y(v):
        return pad_t + plot_h * (1 - (v - lo) / rng)

    n = len(bars)
    slot = plot_w / n
    bw = slot * 0.6

    svg = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
           f'font-family="system-ui, sans-serif" font-size="11">']
    svg.append(f'<line x1="{pad_l}" y1="{y(0)}" x2="{width-pad_r}" y2="{y(0)}" '
               f'stroke="#cccccc" stroke-width="1"/>')

    cum = 0
    for i, (label, val, colour, kind) in enumerate(bars):
        x = pad_l + i * slot + (slot - bw) / 2
        if kind == "anchor":
            top = y(max(0, val)); h = abs(y(val) - y(0))
            svg.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" '
                       f'height="{h:.1f}" fill="{colour}"/>')
            cum = val
        else:
            start = cum
            end = cum + val
            top = y(max(start, end)); h = abs(y(start) - y(end)) or 1
            svg.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" '
                       f'height="{h:.1f}" fill="{colour}"/>')
            # connector line from prior running level
            svg.append(f'<line x1="{x - (slot-bw):.1f}" y1="{y(start):.1f}" '
                       f'x2="{x:.1f}" y2="{y(start):.1f}" stroke="#bbbbbb" '
                       f'stroke-dasharray="2,2"/>')
            cum = end
        # label + value
        cx = x + bw / 2
        svg.append(f'<text x="{cx:.1f}" y="{height-pad_b+16:.1f}" text-anchor="middle" '
                   f'fill="#444">{label}</text>')
        svg.append(f'<text x="{cx:.1f}" y="{height-pad_b+30:.1f}" text-anchor="middle" '
                   f'fill="#777" font-size="9">{euros(val)}</text>')

    svg.append(f'<text x="{pad_l}" y="18" fill="#333" font-size="13" '
               f'font-weight="600">{tree["name"]} variance bridge</text>')
    svg.append('</svg>')
    return "\n".join(svg)


def _flatten(tree: dict, out: list, depth=0):
    out.append({"name": tree["name"], "depth": depth,
                "variance_cents": tree["total_variance_cents"],
                "favourable": tree["favourable"], "quadrant": tree.get("quadrant")})
    for c in tree.get("children", []):
        _flatten(c, out, depth + 1)


def board_pack(tree: dict, persistence_by_line=None, reforecast_by_line=None) -> dict:
    """Full board pack: hierarchy, waterfall, reconciled commentary."""
    registry = build_registry(tree, reforecast_by_line)
    claims = compose(tree, persistence_by_line, reforecast_by_line)
    gate = reconcile(claims, registry)
    if not gate["passed"]:
        raise ValueError(f"commentary failed reconciliation: {gate['violations']}")
    rows = []
    _flatten(tree, rows)
    return {"mode": "board_pack", "hierarchy": rows,
            "waterfall_svg": variance_waterfall_svg(tree),
            "commentary": claims, "reconciliation": gate,
            "reconciles": tree["reconciles"]}


_EXCEPTION_QUADRANTS = {"TOP_PRIORITY", "EARLY_WARNING", "MATERIAL_SIG_NC"}


def exception_view(tree: dict, persistence_by_line=None, reforecast_by_line=None) -> dict:
    """Only the lines that matter: material-and-significant / early-warning."""
    registry = build_registry(tree, reforecast_by_line)
    claims = compose(tree, persistence_by_line, reforecast_by_line,
                     only_quadrants=_EXCEPTION_QUADRANTS)
    gate = reconcile(claims, registry)
    if not gate["passed"]:
        raise ValueError(f"commentary failed reconciliation: {gate['violations']}")
    rows = []
    _flatten(tree, rows)
    exceptions = [r for r in rows if r["quadrant"] in ("TOP_PRIORITY", "EARLY_WARNING")]
    return {"mode": "exception_view", "exceptions": exceptions,
            "commentary": claims, "reconciliation": gate}
