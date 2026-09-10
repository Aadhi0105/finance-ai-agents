"""Agent 4 commentary grounding gate (§45 context, §46 sign, §47 percentage,
§48 hypothesis) and output fixes (§53 XML escape, §54 exception-table)."""

import json
from agent4.hierarchy import rollup
from agent4.persistence import classify_persistence
from agent4.commentary import build_registry, compose, reconcile
from agent4.output import board_pack, exception_view, variance_waterfall_svg


def _tree_and_persistence():
    pnl = json.load(open("fixtures/pnl.json"))
    tree = rollup(pnl)
    persistence = {}
    def collect(n):
        if "history" in n and "leaf" in n:
            persistence[n["name"]] = classify_persistence(n["history"], name=n["name"])
        for c in n.get("children", []):
            collect(c)
    collect(pnl)
    return tree, persistence


# --- honest board pack still passes the hard gate -----------------------

def test_honest_board_pack_grounds_cleanly():
    tree, persistence = _tree_and_persistence()
    bp = board_pack(tree, persistence_by_line=persistence)
    assert bp["reconciliation"]["passed"] is True


# --- §45: context-blind loophole closed ---------------------------------

def test_grounding_catches_wrong_line_figure():
    tree, persistence = _tree_and_persistence()
    reg = build_registry(tree)
    claims = compose(tree, persistence_by_line=persistence)
    # inject a euro from a DIFFERENT line into a Materials fact
    tampered = [dict(c) for c in claims]
    for i, c in enumerate(tampered):
        if c["tier"] == "computed_fact" and "Materials" in c["text"]:
            t = dict(c); t["text"] += " Includes €40,800.00 from Premium."
            tampered[i] = t
            break
    assert reconcile(tampered, reg)["passed"] is False


# --- §46: sign-blind loophole closed ------------------------------------

def test_grounding_catches_flipped_sign():
    tree, persistence = _tree_and_persistence()
    reg = build_registry(tree)
    claims = compose(tree, persistence_by_line=persistence)
    tampered = [dict(c) for c in claims]
    tampered[0] = dict(tampered[0])
    tampered[0]["text"] = tampered[0]["text"].replace("-€17,240.00", "+€17,240.00")
    assert reconcile(tampered, reg)["passed"] is False


# --- §47: fabricated percentage caught ----------------------------------

def test_grounding_catches_fabricated_percentage():
    tree, _ = _tree_and_persistence()
    reg = build_registry(tree)
    claim = [{"tier": "observation", "text": "P(hit target) 97%.",
              "refs": {"prob_hit": 0.74}}]
    assert reconcile(claim, reg)["passed"] is False


# --- §48: hypothesis cannot assert a hard number ------------------------

def test_hypothesis_with_number_rejected():
    tree, _ = _tree_and_persistence()
    reg = build_registry(tree)
    claim = [{"tier": "hypothesis", "text": "Supplier caused a 25% volume drop.",
              "refs": {}}]
    assert reconcile(claim, reg)["passed"] is False


# --- §53: SVG labels are XML-escaped ------------------------------------

def test_svg_escapes_ampersand():
    svg = variance_waterfall_svg({"name": "R&D Budget", "budget_cents": 100,
                                  "actual_cents": 90, "total_variance_cents": -10,
                                  "favourable": True, "children": []})
    assert "R&amp;D" in svg
    assert "R&D Budget<" not in svg    # raw & not present


# --- §54: exception table matches commentary filter ---------------------

def test_exception_view_runs():
    tree, persistence = _tree_and_persistence()
    ev = exception_view(tree, persistence_by_line=persistence)
    assert ev["reconciliation"]["passed"] is True
    # every surfaced exception is in the exception quadrant set
    for r in ev["exceptions"]:
        assert r["quadrant"] in ("TOP_PRIORITY", "EARLY_WARNING", "MATERIAL_SIG_NC")
