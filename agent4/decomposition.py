"""
Variance decomposition engine (Agent 4, the flagship).

Agent 1 valued, Agent 2 monitored, Agent 3 tested events — Agent 4 explains WHY a
number missed plan. Its signature act is DECOMPOSITION (attribution), not
detection: it splits a budget-vs-actual variance into its arithmetic drivers.

Three governing properties (all mechanical, all demoable):

  1. RECONCILES TO THE PENNY. Every amount is carried as INTEGER CENTS, and the
     drivers sum EXACTLY to the total variance — no floating-point dust, no
     "approximately ties". A bridge that doesn't reconcile fails loudly. An
     explicit, labelled residual absorbs only genuine unexplained remainder.

  2. DISPATCH BY LINE TYPE. revenue -> price x volume x mix; variable cost ->
     rate x volume; fixed cost -> spending (amount-only). One engine routes by the
     line's declared type.

  3. CONVENTION NAMED, JOINT TERM SURFACED. Decompositions are convention-
     dependent; pretending otherwise is the amateur tell. Default is the
     SEQUENTIAL convention (volume at budget price, price at actual volume, the
     joint price x volume interaction absorbed into price). The convention is
     named in the output, and when the absorbed joint term is material its
     magnitude is reported — a large joint term means both price and volume moved
     a lot, which is itself information. A symmetric (split-the-joint) convention
     is available via flag.

Decomposition is deterministic accounting arithmetic (like the DCF, it is not one
of the three disciplines). The LLM never does this math.

Sign convention: variance = actual - budget, from the P&L's perspective. For
revenue, positive = favourable. For costs, positive actual-minus-budget = MORE
cost = adverse; `favourable` is computed per line type, not from the raw sign.
"""

from __future__ import annotations

from agent4.contracts import money, normalize_line, name, cents

# Materiality default for surfacing the absorbed joint term (share of |total|).
_JOINT_MATERIAL_FRAC = 0.05


def _c(x) -> int:
    """Round a major-unit decimal amount to integer cents, half-even."""
    return money(x)


def _favourable(line_type: str, variance_cents: int) -> bool:
    """Is a positive actual-minus-budget variance good? Revenue: yes. Costs: no."""
    if variance_cents == 0:
        return True
    if line_type == "revenue":
        return variance_cents > 0
    return variance_cents < 0   # cost lines: below budget (negative variance) is favourable


def decompose_line(line: dict, convention: str = "sequential") -> dict:
    """
    Decompose one P&L line's total variance into drivers, in integer cents.

    line = {
      "name": str, "type": "revenue"|"variable_cost"|"fixed_cost",
      # revenue / variable_cost need unit data for a price/rate x volume split:
      "budget": {"price": float, "volume": float}   (revenue)
              | {"rate": float, "volume": float}     (variable_cost)
              | {"amount": float}                    (fixed_cost, or any line w/o unit data)
      "actual": { ... same shape ... }
    }

    Returns total variance and the driver breakdown, all in cents, with the
    convention named and the drivers reconciling to the total exactly.
    """
    line = normalize_line(line)
    lt = line.get("type")
    # §4: validate the line type FIRST — a malformed type carrying amount data must
    # be rejected, not silently routed into the amount path and treated as a cost.
    if lt not in ("revenue", "variable_cost", "fixed_cost"):
        raise ValueError(
            f"invalid line type {lt!r} for '{line.get('name','?')}' — "
            f"must be one of revenue / variable_cost / fixed_cost")
    if convention not in ("sequential", "symmetric"):
        raise ValueError(f"invalid convention {convention!r} — sequential or symmetric")
    b, a = line["budget"], line["actual"]

    # --- lines without unit data: total variance only (granularity-aware) -------
    if "amount" in b or "amount" in a or lt == "fixed_cost":
        return _decompose_amount_line(line)

    if lt == "revenue":
        return _decompose_pv(line, price_key="price", convention=convention)
    if lt == "variable_cost":
        return _decompose_pv(line, price_key="rate", convention=convention)


def _amount_of(side: dict, which: str, name: str) -> int:
    """Resolve a side's amount, distinguishing MISSING from zero (§5). Uses an
    explicit amount, else price*volume, else raises — never defaults to 0."""
    if "amount" in side:
        return _c(side["amount"])
    if "price" in side and "volume" in side:
        return _c(side["price"] * side["volume"])
    if "rate" in side and "volume" in side:
        return _c(side["rate"] * side["volume"])
    raise ValueError(f"missing {which} amount for '{name}' — data error, not zero")


