"""
Change classification (spec §3.3, State).

The 2x2 on (breached-last x breached-this), refined by magnitude. Status is a
first-class stored field — computed once here, then persisted, never recomputed
downstream.

    is_baseline (cold start)        -> BASELINE   (record state, suppress alerts)
    not last, not this              -> OK         (log only, not surfaced)
    not last, breached this         -> NEW_BREACH (surface, high)
    breached last, not this         -> RESOLVED   (surface, then drops next cycle)
    breached both, worse            -> WIDENING   (re-surface with trajectory)
    breached both, better           -> IMPROVING  (surface, lower urgency)
    breached both, same             -> KNOWN_STABLE (suppress)

Cold start: the FIRST time an item is seen (including cycle 1) we only establish
state — real change-detection begins the next cycle. This avoids a wall of false
NEW_BREACH alerts on the first run.

`last` is the item's previous current-state row (dict) or None if unseen.
`margin` follows threshold_check's convention: >0 means in-breach by that much.
"""

from __future__ import annotations

_EPS = 1e-9

# Statuses that the exception report surfaces (everything else is suppressed).
SURFACED = {"NEW_BREACH", "WIDENING", "IMPROVING", "RESOLVED"}


def classify(last: dict | None, breached_this: bool, margin_this: float,
             is_baseline: bool) -> str:
    # Cold start / first sighting: establish state only.
    if is_baseline or last is None:
        return "BASELINE"

    breached_last = bool(last.get("breached"))
    margin_last = last.get("margin", 0.0)

    if not breached_last and not breached_this:
        return "OK"
    if not breached_last and breached_this:
        return "NEW_BREACH"
    if breached_last and not breached_this:
        return "RESOLVED"

    # Breached in both cycles: compare how deep the breach is.
    if margin_this > margin_last + _EPS:
        return "WIDENING"
    if margin_this < margin_last - _EPS:
        return "IMPROVING"
    return "KNOWN_STABLE"
