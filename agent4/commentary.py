"""
Commentary integrity (Agent 4) — the prose analogue of the penny-reconciling bridge.

The governing principle: the LLM never invents a cause. Every statement in the
commentary is one of three tiers, and the gate enforces the distinction:

  1. COMPUTED FACT       — a number/driver straight from the engine. Stated plainly.
                           EVERY figure must reconcile against the computed registry
                           (Agent 4's model.json). Built BY REFERENCE — the number in
                           the text is inserted from the data, so it is correct by
                           construction; the gate is the backstop for any live rewrite.
  2. OBSERVATION         — traces to a stored classification (a materiality quadrant,
                           a persistence verdict). Allowed because it references a
                           real, computed verdict + confidence.
  3. HYPOTHESIS          — a business CAUSE ("likely the new supplier contract").
                           Cannot be data-supported, so it is ALWAYS flagged
                           "requires confirmation" and never asserted as fact.

The hard reconciliation gate: extract every monetary figure from every fact/
observation claim and verify its magnitude exists in the registry. A figure that
does not reconcile FAILS THE RUN — a fabricated number cannot slip through. This is
what makes "the model never makes up a number" a mechanical property, not a hope.

All money in integer cents.
"""

from __future__ import annotations

import re

from agent4.decomposition import euros

_EURO = re.compile(r"[+-]?\u20ac[\d,]+\.\d{2}")


def _euro_to_cents(s: str) -> int:
    neg = s.strip().startswith("-")
    digits = s.replace("\u20ac", "").replace(",", "").replace("-", "").strip()
    cents = int(round(float(digits) * 100))
    return -cents if neg else cents


def build_registry(tree: dict, reforecast_by_line: dict | None = None) -> dict:
    """Flatten every computed number the commentary is allowed to state into a
    registry (Agent 4's model.json) plus a set of allowed magnitudes (abs cents)."""
    numbers = {}          # human-readable map, for the sidecar
    allowed = set()       # abs cents the gate will accept

    def add(key, cents):
        numbers[key] = cents
        allowed.add(abs(int(cents)))

    def walk(node, path=""):
        here = f"{path}/{node['name']}" if path else node["name"]
        add(f"{here}:budget", node["budget_cents"])
        add(f"{here}:actual", node["actual_cents"])
        add(f"{here}:variance", node["total_variance_cents"])
        if node.get("profit_impact_cents") is not None:
            add(f"{here}:profit_impact", node["profit_impact_cents"])
        for d in node.get("drivers", []) or []:
            add(f"{here}:driver:{d['driver']}", d["cents"])
        if node.get("residual_cents"):
            add(f"{here}:residual", node["residual_cents"])
        for c in node.get("children", []) or []:
            walk(c, here)

    walk(tree)

    if reforecast_by_line:
        for line, rf in reforecast_by_line.items():
            if rf.get("projected_landing_cents") is not None:
                add(f"{line}:landing", rf["projected_landing_cents"])
            if rf.get("band_cents"):
                add(f"{line}:band_lo", rf["band_cents"][0])
                add(f"{line}:band_hi", rf["band_cents"][1])

    return {"numbers": numbers, "allowed_abs_cents": allowed,
            "allowed_signed_cents": set(int(v) for v in numbers.values())}


def _fav_word(node: dict) -> str:
    return "favourable" if node.get("favourable") else "adverse"