def _decompose_amount_line(line: dict) -> dict:
    """A line given only as amounts (fixed cost, or any line lacking unit data):
    report total variance, label the split as not computable — never fabricate."""
    lt = line["type"]
    b_amt = _amount_of(line["budget"], "budget", line["name"])
    a_amt = _amount_of(line["actual"], "actual", line["name"])
    total = cents(a_amt - b_amt, "variance")
    return {
        "name": line["name"], "type": lt, "context": line.get("context", {}), "convention": "none (amount only)",
        "budget_cents": b_amt, "actual_cents": a_amt, "total_variance_cents": total,
        "favourable": _favourable(lt, total),
        "drivers": [{"driver": "spending", "cents": total}],
        "residual_cents": 0, "rounding_tolerance_cents": 0,
        "granularity_note": ("no unit (price/volume) data — reporting total spending "
                             "variance only; volume/rate split not computable"),
        "reconciles": True,
        "computed_by": "decompose_line (python, integer cents)",
    }


def _decompose_pv(line: dict, price_key: str, convention: str) -> dict:
    """Price/rate x volume (x mix handled by the multi-product caller). Sequential
    or symmetric convention, integer cents, exact reconciliation."""
    lt = line["type"]
    bp, bv = line["budget"][price_key], line["budget"]["volume"]
    ap, av = line["actual"][price_key], line["actual"]["volume"]

    b_amt = _c(bp * bv)
    a_amt = _c(ap * av)
    total = cents(a_amt - b_amt, "variance")

    # Driver amounts computed in cents from the exact factor arithmetic.
    # Volume effect at BUDGET price: (av - bv) * bp
    # Price effect at ACTUAL volume: (ap - bp) * av   [absorbs the joint term]
    # Joint (interaction): (ap - bp) * (av - bv)
    vol_at_budget_price = _c((av - bv) * bp)
    price_at_actual_vol = _c((ap - bp) * av)
    price_at_budget_vol = _c((ap - bp) * bv)
    joint = _c((ap - bp) * (av - bv))

    if convention == "symmetric":
        # split the joint term evenly between price and volume
        half = joint // 2
        price_drv = price_at_budget_vol + half
        vol_drv = vol_at_budget_price + (joint - half)   # give the odd cent to volume
        conv_name = "symmetric (joint split evenly)"
        joint_surfaced = joint
    else:
        # sequential (default): volume at budget price, price at actual volume
        price_drv = price_at_actual_vol
        vol_drv = vol_at_budget_price
        conv_name = "sequential (volume @ budget price, price @ actual volume)"
        joint_surfaced = joint

    # Reconcile in cents. Any remainder from cents-rounding of the three products
    # is a true residual, surfaced — but with exact factors it is typically 0.
    explained = price_drv + vol_drv
    residual = total - explained

    if abs(residual) > 2:
        raise ValueError("unexplained residual exceeds rounding tolerance")
    drivers = [
        {"driver": ("price" if price_key == "price" else "rate"), "cents": price_drv},
        {"driver": "volume", "cents": vol_drv},
    ]

    result = {
        "name": line["name"], "type": lt, "context": line.get("context", {}), "convention": conv_name,
        "budget_cents": b_amt, "actual_cents": a_amt, "total_variance_cents": total,
        "favourable": _favourable(lt, total),
        "drivers": drivers,
        "residual_cents": residual, "rounding_tolerance_cents": 2,
        "reconciles": (price_drv + vol_drv + residual == total),
        "computed_by": "decompose_line (python, integer cents)",
    }

    # Surface the absorbed joint term when it is material (sequential only —
    # symmetric already split it into the drivers).
    if convention != "symmetric" and joint_surfaced != 0 and \
            abs(joint_surfaced) * 20 >= max(1, abs(price_drv) + abs(vol_drv)):
        result["joint_term_note"] = (
            f"joint price-volume interaction of {joint_surfaced} cents absorbed into "
            f"'{drivers[0]['driver']}' per sequential convention — both factors moved "
            f"materially")
        result["joint_term_cents"] = joint_surfaced

    return result


