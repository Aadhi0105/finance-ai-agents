"""
Validation / confidence gate (component #5, spec §3.1).

Scores a completed run and decides: emit, or flag for human review. The whole
point is that confidence is COMPUTED from the run's own logged outputs, not
guessed by the model grading itself — deterministic, auditable, every flag names
its reason. This mirrors the covenant demo's human-in-the-loop layer.

Design rule that keeps it honest: distinguish
  - DATA-QUALITY problems (missing net income, stale filing, implausible
    assumptions, nonsensical ratios) -> these lower confidence / flag for review;
  - NOTABLE FINDINGS (a big DCF-vs-price gap, a peer-method divergence) -> these
    are legitimate results, so they are surfaced as flags but do NOT by
    themselves block emission.

A finance reviewer should be able to read the check list and know exactly why a
run was passed or held.
"""

from __future__ import annotations

from datetime import date, datetime


# Tunables (documented so a reviewer can see the thresholds).
_WARN_WEIGHT = 0.15         # each warn costs this off a 1.0 base
_PASS_THRESHOLD = 0.70      # below this (or any fail) -> flag for review
_STALE_MONTHS = 18          # filing older than this warns
_AGGRESSIVE_GROWTH = 0.25   # DCF high_growth above this warns
_BIG_GAP = 0.50             # |DCF vs price| beyond this warns (a finding, not a fault)
_MIN_PEERS = 5              # fewer peers -> robust stats noisy


def assess(analysis: dict, now: date | None = None) -> dict:
    """Assess one run's analysis dict (state.results). Pure function."""
    checks: list[dict] = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    fin = (analysis.get("get_financials") or {}).get("financials", {}) or {}
    prices = analysis.get("get_prices") or {}
    ratios = (analysis.get("compute_ratios") or {}).get("ratios", {}) or {}
    dcf = analysis.get("run_dcf") or {}
    dcf_a = dcf.get("assumptions", {}) or {}
    peer = analysis.get("peer_outlier_check") or {}

    # 1. Data completeness (missing net income or market cap is disqualifying).
    missing = [k for k in ("revenue", "net_income") if not fin.get(k)]
    if not prices.get("market_cap"):
        missing.append("market_cap")
    if not prices.get("shares_outstanding"):
        missing.append("shares_outstanding")
    if missing:
        hard = any(k in missing for k in ("net_income", "market_cap"))
        add("data_completeness", "fail" if hard else "warn", f"missing: {', '.join(missing)}")
    else:
        add("data_completeness", "pass", "all key fields present")

    # 2. FCF quality — real cash flow vs a net-income proxy.
    src = dcf_a.get("fcf_source", "")
    if "fallback" in src:
        add("fcf_quality", "warn", "DCF ran on net-income proxy (no real FCF available)")
    elif src:
        add("fcf_quality", "pass", "DCF used real free cash flow")

    # 3. Net-debt bridge known vs approximated.
    ndn = dcf_a.get("net_debt_note", "")
    if "approximated" in ndn:
        add("net_debt_bridge", "warn", "equity approximated by EV (net-debt items unavailable)")
    elif ndn:
        add("net_debt_bridge", "pass", "net-debt bridge applied")

    # 4. Filing recency (stale filing -> warn).
    period = fin.get("period")
    if period:
        try:
            pdate = datetime.fromisoformat(str(period)).date()
            ref = now or date.today()
            months = (ref.year - pdate.year) * 12 + (ref.month - pdate.month)
            if months > _STALE_MONTHS:
                add("filing_recency", "warn", f"latest financials are ~{months} months old")
            else:
                add("filing_recency", "pass", f"financials ~{max(months,0)} months old")
        except Exception:
            add("filing_recency", "warn", f"could not parse filing period '{period}'")

    # 5a. Implausible growth assumption (spec's example).
    hg = dcf_a.get("high_growth")
    if isinstance(hg, (int, float)):
        if hg > _AGGRESSIVE_GROWTH:
            add("growth_assumption", "warn", f"DCF high_growth {hg:.0%} is aggressive (>{_AGGRESSIVE_GROWTH:.0%})")
        else:
            add("growth_assumption", "pass", f"DCF high_growth {hg:.0%} within normal range")

    # 5b. Valuation gap — a FINDING, so warn (surface) but don't fault.
    up = dcf.get("implied_upside")
    if isinstance(up, (int, float)):
        if abs(up) > _BIG_GAP:
            add("valuation_gap", "warn",
                f"DCF fair value diverges {up:+.0%} from price — a finding to explain, not a data error")
        else:
            add("valuation_gap", "pass", f"DCF within {_BIG_GAP:.0%} of price ({up:+.0%})")

    # 6. Peer robustness.
    if peer:
        n = len(peer.get("peer_pes", {}) or {})
        if n < _MIN_PEERS:
            add("peer_sample_size", "warn", f"only {n} peers — robust stats noisy below {_MIN_PEERS}")
        else:
            add("peer_sample_size", "pass", f"{n} peers")
        if peer.get("verdict_divergence"):
            add("peer_method_agreement", "warn",
                "robust and mean-based peer verdicts diverge (peer set is skewed)")

    # 7. Ratio sanity (margins should be within [-1, 1]).
    bad = [k for k, v in ratios.items()
           if k.endswith("margin") and isinstance(v, (int, float)) and (v < -1 or v > 1)]
    if bad:
        add("ratio_sanity", "fail", f"implausible margin(s): {', '.join(bad)}")
    elif ratios:
        add("ratio_sanity", "pass", "margins within plausible range")

    # 8. Comparison basis — did the run anchor its view to consensus, or fall
    # back to the company's own history? Neither is a real gap.
    consensus = analysis.get("get_consensus") or {}
    trend = analysis.get("get_historical_trend") or {}
    if consensus.get("available"):
        add("comparison_basis", "pass", "anchored to analyst consensus")
    elif trend and not trend.get("error"):
        add("comparison_basis", "pass", "consensus unavailable — fell back to company's own history")
    elif consensus or trend:
        add("comparison_basis", "warn", "no usable comparison basis (consensus null and no trend)")

    # --- aggregate ---
    fails = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]
    score = round(max(0.0, 1.0 - _WARN_WEIGHT * len(warns) - 1.0 * len(fails)), 2)

    if fails or score < _PASS_THRESHOLD:
        verdict = "flag_for_review"
        confidence = "low" if fails else "medium"
    else:
        verdict = "pass"
        confidence = "high"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "score": score,
        "n_pass": len([c for c in checks if c["status"] == "pass"]),
        "n_warn": len(warns),
        "n_fail": len(fails),
        "checks": checks,
        "thresholds": {"pass_threshold": _PASS_THRESHOLD, "warn_weight": _WARN_WEIGHT},
        "assessed_by": "validation.gate (deterministic, python)",
    }
