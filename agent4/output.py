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
from agent4.commentary import build_registry, compose_registry, reconcile
from copy import deepcopy
from agent4.hierarchy import validate_result

from xml.sax.saxutils import escape as _xml_escape


def _xml(s) -> str:
    """XML-escape a label for safe injection into SVG text (& < > and quotes)."""
    return _xml_escape(str(s), {'"': "&quot;", "'": "&apos;"})

_FAV = "#2e7d32"      # favourable (green)
_ADV = "#c62828"      # adverse (red)
_ANCHOR = "#455a64"   # budget/actual anchor bars
_RESID = "#f9a825"    # residual (amber) — always shown when non-zero


def waterfall_rows(tree):
    """Exact bridge in the displayed node's units, with each residual owned once."""
    validate_result(tree)
    if tree.get('kind') == 'leaf':
        steps = [(d['driver'], d['cents']) for d in tree['drivers']]
        if tree['residual_cents']:
            steps.append(('Rounding residual', tree['residual_cents']))
    else:
        if tree.get('residual_cents', 0):
            raise ValueError('internal residual is already owned by child bridges')
        steps = [(c['name'], (1 if c['sign']=='add' else -1)*c['total_variance_cents'])
                 for c in tree['children']]
    rows = [{'label':'Budget', 'kind':'anchor', 'start_cents':0,
             'end_cents':tree['budget_cents'], 'value_cents':tree['budget_cents']}]
    running = tree['budget_cents']
    for label, value in steps:
        end = running + value
        rows.append({'label':label, 'kind':'step', 'start_cents':running,
                     'end_cents':end, 'value_cents':value,
                     'favourable':value * tree['sign_toward_profit'] >= 0})
        running = end
    if running != tree['actual_cents']:
        raise ValueError('waterfall steps do not reach actual')
    rows.append({'label':'Actual','kind':'anchor','start_cents':0,
                 'end_cents':running,'value_cents':running})
    return rows


def variance_waterfall_svg(tree: dict, width: int = 720, height: int = 360) -> str:
    """Accessible bridge; full labels and exact amounts are in waterfall_rows()."""
    if type(width) is not int or type(height) is not int or not 320 <= width <= 50000 or not 240 <= height <= 4096:
        raise ValueError('chart dimensions must be integer width 320–50000 and height 240–4096')
    rows = waterfall_rows(tree)
    # Keep text readable: the report scrolls the chart instead of shrinking it.
    width = max(width, len(rows)*110+80)
    lo = min([0]+[r[k] for r in rows for k in ('start_cents','end_cents')])
    hi = max([0]+[r[k] for r in rows for k in ('start_cents','end_cents')])
    span = hi-lo or 1
    def y(value):
        return 42 + (height-120)*(hi-value)/span
    slot = (width-80)/len(rows)
    svg = [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{_xml(tree["name"])} variance bridge" font-family="system-ui,sans-serif" font-size="13">',
           f'<title>{_xml(tree["name"])}: budget to actual</title>',
           '<desc>Numbered steps match the accompanying exact-value table. Green is favourable, red adverse. Amounts are EUR.</desc>',
           f'<line x1="40" x2="{width-40}" y1="{y(0):.2f}" y2="{y(0):.2f}" stroke="#9ca8b6"/>']
    for i, row in enumerate(rows):
        x = 40+i*slot+slot*.18
        start, end = row['start_cents'], row['end_cents']
        colour = _ANCHOR if row['kind']=='anchor' else (_FAV if row['favourable'] else _ADV)
        if row['kind']=='step':
            svg.append(f'<line x1="{x-slot*.36:.2f}" x2="{x:.2f}" y1="{y(start):.2f}" y2="{y(start):.2f}" stroke="#8b96a5" stroke-dasharray="3,3"/>')
        top, h = y(max(start,end)), abs(y(start)-y(end))
        if start == end:
            svg.append(f'<line x1="{x:.2f}" x2="{x+slot*.64:.2f}" y1="{top:.2f}" y2="{top:.2f}" stroke="{colour}" stroke-width="2"/>')
        else:
            svg.append(f'<rect x="{x:.2f}" y="{top:.2f}" width="{slot*.64:.2f}" height="{h:.2f}" fill="{colour}"><title>{_xml(row["label"])}: {euros(row["value_cents"])}</title></rect>')
        label = row['label'] if row['kind']=='anchor' else f'Step {i}'
        svg.append(f'<text x="{x+slot*.32:.2f}" y="{height-45}" text-anchor="middle">{_xml(label)}</text>')
    svg.append('</svg>')
    return ''.join(svg)


def _flatten(tree: dict, out: list, depth=0):
    out.append({"name": tree["name"], "depth": depth,
                "variance_cents": tree["total_variance_cents"],
                "favourable": tree["favourable"], "quadrant": tree.get("quadrant")})
    for c in tree.get("children", []):
        _flatten(c, out, depth + 1)


def board_pack(tree: dict, persistence_by_line=None, reforecast_by_line=None) -> dict:
    """Full board pack: hierarchy, waterfall, reconciled commentary."""
    validate_result(tree)
    registry = build_registry(tree, reforecast_by_line, persistence_by_line)
    claims = compose_registry(registry)
    gate = reconcile(claims, registry)
    if not gate["passed"]:
        raise ValueError(f"commentary failed reconciliation: {gate['violations']}")
    rows = []
    _flatten(tree, rows)
    return {"mode": "board_pack", "hierarchy": rows,
            "waterfall_svg": variance_waterfall_svg(tree),
            "commentary": claims, "reconciliation": gate,
            "registry": registry, "full_hierarchy": deepcopy(tree),
            "reforecasts": deepcopy(registry["snapshot"]["forecasts"]),
            "reconciles": tree["reconciles"],
            "source_reconciliation": tree.get("source_reconciliation", "not_provided"),
            "context": tree.get("context", {})}


_EXCEPTION_QUADRANTS = {"TOP_PRIORITY", "EARLY_WARNING", "MATERIAL_SIG_NC"}


def exception_view(tree: dict, persistence_by_line=None, reforecast_by_line=None) -> dict:
    """Only the lines that matter: material-and-significant / early-warning."""
    validate_result(tree)
    registry = build_registry(tree, reforecast_by_line, persistence_by_line)
    claims = compose_registry(registry, only_quadrants=_EXCEPTION_QUADRANTS)
    gate = reconcile(claims, registry, only_quadrants=_EXCEPTION_QUADRANTS)
    if not gate["passed"]:
        raise ValueError(f"commentary failed reconciliation: {gate['violations']}")
    rows = []
    _flatten(tree, rows)
    # §54: the exception TABLE now matches the commentary FILTER — a materially
    # large variance whose significance is not computable (MATERIAL_SIG_NC) also
    # deserves controller attention, so it appears in both, not just the prose.
    exceptions = [r for r in rows if r["quadrant"] in _EXCEPTION_QUADRANTS]
    return {"mode": "exception_view", "exceptions": exceptions,
            "commentary": claims, "reconciliation": gate,
            "registry": registry, "full_hierarchy": deepcopy(tree),
            "reforecasts": deepcopy(registry["snapshot"]["forecasts"]),
            "source_reconciliation": tree.get("source_reconciliation", "not_provided"),
            "context": tree.get("context", {})}
