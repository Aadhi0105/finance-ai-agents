"""Agent 4 decomposition + fail-closed validation (§4/§5/§8/§13) and penny
reconciliation."""

import pytest
from agent4.decomposition import decompose_line, decompose_multiproduct, euros
from agent4.hierarchy import rollup, ReconciliationError


# --- penny reconciliation (the flagship property) -----------------------

def test_revenue_decomposition_reconciles_to_penny():
    r = decompose_line({"name": "A", "type": "revenue",
                        "budget": {"price": 50.0, "volume": 1000},
                        "actual": {"price": 52.0, "volume": 1100}})
    assert r["total_variance_cents"] == 720000        # +€7,200
    drivers = sum(d["cents"] for d in r["drivers"])
    assert drivers + r["residual_cents"] == r["total_variance_cents"]


def test_multiproduct_mix_reconciles():
    prods = [{"name": "P", "budget": {"price": 100.0, "volume": 500}, "actual": {"price": 105.0, "volume": 700}},
             {"name": "S", "budget": {"price": 40.0, "volume": 1500}, "actual": {"price": 39.0, "volume": 1400}}]
    r = decompose_multiproduct("Sales", "revenue", prods)
    drivers = sum(d["cents"] for d in r["drivers"])
    assert drivers + r["residual_cents"] == r["total_variance_cents"]


# --- §4: fail-closed line type ------------------------------------------

def test_invalid_line_type_rejected():
    with pytest.raises(ValueError):
        decompose_line({"name": "X", "type": "banana",
                        "budget": {"amount": 100.0}, "actual": {"amount": 120.0}})


def test_invalid_convention_rejected():
    with pytest.raises(ValueError):
        decompose_line({"name": "A", "type": "revenue",
                        "budget": {"price": 50.0, "volume": 1000},
                        "actual": {"price": 52.0, "volume": 1100}}, convention="banana")


# --- §5: missing amount is a data error, not silent zero ----------------

def test_missing_amount_is_data_error():
    with pytest.raises(ValueError):
        decompose_line({"name": "Rent", "type": "fixed_cost",
                        "budget": {}, "actual": {"amount": 120.0}})


# --- §8: multi-product symmetric convention rejected --------------------

def test_multiproduct_symmetric_convention_rejected():
    prods = [{"name": "P", "budget": {"price": 100.0, "volume": 500}, "actual": {"price": 105.0, "volume": 700}}]
    with pytest.raises(NotImplementedError):
        decompose_multiproduct("Sales", "revenue", prods, convention="symmetric")


# --- §13: fail-closed sign in the hierarchy -----------------------------

def _leaf(name, sign, budget, actual):
    return {"name": name, "sign": sign,
            "leaf": {"name": name, "type": "fixed_cost",
                     "budget": {"amount": budget}, "actual": {"amount": actual}}}


def test_invalid_sign_raises():
    tree = {"name": "OP", "children": [
        _leaf("Rev", "add", 1000.0, 1100.0),
        _leaf("Cost", "substract", 400.0, 420.0),   # typo!
    ]}
    with pytest.raises(ReconciliationError):
        rollup(tree)


def test_missing_sign_raises():
    tree = {"name": "OP", "children": [
        {"name": "Rev", "leaf": {"name": "Rev", "type": "fixed_cost",
                                 "budget": {"amount": 1000.0}, "actual": {"amount": 1100.0}}},
    ]}
    with pytest.raises(ReconciliationError):
        rollup(tree)


def test_valid_tree_reconciles_every_node():
    tree = {"name": "OP", "children": [
        _leaf("Rev", "add", 1000.0, 1100.0),
        _leaf("Cost", "subtract", 400.0, 420.0),
    ]}
    r = rollup(tree)
    assert r["reconciles"] is True
    # OP variance = +100 (rev) - 20 (cost) = +80
    assert r["total_variance_cents"] == 8000


# --- #4: multi-product variable-cost uses 'rate' not 'price' -------------

def test_multiproduct_variable_cost_uses_rate():
    prods = [{"name": "Steel", "budget": {"rate": 8.0, "volume": 1000},
              "actual": {"rate": 8.5, "volume": 1100}}]
    r = decompose_multiproduct("Materials", "variable_cost", prods)
    driver_names = {d["driver"] for d in r["drivers"]}
    assert "rate" in driver_names and "price" not in driver_names
    drivers = sum(d["cents"] for d in r["drivers"])
    assert drivers + r["residual_cents"] == r["total_variance_cents"]


def test_multiproduct_rejects_unknown_type():
    prods = [{"name": "X", "budget": {"price": 1.0, "volume": 1}, "actual": {"price": 1.0, "volume": 1}}]
    with pytest.raises(ValueError):
        decompose_multiproduct("X", "fixed_cost", prods)
