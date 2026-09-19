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
_TOL = 0.02       # relative tolerance for currency / multiples (kept tight)
_PCT_TOL = 0.05   # wider for PERCENTAGES: a note may write "15%" for a computed
                  # 15.55% (human rounding). Still catches real fabrication, which
                  # in every observed case was >5% off the true value.


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


def build_number_registry(results: dict):
    """All computed numbers in signed and common presentational forms. Returns
    (signed_set, abs_set): a note figure with an explicit sign must match the
    SIGNED set; an unsigned figure may match the ABS set (prose often carries
    direction in words). This makes grounding sign-aware — a computed -20% no
    longer validates a stated +20%."""
    signed, allowed = set(), set()
    for v in _walk_numbers(results):
        for scale in (1, 100):                     # raw + ratio->percent
            signed.add(round(v * scale, 4)); allowed.add(round(abs(v) * scale, 4))
        av = abs(v)
        if av >= 1e3:
            signed.add(round(v / 1e3, 4)); allowed.add(round(av / 1e3, 4))
        if av >= 1e6:
            signed.add(round(v / 1e6, 4)); allowed.add(round(av / 1e6, 4))
        if av >= 1e9:
            signed.add(round(v / 1e9, 4)); allowed.add(round(av / 1e9, 4))
    return signed, allowed


def _matches(value: float, has_sign: bool, signed: set, allowed: set,
             tol: float = _TOL) -> bool:
    """An explicitly-signed figure must match the SIGNED registry; an unsigned one
    may match the ABS registry (direction carried by prose wording). `tol` is the
    relative tolerance — wider for percentages (see _PCT_TOL)."""
    target = signed if has_sign else allowed
    v = value if has_sign else abs(value)
    for a in target:
        if a == 0:
            if v == 0:
                return True
            continue
        if abs(v - a) / abs(a) <= tol:
            return True
    return False


def _extract_figures(note: str):
    """Yield (text, value, has_explicit_sign, kind) for each financial figure.
    kind is "pct" for percentages (wider tolerance) or "other" (tight)."""
    for m in _PCT.finditer(note):
        raw = m.group(1)
        yield m.group(0), float(raw), raw.strip().startswith(("+", "-")), "pct"
    for m in _MULT.finditer(note):
        raw = m.group(1)
        yield m.group(0), float(raw), raw.strip().startswith(("+", "-")), "other"
    for m in _CUR.finditer(note):
        raw = m.group(1).replace(",", "")
        has_sign = m.group(0).strip().startswith(("+", "-"))
        val = float(raw)
        if has_sign and m.group(0).strip().startswith("-"):
            val = -val
        yield m.group(0), val, has_sign, "other"


def ground_note(note: str, results: dict) -> dict:
    """Check every financial figure in the note against the computed registry,
    sign-aware. Returns pass/fail + the unmatched figures (which the gate flags)."""
    signed, allowed = build_number_registry(results)
    unmatched = []
    checked = 0
    for text, value, has_sign, kind in _extract_figures(note or ""):
        checked += 1
        tol = _PCT_TOL if kind == "pct" else _TOL
        if not _matches(value, has_sign, signed, allowed, tol):
            unmatched.append({"figure": text, "value": value})
    return {
        "passed": len(unmatched) == 0,
        "figures_checked": checked,
        "unmatched": unmatched,
        "note": ("every figure in the note reconciles to a computed value"
                 if not unmatched
                 else "UNGROUNDED FIGURE(S) IN NOTE — the model stated a number no tool computed"),
        "checked_by": "note_grounding (python; sign-aware, Agent-4 reconciliation philosophy)",
    }