def decompose_multiproduct(line_name: str, line_type: str, products: list[dict],
                           convention: str = "sequential") -> dict:
    """
    Decompose a multi-product line into price/rate, volume, AND mix.

    Mix isolates the effect of the sales-mix shift at constant total volume; the
    pure volume effect is the total-volume change at budget mix. products is a list
    of per-product {name, budget:{price,volume}, actual:{price,volume}}.

    Reconciles to the penny across all products: sum of (price + volume + mix) over
    products + residual == total variance.
    """
    if convention != "sequential":
        raise NotImplementedError(
            f"convention {convention!r} not supported for multi-product lines — "
            f"symmetric is single-product only")
    # #4: the per-unit factor is 'price' for revenue and 'rate' for a variable cost.
    # Previously this was hardcoded to 'price', so a variable-cost basket with 'rate'
    # data was not actually supported despite the line_type argument.
    if line_type == "revenue":
        fkey = "price"
    elif line_type == "variable_cost":
        fkey = "rate"
    else:
        raise ValueError(
            f"decompose_multiproduct supports revenue / variable_cost, got {line_type!r}")

    name(line_name)
    if not isinstance(products, list) or not products:
        raise ValueError('products must be a nonempty list')
    if any(not isinstance(p, dict) or set(p) - {'name', 'budget', 'actual', 'context'} for p in products):
        raise ValueError('product: expected name, budget, actual and optional context')
    products = [normalize_line({**p, 'type': line_type}) for p in products]
    if len({p['name'] for p in products}) != len(products):
        raise ValueError('product names must be unique')
    if len({tuple(sorted(p['context'].items())) for p in products}) > 1:
        raise ValueError('products must have compatible context and quantity units')
    if any(fkey not in p['budget'] for p in products):
        raise ValueError('products require factor and volume data')
    total_b = sum(_c(p["budget"][fkey] * p["budget"]["volume"]) for p in products)
    total_a = sum(_c(p["actual"][fkey] * p["actual"]["volume"]) for p in products)
    total = total_a - total_b

    bud_total_vol = sum(p["budget"]["volume"] for p in products)
    act_total_vol = sum(p["actual"]["volume"] for p in products)

    if bud_total_vol == 0:
        raise ValueError('budget mix is undefined at zero total volume; use amount-only new-activity reporting')
    price_sum = vol_sum = mix_sum = 0
    per_product = []
    for p in products:
        bp, bv = p["budget"][fkey], p["budget"]["volume"]
        ap, av = p["actual"][fkey], p["actual"]["volume"]
        bud_mix = (bv / bud_total_vol) if bud_total_vol else 0.0

        price_eff = _c((ap - bp) * av)
        vol_eff = _c((act_total_vol - bud_total_vol) * bud_mix * bp)
        expected_vol_at_bud_mix = act_total_vol * bud_mix
        mix_eff = _c((av - expected_vol_at_bud_mix) * bp)

        price_sum += price_eff
        vol_sum += vol_eff
        mix_sum += mix_eff
        per_product.append({"product": p["name"], f"{fkey}_cents": price_eff,
                            "volume_cents": vol_eff, "mix_cents": mix_eff})

    explained = price_sum + vol_sum + mix_sum
    residual = total - explained
    drivers = [
        {"driver": fkey, "cents": price_sum},
        {"driver": "volume", "cents": vol_sum},
        {"driver": "mix", "cents": mix_sum},
    ]
    cents(total_b, 'budget total'); cents(total_a, 'actual total'); cents(total, 'variance')
    if abs(residual) > 3 * len(products):
        raise ValueError('unexplained residual exceeds rounding tolerance')
    return {
        "rounding_tolerance_cents": 3 * len(products),
        "joint_term_cents": sum(_c((p['actual'][fkey] - p['budget'][fkey]) *
                                    (p['actual']['volume'] - p['budget']['volume'])) for p in products),
        "name": line_name, "type": line_type, "context": products[0]["context"],
        "convention": "sequential + mix (multi-product)",
        "budget_cents": total_b, "actual_cents": total_a, "total_variance_cents": total,
        "favourable": _favourable(line_type, total),
        "drivers": drivers, "per_product": per_product,
        "residual_cents": residual,
        "reconciles": (explained + residual == total),
        "computed_by": "decompose_multiproduct (python, integer cents)",
    }


def euros(cents: int) -> str:
    """Format integer cents as a euro string for display."""
    if type(cents) is not int:
        raise ValueError("display amounts must be integer cents")
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}\u20ac{c // 100:,}.{c % 100:02d}"
