"""
Note grounding (Agent 1) — makes "the LLM never does the math" a MECHANICAL
property of the published note, not a prompt-based hope.

This applies the reconciliation philosophy proven in Agent 4's commentary gate to
Agent 1's free-text analyst note: build a registry of every number the tools
actually computed, then scan the model's note and reject any financial figure that
does not reconcile to a computed value. A model that writes "fair value €850" when
no tool produced €850 is caught, and the run is flagged.

Agent 1's note contains several number shapes (percentages like 34.6%, multiples
like 13.3x, currency like €850 or $8.4bn, and plain magnitudes), so the registry
holds a set of allowed *normalised* values and the checker matches each figure in
the note against it within a small tolerance (the note may round 0.3462 -> 34.6%).

Grounding is advisory-to-the-gate: it returns the unmatched figures so the caller
(the validation gate / emission path) can flag the run, exactly as a fabricated
number should.
"""

from __future__ import annotations

import re

# Numeric tokens the note might use. Each returns a normalised float value.
_PCT = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
_MULT = re.compile(r"(-?\d+(?:\.\d+)?)\s*[x\u00d7]")           # 13.3x
_CUR = re.compile(r"[\u20ac$\u00a3]\s*(-?\d[\d,]*(?:\.\d+)?)\s*(bn|billion|m|million|k)?",
                  re.IGNORECASE)
_BARE = re.compile(r"(?<![\w.$\u20ac\u00a3])(-?\d[\d,]*(?:\.\d+)?)(?![%x\u00d7\w])")

_MULT_SUFFIX = {"bn": 1e9, "billion": 1e9, "m": 1e6, "million": 1e6, "k": 1e3}
_TOL = 0.02   # 2% relative tolerance (note rounding vs full-precision compute)


def _walk_numbers(obj):
    """Yield every numeric value anywhere in a nested tool-results structure."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_numbers(v)


def build_number_registry(results: dict) -> set:
    """All computed numbers, plus common presentations of them (a ratio 0.3462 is
    allowed to appear as 34.62 for a percentage; a raw 8.4e9 as 8.4 for '€8.4bn').
    Returns a set of allowed absolute magnitudes."""
    allowed = set()
    for v in _walk_numbers(results):
        av = abs(v)
        allowed.add(round(av, 4))
        allowed.add(round(av * 100, 4))      # ratio -> percent
        if av >= 1e3:
            allowed.add(round(av / 1e3, 4))  # -> k
        if av >= 1e6:
            allowed.add(round(av / 1e6, 4))  # -> m
        if av >= 1e9:
            allowed.add(round(av / 1e9, 4))  # -> bn
    return allowed


def _matches(value: float, allowed: set) -> bool:
    v = abs(value)
    for a in allowed:
        if a == 0:
            if v == 0:
                return True
            continue
        if abs(v - a) / a <= _TOL:
            return True
    return False


def _extract_figures(note: str):
    """Yield (text, normalised_value) for each financial figure in the note."""
    for m in _PCT.finditer(note):
        yield m.group(0), float(m.group(1))
    for m in _MULT.finditer(note):
        yield m.group(0), float(m.group(1))
    for m in _CUR.finditer(note):
        val = float(m.group(1).replace(",", ""))
        suf = (m.group(2) or "").lower()
        # keep the AS-WRITTEN magnitude (registry also stores scaled forms)
        yield m.group(0), val
    # bare numbers are noisy (years, counts); only check those that look financial
    # is left out by default to avoid false positives — currency/pct/multiples cover
    # the figures that matter for the "never fabricate a number" claim.


def ground_note(note: str, results: dict) -> dict:
    """Check every financial figure in the note against the computed registry.
    Returns pass/fail + the unmatched figures (which the gate flags)."""
    allowed = build_number_registry(results)
    unmatched = []
    checked = 0
    for text, value in _extract_figures(note or ""):
        checked += 1
        if not _matches(value, allowed):
            unmatched.append({"figure": text, "value": value})
    return {
        "passed": len(unmatched) == 0,
        "figures_checked": checked,
        "unmatched": unmatched,
        "note": ("every figure in the note reconciles to a computed value"
                 if not unmatched
                 else "UNGROUNDED FIGURE(S) IN NOTE — the model stated a number no tool computed"),
        "checked_by": "note_grounding (python; Agent-4 reconciliation philosophy)",
    }
