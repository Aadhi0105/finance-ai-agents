"""
Hierarchy roll-up (Agent 4) — turns "decompose one line" into "explain a whole P&L".

Decompose at the LEAVES (product / cost lines), then aggregate up the tree, and
verify penny-reconciliation at EVERY node — not just the root. That per-node
guarantee is what makes the drill-down narrative trustworthy: a controller can
open any subtotal and the bridge still ties.

Three locked design points:

  1. SIGNS ARE STRUCTURAL. A EUR16,000 cost is stored as 16000 (reads naturally);
     the tree carries an add/subtract role per node and the roll-up applies it.
     Operating Profit = Revenue - COGS - Opex is computed from signs, so a cost
     line's "+EUR1,850 more cost" becomes a NEGATIVE contribution to profit.

  2. FAVOURABILITY BY PROFIT IMPACT, at every level. A node's net sign toward the
     root (profit) times its variance: a cost rising is adverse whether you read
     the leaf, the COGS subtotal, or the profit line.

  3. FAIL-LOUD RECONCILIATION at every node. Each node's total variance must equal
     the sign-adjusted roll-up of its children, exactly, in integer cents — or it
     raises ReconciliationError. Materiality/significance is attached at each leaf
     AND each subtotal so triage works top-down.

A node is either a LEAF (has "leaf": <decompose_line spec>) or an INTERNAL node
(has "children": [...]). Every non-root node has "sign": "add" | "subtract"
(how it enters its parent). Leaves may carry "history" (past variance cents) and
"period"/"period_history" for significance.
"""

from __future__ import annotations

from agent4.decomposition import decompose_line, decompose_multiproduct
from agent4.materiality import classify_variance


class ReconciliationError(Exception):
    """Raised when a node's drivers/children do not sum to its total variance."""


def _sign_mult(node: dict, is_root: bool = False) -> int:
    """§13: signs must be explicit. A typo like 'substract' or a missing sign used
    to silently become 'add', which could turn Revenue - COGS into Revenue + COGS
    and still reconcile against the (wrong) tree. Fail closed instead."""
    s = node.get("sign")
    if is_root:
        return 1
    if s not in ("add", "subtract"):
        raise ReconciliationError(
            f"node '{node.get('name','?')}' has invalid or missing sign {s!r} — "
            f"every non-root node must declare 'add' or 'subtract'")
    return -1 if s == "subtract" else 1


def _rollup(node: dict, sign_toward_profit: int, materiality_base_cents: int,
            n_leaves: int, path: str) -> dict:
    name = node.get("name", "?")
    here = f"{path}/{name}" if path else name

    # --- leaf -------------------------------------------------------------
    if "leaf" in node:
        spec = node["leaf"]
        if "products" in spec:
            d = decompose_multiproduct(spec["name"], spec["type"], spec["products"])
        else:
            d = decompose_line(spec)
        total = d["total_variance_cents"]
        explained = sum(dr["cents"] for dr in d["drivers"]) + d["residual_cents"]
        if explained != total:
            raise ReconciliationError(
                f"leaf '{here}': drivers+residual {explained} != total {total}")

        favourable = (sign_toward_profit * total) > 0 if total != 0 else True
        result = {
            "name": name, "kind": "leaf", "type": d["type"], "context": d.get("context", {}),
            "budget_cents": d["budget_cents"], "actual_cents": d["actual_cents"],
            "total_variance_cents": total, "favourable": favourable,
            "profit_impact_cents": sign_toward_profit * total,
            "drivers": d["drivers"], "residual_cents": d["residual_cents"],
            "convention": d.get("convention"),
            "granularity_note": d.get("granularity_note"),
            "joint_term_note": d.get("joint_term_note"),
            "joint_term_cents": d.get("joint_term_cents"),
            "rounding_tolerance_cents": d.get("rounding_tolerance_cents", 0),
            "reconciles": True,
        }
        _controls(result, node, sign_toward_profit, here)
        _attach_classification(result, node, materiality_base_cents, n_leaves)
        return result

    # --- internal node ----------------------------------------------------
    children = node.get("children")
    if not children:
        raise ReconciliationError(f"node '{here}' has neither leaf nor children")

    child_results = []
    node_budget = node_actual = rolled_var = 0
    for child in children:
        cs = _sign_mult(child)
        cr = _rollup(child, sign_toward_profit * cs, materiality_base_cents,
                     n_leaves, here)
        child_results.append(cr)
        node_budget += cs * cr["budget_cents"]
        node_actual += cs * cr["actual_cents"]
        rolled_var += cs * cr["total_variance_cents"]

    total = node_actual - node_budget
    if total != rolled_var:
        raise ReconciliationError(
            f"node '{here}': sign-adjusted children sum {rolled_var} != "
            f"actual-minus-budget {total}")
    if any(not c["reconciles"] for c in child_results):
        raise ReconciliationError(f"node '{here}': a child failed to reconcile")

    favourable = (sign_toward_profit * total) > 0 if total != 0 else True
    result = {
        "name": name, "kind": "node",
        "budget_cents": node_budget, "actual_cents": node_actual,
        "total_variance_cents": total, "favourable": favourable,
        "profit_impact_cents": sign_toward_profit * total,
        "children": child_results, "reconciles": True,
    }
    _controls(result, node, sign_toward_profit, here)
    _attach_classification(result, node, materiality_base_cents, n_leaves)
    return result