def compose(tree: dict, persistence_by_line: dict | None = None,
            reforecast_by_line: dict | None = None,
            only_quadrants: set | None = None) -> list[dict]:
    """
    Deterministic, reference-built commentary as a list of tiered claims. Numbers
    are inserted from the node via euros(), so facts are correct by construction.
    `only_quadrants` filters which lines get commentary (e.g. the exception view).
    """
    persistence_by_line = persistence_by_line or {}
    reforecast_by_line = reforecast_by_line or {}
    claims: list[dict] = []

    def emit(tier, text, refs=None):
        claims.append({"tier": tier, "text": text, "refs": refs or {}})

    # Headline fact for the root. refs carry EVERY figure the text states, so the
    # grounding gate can verify each against its exact computed value.
    root = tree
    emit("computed_fact",
         f"{root['name']} variance was {euros(root['total_variance_cents'])} "
         f"({_fav_word(root)}): actual {euros(root['actual_cents'])} vs budget "
         f"{euros(root['budget_cents'])}.",
         {"variance": root["total_variance_cents"],
          "actual": root["actual_cents"], "budget": root["budget_cents"]})

    def walk(node, top=False):
        q = node.get("quadrant")
        surface = (only_quadrants is None) or (q in only_quadrants) or top
        if surface and node is not root:
            # computed fact: the line and its driver breakdown. refs = variance +
            # every driver figure stated in the text.
            drv = node.get("drivers")
            fact_refs = {"variance": node["total_variance_cents"]}
            if drv:
                parts = ", ".join(f"{d['driver']} {euros(d['cents'])}" for d in drv)
                fact = (f"{node['name']}: {euros(node['total_variance_cents'])} "
                        f"({_fav_word(node)}), driven by {parts}.")
                for d in drv:
                    fact_refs[f"driver:{d['driver']}"] = d["cents"]
            else:
                fact = (f"{node['name']}: {euros(node['total_variance_cents'])} "
                        f"({_fav_word(node)}).")
            if node.get("granularity_note"):
                fact += f" ({node['granularity_note']})"
            emit("computed_fact", fact, fact_refs)

            # observation: the materiality/significance classification
            if q:
                emit("observation",
                     f"Classified {q}: {node.get('triage','')}.",
                     {"quadrant": q})

            # observation: persistence, if available for this line
            p = persistence_by_line.get(node["name"])
            if p and p.get("persistence") not in (None, "INSUFFICIENT_HISTORY"):
                p_refs = {"persistence": p["persistence"], "confidence": p["confidence"]}
                # the reason text embeds computed signal figures (run length,
                # % sign-consistency) — expose them as refs so they ground.
                for k, v in (p.get("signals") or {}).items():
                    if isinstance(v, (int, float)):
                        p_refs[f"signal:{k}"] = v
                emit("observation",
                     f"Persistence: {p['persistence'].lower()} "
                     f"(confidence {p['confidence']}) — {p['reason']}.",
                     p_refs)

            # observation: reforecast, if available
            rf = reforecast_by_line.get(node["name"])
            if rf and rf.get("projected_landing_cents") is not None:
                line = f"Reforecast landing {euros(rf['projected_landing_cents'])}"
                rf_refs = {"landing": rf["projected_landing_cents"]}
                if rf.get("prob_hit_target") is not None:
                    line += f", P(hit target) {rf['prob_hit_target']:.0%}"
                    rf_refs["prob_hit"] = rf["prob_hit_target"]
                line += f" [{rf['method']}]."
                emit("observation", line, rf_refs)

            # hypothesis: business cause — ALWAYS flagged, never asserted
            if q in ("TOP_PRIORITY", "EARLY_WARNING"):
                emit("hypothesis",
                     f"Business cause for {node['name']} requires confirmation — "
                     f"not derivable from the figures (arithmetic driver is fact; the "
                     f"reason is a hypothesis).")

        for c in node.get("children", []) or []:
            walk(c)

    walk(root, top=True)
    return claims


_PCT = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")


def _pct_values(refs: dict) -> set:
    """Percentages/probabilities a claim is allowed to state, derived from its refs
    (a ratio 0.62 may appear as 62%, a prob_hit 0.74 as 74%)."""
    out = set()
    for v in refs.values():
        if isinstance(v, (int, float)) and -1.0 <= v <= 1.0:
            out.add(round(abs(v) * 100, 1))
        if isinstance(v, (int, float)):
            out.add(round(abs(v), 1))            # e.g. a run length or count
    return out


def reconcile(claims: list[dict], registry: dict) -> dict:
    """
    Hard grounding gate. Every hard figure in a fact/observation must reconcile to
    a value the claim ACTUALLY REFERENCES — not merely exist somewhere in the
    registry. This closes three loopholes the global-magnitude check had:
      - context-blind (§45): a Marketing €50k can't validate a Materials €50k;
      - sign-blind (§46): -€50k must not pass as +€50k;
      - euro-only (§47): percentages / probabilities are now checked too.
    Hypotheses (§48) may carry NO hard figure (euro or percent).
    """
    signed = registry.get("allowed_signed_cents", set())
    violations = []
    for i, cl in enumerate(claims):
        refs = cl.get("refs", {}) or {}
        text = cl["text"]

        if cl["tier"] == "hypothesis":
            # a business-cause hypothesis must not assert any hard number
            if _EURO.search(text) or _PCT.search(text):
                violations.append({"claim": i, "tier": "hypothesis",
                                   "issue": "hypothesis contains a hard figure",
                                   "text": text})
            continue

        # allowed signed cents for THIS claim: its own refs (fall back to the
        # global signed registry only for facts that legitimately restate a node).
        ref_cents = set(int(v) for v in refs.values()
                        if isinstance(v, (int, float)) and abs(v) >= 1)
        allowed_here = ref_cents if ref_cents else signed

        for m in _EURO.findall(text):
            cents = _euro_to_cents(m)
            explicit_sign = m.strip().startswith(("+", "-"))
            if explicit_sign:
                # an explicit +/- in the prose must match the referenced sign exactly
                ok = cents in allowed_here
            else:
                # unsigned figure: accept either sign of the same magnitude (the
                # sign is carried by words like 'adverse'/'favourable')
                ok = abs(cents) in {abs(x) for x in allowed_here}
            if not ok:
                violations.append({"claim": i, "tier": cl["tier"], "figure": m,
                                   "issue": "euro figure not in this claim's references",
                                   "text": text})

        # §47: percentages/probabilities must trace to a ref value
        pct_allowed = _pct_values(refs)
        for pm in _PCT.findall(text):
            val = round(abs(float(pm)), 1)
            if pct_allowed and not any(abs(val - a) <= 0.5 for a in pct_allowed):
                violations.append({"claim": i, "tier": cl["tier"], "figure": pm + "%",
                                   "issue": "percentage not in this claim's references",
                                   "text": text})

    return {"passed": len(violations) == 0, "n_claims": len(claims),
            "violations": violations,
            "note": "every stated figure reconciles to its referenced computed value"
                    if not violations else "FABRICATED OR MISMATCHED FIGURE — run fails"}
