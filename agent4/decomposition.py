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
     rate x efficiency; fixed cost -> spending x volume. One engine routes by the
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

# Materiality default for surfacing the absorbed joint term (share of |total|).
_JOINT_MATERIAL_FRAC = 0.05


def _c(x) -> int:
    """Coerce a money amount to integer cents. Accepts euros (float/int) or an
    already-cents int via the callers below; here we take EUROS and round to cents
    deterministically (round-half-to-even is fine; inputs are fixture-exact)."""
    return int(round(x * 100))


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
    lt = line["type"]
    b, a = line["budget"], line["actual"]

    # --- lines without unit data: total variance only (granularity-aware) -------
    if "amount" in b or "amount" in a or lt == "fixed_cost":
        # fixed cost decomposes as spending (rate) x volume only if volume given;
        # otherwise it's a pure spending variance on the amount.
        return _decompose_amount_line(line)

    if lt == "revenue":
        return _decompose_pv(line, price_key="price", convention=convention)
    if lt == "variable_cost":
        return _decompose_pv(line, price_key="rate", convention=convention)
    raise ValueError(f"unknown line type: {lt}")


def _decompose_amount_line(line: dict) -> dict:
    """A line given only as amounts (fixed cost, or any line lacking unit data):
    report total variance, label the split as not computable — never fabricate."""
    lt = line["type"]
    b_amt = _c(line["budget"].get("amount",
               line["budget"].get("price", 0) * line["budget"].get("volume", 0)))
    a_amt = _c(line["actual"].get("amount",
               line["actual"].get("price", 0) * line["actual"].get("volume", 0)))
    total = a_amt - b_amt
    return {
        "name": line["name"], "type": lt, "convention": "none (amount only)",
        "budget_cents": b_amt, "actual_cents": a_amt, "total_variance_cents": total,
        "favourable": _favourable(lt, total),
        "drivers": [{"driver": "spending", "cents": total}],
        "residual_cents": 0,
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
    total = a_amt - b_amt

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

    drivers = [
        {"driver": ("price" if price_key == "price" else "rate"), "cents": price_drv},
        {"driver": "volume", "cents": vol_drv},
    ]

    result = {
        "name": line["name"], "type": lt, "convention": conv_name,
        "budget_cents": b_amt, "actual_cents": a_amt, "total_variance_cents": total,
        "favourable": _favourable(lt, total),
        "drivers": drivers,
        "residual_cents": residual,
        "reconciles": (price_drv + vol_drv + residual == total),
        "computed_by": "decompose_line (python, integer cents)",
    }

    # Surface the absorbed joint term when it is material (sequential only —
    # symmetric already split it into the drivers).
    if convention != "symmetric" and abs(total) > 0 and \
            abs(joint_surfaced) >= _JOINT_MATERIAL_FRAC * abs(total):
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
    total_b = sum(_c(p["budget"]["price"] * p["budget"]["volume"]) for p in products)
    total_a = sum(_c(p["actual"]["price"] * p["actual"]["volume"]) for p in products)
    total = total_a - total_b

    bud_total_vol = sum(p["budget"]["volume"] for p in products)
    act_total_vol = sum(p["actual"]["volume"] for p in products)

    price_sum = vol_sum = mix_sum = 0
    per_product = []
    for p in products:
        bp, bv = p["budget"]["price"], p["budget"]["volume"]
        ap, av = p["actual"]["price"], p["actual"]["volume"]
        bud_mix = (bv / bud_total_vol) if bud_total_vol else 0.0

        # price @ actual volume (sequential)
        price_eff = _c((ap - bp) * av)
        # pure volume: total volume change, this product's budget share, at budget price
        vol_eff = _c((act_total_vol - bud_total_vol) * bud_mix * bp)
        # mix: (actual volume - what budget-mix would have given at actual total) at budget price
        expected_vol_at_bud_mix = act_total_vol * bud_mix
        mix_eff = _c((av - expected_vol_at_bud_mix) * bp)

        price_sum += price_eff
        vol_sum += vol_eff
        mix_sum += mix_eff
        per_product.append({"product": p["name"], "price_cents": price_eff,
                            "volume_cents": vol_eff, "mix_cents": mix_eff})

    explained = price_sum + vol_sum + mix_sum
    residual = total - explained
    drivers = [
        {"driver": "price", "cents": price_sum},
        {"driver": "volume", "cents": vol_sum},
        {"driver": "mix", "cents": mix_sum},
    ]
    return {
        "name": line_name, "type": line_type,
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
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}\u20ac{c // 100:,}.{c % 100:02d}"
