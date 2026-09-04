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

_EURO = re.compile(r"-?\u20ac[\d,]+\.\d{2}")


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

    return {"numbers": numbers, "allowed_abs_cents": allowed}


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

    # Headline fact for the root.
    root = tree
    emit("computed_fact",
         f"{root['name']} variance was {euros(root['total_variance_cents'])} "
         f"({_fav_word(root)}): actual {euros(root['actual_cents'])} vs budget "
         f"{euros(root['budget_cents'])}.",
         {"variance": root["total_variance_cents"]})

    def walk(node, top=False):
        q = node.get("quadrant")
        surface = (only_quadrants is None) or (q in only_quadrants) or top
        if surface and node is not root:
            # computed fact: the line and its driver breakdown
            drv = node.get("drivers")
            if drv:
                parts = ", ".join(f"{d['driver']} {euros(d['cents'])}" for d in drv)
                fact = (f"{node['name']}: {euros(node['total_variance_cents'])} "
                        f"({_fav_word(node)}), driven by {parts}.")
            else:
                fact = (f"{node['name']}: {euros(node['total_variance_cents'])} "
                        f"({_fav_word(node)}).")
            if node.get("granularity_note"):
                fact += f" ({node['granularity_note']})"
            emit("computed_fact", fact, {"variance": node["total_variance_cents"]})

            # observation: the materiality/significance classification
            if q:
                emit("observation",
                     f"Classified {q}: {node.get('triage','')}.",
                     {"quadrant": q})

            # observation: persistence, if available for this line
            p = persistence_by_line.get(node["name"])
            if p and p.get("persistence") not in (None, "INSUFFICIENT_HISTORY"):
                emit("observation",
                     f"Persistence: {p['persistence'].lower()} "
                     f"(confidence {p['confidence']}) — {p['reason']}.",
                     {"persistence": p["persistence"]})

            # observation: reforecast, if available
            rf = reforecast_by_line.get(node["name"])
            if rf and rf.get("projected_landing_cents") is not None:
                line = f"Reforecast landing {euros(rf['projected_landing_cents'])}"
                if rf.get("prob_hit_target") is not None:
                    line += f", P(hit target) {rf['prob_hit_target']:.0%}"
                line += f" [{rf['method']}]."
                emit("observation", line, {"landing": rf["projected_landing_cents"]})

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


def reconcile(claims: list[dict], registry: dict) -> dict:
    """Hard gate: every euro figure in a fact/observation claim must reconcile to a
    magnitude in the registry. Hypotheses carry no hard figures. Returns pass/fail
    with any violations named."""
    allowed = registry["allowed_abs_cents"]
    violations = []
    for i, cl in enumerate(claims):
        if cl["tier"] == "hypothesis":
            # a hypothesis must NOT assert a hard figure
            if _EURO.search(cl["text"]):
                violations.append({"claim": i, "tier": cl["tier"],
                                   "issue": "hypothesis contains a hard figure",
                                   "text": cl["text"]})
            continue
        for m in _EURO.findall(cl["text"]):
            cents = abs(_euro_to_cents(m))
            if cents not in allowed:
                violations.append({"claim": i, "tier": cl["tier"],
                                   "figure": m, "issue": "figure not in computed registry",
                                   "text": cl["text"]})
    return {"passed": len(violations) == 0, "n_claims": len(claims),
            "violations": violations,
            "note": "every stated figure reconciles to the computed model.json"
                    if not violations else "FABRICATED OR MISMATCHED FIGURE — run fails"}
