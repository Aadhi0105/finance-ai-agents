"""
Validation / confidence gate (component #5, spec §3.1).

Scores a completed run and decides: emit, or flag for human review. Confidence is
COMPUTED from the run's own logged outputs, not guessed by the model grading
itself — deterministic, auditable, every check names its reason.

The distinction the gate turns on (and the fix vs. the old scorecard): not every
flag is a defect.
  - QUALITY_WARN  : a data/method problem (missing net income, stale filing,
                    implausible assumption, incomplete bridge) -> LOWERS confidence.
  - INFO_FINDING  : a legitimate result worth surfacing (a big DCF-vs-price gap,
                    a peer-method divergence) -> surfaced, but does NOT lower
                    confidence or block emission. A dramatic valuation gap is a
                    finding to explain, not a data error.
  - FAIL          : disqualifying (missing core data, nonsensical ratio) -> flag.
  - PASS          : the check is clean.

Only QUALITY_WARN and FAIL move the score. That stops three legitimate findings
from dragging an otherwise-clean run into review.
"""

from __future__ import annotations

from datetime import date, datetime


# Tunables (documented so a reviewer can see the thresholds).
_QUALITY_WARN_WEIGHT = 0.15   # each quality warn costs this off a 1.0 base
_FAIL_WEIGHT = 1.0            # a fail is disqualifying
_PASS_THRESHOLD = 0.70       # below this (or any fail) -> flag for review
_STALE_MONTHS = 18           # filing older than this warns
_AGGRESSIVE_GROWTH = 0.25    # DCF high_growth above this warns
_BIG_GAP = 0.50              # |DCF vs price| beyond this is a FINDING (not a fault)
_MIN_PEERS = 5               # fewer peers -> robust stats noisy