def _attach_classification(result: dict, node: dict, base_cents: int,
                           n_leaves: int) -> None:
    """Attach the materiality x significance quadrant to a node (leaf or subtotal)."""
    cls = classify_variance(
        {"name": result["name"], "total_variance_cents": result["total_variance_cents"],
         "favourable": result["favourable"]},
        line_budget_cents=result["budget_cents"],
        total_budget_cents=base_cents,
        variance_history_cents=([p["variance_cents"] for p in node["observation_history"]]
                                if "observation_history" in node else node.get("history")),
        period=node.get("period"), period_history=node.get("period_history"),
        n_lines_scanned=n_leaves,
    )
    result["quadrant"] = cls["quadrant"]
    result["triage"] = cls["reason"]
    result["materiality"] = cls["materiality"]
    result["significance"] = cls["significance"]


def _count_leaves(node: dict) -> int:
    if "leaf" in node:
        return 1
    return sum(_count_leaves(c) for c in node.get("children", []))


def rollup(tree: dict, materiality_base_cents: int | None = None) -> dict:
    """
    Roll up a P&L tree: decompose leaves, aggregate with signs, verify penny-
    reconciliation at every node, and attach triage classification throughout.

    materiality_base_cents: the denominator for "% of total" materiality (the
    caller-selected base). Defaults to the largest absolute signed top-level budget;
    its basis is labelled and never implicitly described as revenue.
    """
    from agent4.contracts import cents
    _validate_tree(tree)
    n_leaves = _count_leaves(tree)
    measure = tree.get('root_measure', 'cost' if tree.get('leaf', {}).get('type') in
                       ('fixed_cost', 'variable_cost') else 'profit')
    if measure not in ('profit', 'revenue', 'cost'):
        raise ValueError('root_measure must be profit, revenue or cost')
    base_basis = 'explicit caller base'
    if materiality_base_cents is None:
        candidates = tree.get('children') or [tree]
        materiality_base_cents = max(abs(_first_budget(c)) for c in candidates)
        base_basis = 'largest absolute signed top-level budget (not assumed revenue)'
    cents(materiality_base_cents, 'materiality base')
    if materiality_base_cents < 0:
        raise ValueError('materiality base must be nonnegative')
    result = _rollup(tree, -1 if measure == 'cost' else 1,
                     materiality_base_cents, n_leaves, '')
    result.update(root_measure=measure, materiality_base_basis=base_basis,
                  context={**result.get('context', {}), **tree.get('context', {})})
    validate_result(result)
    return result


def _first_budget(node: dict) -> int:
    """Use the same type-aware resolver and signs as the accounting engine."""
    if 'leaf' in node:
        spec = node['leaf']
        result = (decompose_multiproduct(spec['name'], spec['type'], spec['products'])
                  if 'products' in spec else decompose_line(spec))
        return result['budget_cents']
    return sum(_sign_mult(c) * _first_budget(c) for c in node['children'])


