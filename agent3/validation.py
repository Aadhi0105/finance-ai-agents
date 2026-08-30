"""
Validation / confidence gate (Agent 3). Mirrors Agent 1's gate shape — a pure
assess() returning named checks with pass/warn/fail + reasons — but the checks
are the ones that matter for an EVENT STUDY, not a valuation.

The whole point (same as Agent 1): confidence is COMPUTED from the study's own
outputs, not guessed. Every flag names its reason so a reviewer knows exactly why
a result was passed or held.

The three Agent-3-specific failure modes:

  1. CONFOUND — a "significant" CAAR that is really an index-wide move on the same
     day, not a firm-specific reaction. The market-model event study already
     strips market beta, so this is a second line of defence: if abnormal returns
     cluster suspiciously tightly (all events moved the same way) OR the event set
     spans few distinct dates (so one macro day drives many "events"), flag it.
  2. THIN DATA — too few usable events / too few contributing peers for the CAAR
     test to carry weight. Low N is reported by the study; the gate escalates it
     to a hold when it's below a review threshold.
  3. MULTIPLE TESTING — if many event types were tested and this one came up
     significant, a single p<0.05 is not what it seems (test 20, expect ~1 false
     positive). The gate flags significance that hasn't been multiplicity-adjusted.

Design rule carried from Agent 1: distinguish a DATA/METHOD problem (lowers
confidence, may hold) from a NOTABLE FINDING (surfaced but doesn't block). An
insignificant result is not a fault — it's an honest null and passes cleanly.
"""

from __future__ import annotations

# Tunables (documented so a reviewer sees the thresholds).
_WARN_WEIGHT = 0.15
_PASS_THRESHOLD = 0.70
_MIN_EVENTS_OK = 10          # below this, thin-data warns; the study's own floor is 5
_MIN_PEERS_OK = 3            # a CAAR resting on <3 firms is fragile
_CONFOUND_DISPERSION = 0.004  # if per-event CAR stdev is below this AND significant,
#                              the events are suspiciously uniform -> possible macro confound
_BONFERRONI_HINT = 0.05


def assess(study: dict, *, contributing_peers: int | None = None,
           n_event_types_tested: int = 1) -> dict:
    """
    Assess one event-study result (the dict from run_event_study). Pure function.

    contributing_peers  : distinct firms that supplied events (for the confound /
                          thin-data checks); defaults to n_events if unknown.
    n_event_types_tested: how many event types were tested this session — drives
                          the multiple-testing check.
    """
    checks: list[dict] = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    n = study.get("n_events", 0) or 0
    caar = study.get("caar")
    significant = study.get("caar_significant")
    p_value = study.get("p_value")
    per_event = study.get("per_event") or []
    peers = contributing_peers if contributing_peers is not None else n

    # --- 1. thin data -------------------------------------------------------
    if n < _MIN_EVENTS_OK or peers < _MIN_PEERS_OK:
        add("thin_data", "warn",
            f"N={n} events across {peers} peer(s) — low power; CAAR estimate is noisy")
    else:
        add("thin_data", "pass", f"N={n} events across {peers} peers — adequate")

    # --- 2. confound (index-wide move masquerading as firm-specific) --------
    # Only meaningful when the study claims significance.
    if significant and per_event:
        cars = [e.get("car", 0.0) for e in per_event]
        mean = sum(cars) / len(cars)
        var = sum((c - mean) ** 2 for c in cars) / len(cars)
        dispersion = var ** 0.5
        n_dates = len({e.get("event_date") for e in per_event})
        if dispersion < _CONFOUND_DISPERSION:
            add("confound", "warn",
                f"significant CAAR but per-event dispersion {dispersion:.4f} is very low — "
                f"events moved almost identically; check for a shared macro driver")
        elif n_dates < max(3, n // 3):
            add("confound", "warn",
                f"significant CAAR but only {n_dates} distinct event dates across {n} events — "
                f"a single macro day may drive several 'events'")
        else:
            add("confound", "pass",
                f"per-event dispersion {dispersion:.4f} across {n_dates} distinct dates — firm-specific")
    else:
        add("confound", "pass", "no significant CAAR to confound (or no per-event detail)")

    # --- 3. multiple testing ------------------------------------------------
    if significant and n_event_types_tested > 1:
        adj = _BONFERRONI_HINT / n_event_types_tested
        survives = (p_value is not None and p_value < adj)
        if survives:
            add("multiple_testing", "pass",
                f"p={p_value} survives Bonferroni adj ({adj:.4f}) for {n_event_types_tested} tests")
        else:
            add("multiple_testing", "warn",
                f"significant at 0.05 but {n_event_types_tested} event types were tested; "
                f"p={p_value} does not clear Bonferroni {adj:.4f} — likely a false positive")
    else:
        add("multiple_testing", "pass",
            "single event type tested — no multiplicity inflation" if significant
            else "result not significant — multiplicity not at issue")

    # --- score & verdict ----------------------------------------------------
    # Not all warns are equal: a confound or multiple-testing warn on a
    # significant result means "this finding may be illusory" — heavier than a
    # generic thin-data note. Those are exactly the cases a human should see.
    _HEAVY = {"confound", "multiple_testing"}
    penalty = 0.0
    for c in checks:
        if c["status"] == "warn":
            penalty += 0.30 if c["check"] in _HEAVY else _WARN_WEIGHT
        elif c["status"] == "fail":
            penalty += 0.5
    confidence = max(0.0, 1.0 - penalty)
    warns = sum(1 for c in checks if c["status"] == "warn")
    fails = sum(1 for c in checks if c["status"] == "fail")
    hold = fails > 0 or confidence < _PASS_THRESHOLD or \
        any(c["status"] == "warn" and c["check"] in _HEAVY for c in checks)

    return {
        "checks": checks,
        "n_warn": warns, "n_fail": fails,
        "confidence": round(confidence, 3),
        "verdict": "HOLD_FOR_REVIEW" if hold else "PASS",
        "note": ("An insignificant CAAR is an honest null and passes; holds are for "
                 "data/method concerns, not for the direction of the finding."),
        "computed_by": "agent3.validation.assess (python)",
    }