def assess(analysis: dict, now: date | None = None) -> dict:
    """Assess one run's analysis dict (state.results). Pure function."""
    checks: list[dict] = []

    def add(name, status, detail):
        # status in {"pass", "info_finding", "quality_warn", "fail"}
        checks.append({"check": name, "status": status, "detail": detail})

    fin = (analysis.get("get_financials") or {}).get("financials", {}) or {}
    prices = analysis.get("get_prices") or {}
    ratios = (analysis.get("compute_ratios") or {}).get("ratios", {}) or {}
    dcf = analysis.get("run_dcf") or {}
    dcf_a = dcf.get("assumptions", {}) or {}
    peer = analysis.get("peer_outlier_check") or {}

    # 1. Data completeness.
    missing = [k for k in ("revenue", "net_income") if fin.get(k) is None]
    if not prices.get("market_cap"):
        missing.append("market_cap")
    if not prices.get("shares_outstanding"):
        missing.append("shares_outstanding")
    if missing:
        hard = any(k in missing for k in ("net_income", "market_cap"))
        add("data_completeness", "fail" if hard else "quality_warn",
            f"missing: {', '.join(missing)}")
    else:
        add("data_completeness", "pass", "all key fields present")

    # 2. FCF quality.
    src = dcf_a.get("fcf_source", "")
    if "fallback" in src:
        add("fcf_quality", "quality_warn", "DCF ran on net-income proxy (no real FCF)")
    elif src:
        add("fcf_quality", "pass", "DCF used real free cash flow")

    # 3. Net-debt bridge complete vs incomplete.
    bstatus = dcf_a.get("net_debt_bridge_status")
    if bstatus == "incomplete":
        add("net_debt_bridge", "quality_warn",
            "net-debt bridge incomplete — DCF reports enterprise value only, not equity")
    elif bstatus == "complete":
        add("net_debt_bridge", "pass", "net-debt bridge complete (debt and cash known)")

    # 4. Filing recency.
    period = fin.get("period")
    if period:
        try:
            pdate = datetime.fromisoformat(str(period)).date()
            ref = now or date.today()
            months = (ref.year - pdate.year) * 12 + (ref.month - pdate.month)
            if months > _STALE_MONTHS:
                add("filing_recency", "quality_warn", f"latest financials ~{months} months old")
            else:
                add("filing_recency", "pass", f"financials ~{max(months,0)} months old")
        except Exception:
            add("filing_recency", "quality_warn", f"could not parse filing period '{period}'")

    # 5a. Implausible growth assumption -> quality warn.
    hg = dcf_a.get("high_growth")
    if isinstance(hg, (int, float)):
        if hg > _AGGRESSIVE_GROWTH:
            add("growth_assumption", "quality_warn",
                f"DCF high_growth {hg:.0%} is aggressive (>{_AGGRESSIVE_GROWTH:.0%})")
        else:
            add("growth_assumption", "pass", f"DCF high_growth {hg:.0%} within normal range")

    # 5b. Valuation gap -> INFO FINDING (surface, do NOT fault).
    up = dcf.get("implied_upside")
    if isinstance(up, (int, float)):
        if abs(up) > _BIG_GAP:
            add("valuation_gap", "info_finding",
                f"DCF fair value diverges {up:+.0%} from price — a finding to explain")
        else:
            add("valuation_gap", "pass", f"DCF within {_BIG_GAP:.0%} of price ({up:+.0%})")

    # 5c. Terminal-value concentration -> INFO FINDING when very high.
    tvc = (dcf.get("terminal_value_concentration") or {}).get("base")
    if isinstance(tvc, (int, float)):
        if tvc > 0.85:
            add("terminal_value_concentration", "info_finding",
                f"{tvc:.0%} of DCF value is terminal value — highly terminal-sensitive")
        else:
            add("terminal_value_concentration", "pass", f"terminal value {tvc:.0%} of DCF")

    # 6. Peer robustness.
    if peer and not peer.get("error"):
        n = peer.get("n_peers", len(peer.get("peer_pes", {}) or {}))
        if n < _MIN_PEERS:
            add("peer_sample_size", "quality_warn",
                f"only {n} peers — robust stats noisy below {_MIN_PEERS}")
        else:
            add("peer_sample_size", "pass", f"{n} peers")
        if peer.get("verdict_divergence"):
            add("peer_method_agreement", "info_finding",
                "robust and mean-based peer verdicts diverge (peer set is skewed)")

    # 7. Ratio sanity (margins within [-1, 1]).
    bad = [k for k, v in ratios.items()
           if k.endswith("margin") and isinstance(v, (int, float)) and (v < -1 or v > 1)]
    if bad:
        add("ratio_sanity", "fail", f"implausible margin(s): {', '.join(bad)}")
    elif ratios:
        add("ratio_sanity", "pass", "margins within plausible range")

    # 8. Comparison basis.
    consensus = analysis.get("get_consensus") or {}
    trend = analysis.get("get_historical_trend") or {}
    if consensus.get("available"):
        add("comparison_basis", "pass", "anchored to analyst consensus")
    elif trend and not trend.get("error"):
        add("comparison_basis", "pass", "consensus unavailable — fell back to company history")
    elif consensus or trend:
        add("comparison_basis", "quality_warn", "no usable comparison basis")

    return aggregate_checks(checks)


def aggregate_checks(checks: list[dict]) -> dict:
    """Score a checks list -> verdict/confidence/counts. Exposed so a later stage
    (e.g. note grounding) can add a check and RE-AGGREGATE, keeping score, verdict,
    and confidence mutually consistent (no 'score 1.0 but 1 fail' contradictions).
    Only quality_warn and fail move the score; info_finding never does."""
    fails = [c for c in checks if c["status"] == "fail"]
    quality_warns = [c for c in checks if c["status"] == "quality_warn"]
    findings = [c for c in checks if c["status"] == "info_finding"]
    passes = [c for c in checks if c["status"] == "pass"]
    score = round(max(0.0, 1.0 - _QUALITY_WARN_WEIGHT * len(quality_warns)
                      - _FAIL_WEIGHT * len(fails)), 2)

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
        "n_pass": len(passes),
        "n_info_finding": len(findings),
        "n_quality_warn": len(quality_warns),
        "n_fail": len(fails),
        "checks": checks,
        "thresholds": {"pass_threshold": _PASS_THRESHOLD,
                       "quality_warn_weight": _QUALITY_WARN_WEIGHT,
                       "note": "info_finding does not affect the score"},
        "assessed_by": "validation.gate (deterministic, python)",
    }