def _validate_tree(tree):
    """Reject ambiguous identity/shape before traversing or calculating."""
    from agent4.contracts import name, metadata, cents
    from datetime import date
    seen, names, ids = set(), set(), set()
    root_context = metadata(tree.get('context', {})) if isinstance(tree, dict) else {}

    contexts = dict(root_context)
    def check_context(value):
        for key, val in metadata(value).items():
            if key == 'quantity_unit':
                continue  # separate lines may measure different activities
            if key in contexts and contexts[key] != val:
                raise ReconciliationError('conflicting entity, period or source context')
            contexts[key] = val

    def visit(node, path='', depth=0):
        if not isinstance(node, dict) or depth > 50 or id(node) in seen:
            raise ReconciliationError('invalid, shared or cyclic tree (maximum depth 50)')
        if set(node) - {'name', 'node_id', 'sign', 'root_measure', 'context', 'leaf', 'children',
                        'history', 'period', 'period_history', 'observation_history', 'budget_cents', 'actual_cents'}:
            raise ReconciliationError('unsupported tree fields')
        seen.add(id(node))
        label = name(node.get('name'))
        here = path + '/' + label if path else label
        ident = node.get('node_id', here)
        if not isinstance(ident, str) or not ident.strip() or ident in ids or label in names:
            raise ReconciliationError('node IDs and names must be unique across this report')
        names.add(label); ids.add(ident)
        if ('leaf' in node) == ('children' in node):
            raise ReconciliationError('node must contain exactly one of leaf or children')
        check_context(node.get('context', {}))
        if path:
            if 'root_measure' in node:
                raise ReconciliationError('root_measure is only valid on the root')
            _sign_mult(node)
        elif 'sign' in node and node['sign'] != 'add':
            raise ReconciliationError('root sign must be add; use root_measure for cost roots')
        for key in ('budget_cents', 'actual_cents'):
            if key in node:
                cents(node[key], key)
        if ('budget_cents' in node) != ('actual_cents' in node):
            raise ReconciliationError('source control totals require both budget and actual')
        history = node.get('history', [])
        if not isinstance(history, list):
            raise ValueError('history must be a prior-only list of integer cents')
        for value in history:
            cents(value, 'history')
        if 'observation_history' in node:
            if history:
                raise ValueError('choose dated observation_history or legacy history, not both')
            close = date.fromisoformat(root_context['close_date']) if root_context.get('close_date') else None
            if close is None or not isinstance(node['observation_history'], list):
                raise ValueError('dated history requires root context.close_date')
            last = None
            for point in node['observation_history']:
                stamp = date.fromisoformat(point['period'])
                cents(point['variance_cents'], 'history variance')
                if stamp >= close or (last is not None and stamp <= last):
                    raise ValueError('history must be unique, ordered and strictly before the close')
                last = stamp
        if 'leaf' in node:
            if not isinstance(node['leaf'], dict) or node['leaf'].get('name') != label:
                raise ReconciliationError('leaf and node names must match')
            spec = node['leaf']
            check_context(spec.get('context', {}))
            if 'products' in spec:
                if set(spec) - {'name', 'type', 'products', 'context'}:
                    raise ReconciliationError('basket cannot also contain aggregate amount/unit inputs')
                if isinstance(spec['products'], list):
                    for product in spec['products']:
                        if isinstance(product, dict):
                            check_context(product.get('context', {}))
        else:
            if not isinstance(node['children'], list) or not node['children']:
                raise ReconciliationError('children must be a nonempty list')
            for child in node['children']:
                visit(child, here, depth + 1)
    visit(tree)


def _controls(result, node, sign, path):
    from agent4.contracts import cents
    for key in ('budget_cents', 'actual_cents', 'total_variance_cents', 'profit_impact_cents'):
        cents(result[key], key)
    result['context'] = {**result.get('context', {}), **node.get('context', {})}
    result.update(node_id=node.get('node_id', path), sign=node.get('sign', 'add'),
                  sign_toward_profit=sign, source_reconciliation='not_provided')
    if 'budget_cents' in node:
        if any(node[key] != result[key] for key in ('budget_cents', 'actual_cents')):
            raise ReconciliationError(f'{path}: independent source control totals do not match')
        result['source_reconciliation'] = 'matched'
        result['source_controls'] = {key: node[key] for key in ('budget_cents', 'actual_cents')}


def validate_result(tree):
    """Recompute identities at the publication boundary; never trust a flag alone."""
    from agent4.contracts import cents
    seen = set()
    def walk(node, expected_sign=None):
        if id(node) in seen:
            raise ReconciliationError('cyclic or shared result tree')
        seen.add(id(node))
        for key in ('budget_cents', 'actual_cents', 'total_variance_cents', 'profit_impact_cents'):
            cents(node[key], key)
        sign = node.get('sign_toward_profit')
        if type(sign) is not int or sign not in (-1, 1) or (expected_sign is not None and sign != expected_sign):
            raise ReconciliationError('invalid result sign')
        total = node['actual_cents'] - node['budget_cents']
        if total != node['total_variance_cents'] or sign * total != node['profit_impact_cents']:
            raise ReconciliationError('result accounting identity failed')
        if node.get('favourable') is not (sign * total >= 0) or node.get('reconciles') is not True:
            raise ReconciliationError('result classification or reconciliation failed')
        controls = node.get('source_controls')
        if controls and any(controls[k] != node[k] for k in ('budget_cents', 'actual_cents')):
            raise ReconciliationError('source controls no longer match')
        if node.get('kind') == 'leaf':
            residual = cents(node['residual_cents'], 'residual')
            tolerance = node.get('rounding_tolerance_cents', 0)
            if type(tolerance) is not int or tolerance < 0 or abs(residual) > tolerance:
                raise ReconciliationError('residual exceeds rounding tolerance')
            if sum(cents(d['cents'], 'driver') for d in node['drivers']) + residual != total:
                raise ReconciliationError('driver bridge does not tie')
        elif node.get('kind') == 'node' and node.get('children'):
            totals = {'budget_cents': 0, 'actual_cents': 0}
            for child in node['children']:
                cs = _sign_mult(child)
                walk(child, sign * cs)
                for key in totals:
                    totals[key] += cs * child[key]
            if any(node[k] != totals[k] for k in totals):
                raise ReconciliationError('child bridge does not tie')
        else:
            raise ReconciliationError('invalid result shape')
    walk(tree)
