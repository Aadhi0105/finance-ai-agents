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


def _sign_mult(node: dict) -> int:
    return -1 if node.get("sign") == "subtract" else 1


def _rollup(node: dict, sign_toward_profit: int, materiality_base_cents: int,
            n_leaves: int, path: str) -> dict:
    name = node.get("name", "?")
    here = f"{path}/{name}" if path else name

    # --- leaf -------------------------------------------------------------
    if "leaf" in node:
        spec = node["leaf"]
        if spec.get("products"):
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
            "name": name, "kind": "leaf", "type": d["type"],
            "budget_cents": d["budget_cents"], "actual_cents": d["actual_cents"],
            "total_variance_cents": total, "favourable": favourable,
            "profit_impact_cents": sign_toward_profit * total,
            "drivers": d["drivers"], "residual_cents": d["residual_cents"],
            "convention": d.get("convention"),
            "granularity_note": d.get("granularity_note"),
            "joint_term_note": d.get("joint_term_note"),
            "reconciles": True,
        }
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
    _attach_classification(result, node, materiality_base_cents, n_leaves)
    return result


def _attach_classification(result: dict, node: dict, base_cents: int,
                           n_leaves: int) -> None:
    """Attach the materiality x significance quadrant to a node (leaf or subtotal)."""
    cls = classify_variance(
        {"name": result["name"], "total_variance_cents": result["total_variance_cents"],
         "favourable": result["favourable"]},
        line_budget_cents=result["budget_cents"] or 1,
        total_budget_cents=base_cents,
        variance_history_cents=node.get("history"),
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
    revenue base by convention). Defaults to the largest top-level child budget.
    """
    n_leaves = _count_leaves(tree)
    if materiality_base_cents is None:
        # default base = largest first-level child budget magnitude (usually revenue)
        mags = []
        for c in tree.get("children", []):
            b = _first_budget(c)
            mags.append(abs(b))
        materiality_base_cents = max(mags) if mags else 1
    return _rollup(tree, sign_toward_profit=1,
                   materiality_base_cents=materiality_base_cents,
                   n_leaves=n_leaves, path="")


def _first_budget(node: dict) -> int:
    """Cheap budget estimate for a node (for the default materiality base)."""
    if "leaf" in node:
        spec = node["leaf"]
        if spec.get("products"):
            return sum(int(round(p["budget"]["price"] * p["budget"]["volume"] * 100))
                       for p in spec["products"])
        b = spec["budget"]
        if "amount" in b:
            return int(round(b["amount"] * 100))
        price = b.get("price", b.get("rate", 0))
        return int(round(price * b.get("volume", 0) * 100))
    return sum(_first_budget(c) for c in node.get("children", []))
