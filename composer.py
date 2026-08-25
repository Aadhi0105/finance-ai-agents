"""
Output composer (component #6, spec §3.1) — the presentation layer.

Two responsibilities, deliberately split so the report is REBUILDABLE FROM THE
SIDECAR ALONE:

  write_sidecar(...)  -> writes model.json: every analysis number + the note +
                         the chart data (price history). Self-contained record
                         of one run.
  build_report(path)  -> reads model.json and NOTHING ELSE (no yfinance, no
                         model call), renders the chart(s), and writes a
                         self-contained report.html. Because it only reads the
                         sidecar, it structurally proves every chart is driven
                         by a logged number.

This checkpoint wires ONE chart end-to-end (price + 50/200-day moving averages).
The other four charts plug into render step the same way, next checkpoint.

Moving averages are computed here in plain Python — the "LLM never does the
math" rule extends to chart data too.
"""

from __future__ import annotations

import base64
import io
import json
import os
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")  # headless; no display needed
import matplotlib.pyplot as plt


# --- deterministic helpers ------------------------------------------------

def _sma(values: list[float], window: int) -> list:
    """Simple moving average; None until the window fills. Pure Python."""
    out, running = [], []
    for v in values:
        running.append(v)
        if len(running) > window:
            running.pop(0)
        out.append(sum(running) / window if len(running) == window else None)
    return out


def _daily_returns(closes: list[float]) -> list:
    return [None] + [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]


def _rolling_vol(closes: list[float], window: int = 30) -> list:
    """Annualised rolling volatility of daily returns. None until window fills."""
    import statistics, math
    rets = _daily_returns(closes)
    out = []
    for i in range(len(rets)):
        w = [r for r in rets[max(0, i - window + 1): i + 1] if r is not None]
        out.append(statistics.pstdev(w) * math.sqrt(252) if len(w) >= window else None)
    return out


def _drawdown(closes: list[float]) -> list:
    """Drawdown series vs running peak (0 at a new high, negative below)."""
    out, peak = [], closes[0]
    for c in closes:
        peak = max(peak, c)
        out.append(c / peak - 1)
    return out


def _align_on_dates(a: list[dict], b: list[dict]):
    """Intersect two date/close series, return (dates, a_close, b_close) aligned."""
    am = {r["date"]: r["close"] for r in a}
    bm = {r["date"]: r["close"] for r in b}
    common = sorted(set(am) & set(bm))
    return common, [am[d] for d in common], [bm[d] for d in common]


def _finish(fig) -> bytes:
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    return buf.getvalue()


def _thin_xticks(ax, dates):
    step = max(1, len(dates) // 8)
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)],
                       rotation=45, fontsize=7, ha="right")


# --- chart rendering ------------------------------------------------------

def render_price_ma_png(history: list[dict], ticker: str) -> bytes:
    """Chart 2 (price action, simplified): close price + 50/200-day SMAs."""
    dates = [row["date"] for row in history]
    closes = [row["close"] for row in history]
    ma50 = _sma(closes, 50)
    ma200 = _sma(closes, 200)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(dates, closes, linewidth=1.2, label="Close")
    ax.plot(dates, ma50, linewidth=1.0, label="50-day MA")
    ax.plot(dates, ma200, linewidth=1.0, label="200-day MA")
    ax.set_title(f"{ticker} — price and moving averages")
    ax.set_ylabel("Price")
    ax.legend(loc="best", fontsize=8)
    _thin_xticks(ax, dates)
    return _finish(fig)


def render_dcf_footballfield_png(dcf: dict, ticker: str) -> bytes:
    """Chart 5: DCF bear/base/bull range vs current price (the valuation gap)."""
    vps = dcf.get("value_per_share", {})
    bear, base, bull = vps.get("bear"), vps.get("base"), vps.get("bull")
    weighted = dcf.get("probability_weighted_per_share")
    price = dcf.get("current_price")

    fig, ax = plt.subplots(figsize=(9, 2.8))
    y = 0
    # DCF range bar (bear -> bull)
    ax.plot([bear, bull], [y, y], linewidth=10, alpha=0.35, solid_capstyle="round",
            color="#4c78a8", zorder=1)
    for val, lab in [(bear, "Bear"), (base, "Base"), (bull, "Bull")]:
        ax.scatter([val], [y], s=40, color="#4c78a8", zorder=3)
        ax.annotate(f"{lab}\n€{val:,.0f}", (val, y), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=7)
    if weighted:
        ax.scatter([weighted], [y], marker="D", s=70, color="#2a2a2a", zorder=4,
                   label=f"Prob-weighted €{weighted:,.0f}")
    if price:
        ax.axvline(price, color="#d1495b", linestyle="--", linewidth=1.5,
                   label=f"Current price €{price:,.0f}")
    ax.set_yticks([])
    ax.set_xlabel("Value per share (€)")
    ax.set_title(f"{ticker} — DCF football field vs current price")
    ax.legend(loc="lower right", fontsize=7)
    ax.margins(x=0.12, y=0.6)
    return _finish(fig)


def render_peer_scatter_png(peer: dict, ticker: str) -> bytes:
    """Chart 4: each peer's P/E with the target highlighted; median + MAD band."""
    peer_pes = peer.get("peer_pes", {})
    target_pe = peer.get("target_pe")
    median = peer.get("peer_median")
    mad = peer.get("peer_mad")

    names = list(peer_pes.keys()) + [ticker]
    vals = list(peer_pes.values()) + [target_pe]
    colors = ["#4c78a8"] * len(peer_pes) + ["#d1495b"]  # target in red

    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.scatter(range(len(names)), vals, s=[45] * len(peer_pes) + [110], color=colors, zorder=3)
    for i, v in enumerate(vals):
        ax.annotate(f"{v:.1f}", (i, v), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=7)
    if median is not None:
        ax.axhline(median, color="#666", linestyle="-", linewidth=1, label=f"Peer median {median:.1f}")
        if mad:
            ax.axhspan(median - mad, median + mad, color="#999", alpha=0.12, label="± MAD")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("P/E")
    verdict = "outlier" if peer.get("is_outlier") else "not an outlier"
    ax.set_title(f"{ticker} P/E vs peers — {verdict} (robust median/MAD)")
    ax.legend(loc="best", fontsize=7)
    return _finish(fig)


def render_vol_drawdown_png(history: list[dict], ticker: str) -> bytes:
    """Chart 3: rolling annualised volatility (top) and drawdown (bottom)."""
    dates = [row["date"] for row in history]
    closes = [row["close"] for row in history]
    vol = _rolling_vol(closes, 30)
    dd = _drawdown(closes)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True)
    ax1.plot(dates, [v * 100 if v is not None else None for v in vol],
             linewidth=1.1, color="#4c78a8")
    ax1.set_ylabel("30d vol (ann., %)")
    ax1.set_title(f"{ticker} — rolling volatility and drawdown")

    ax2.fill_between(range(len(dates)), [d * 100 for d in dd], 0,
                     color="#d1495b", alpha=0.35)
    ax2.plot(range(len(dates)), [d * 100 for d in dd], linewidth=0.8, color="#d1495b")
    ax2.set_ylabel("Drawdown (%)")
    ax2.annotate(f"max {min(dd)*100:.1f}%", (dd.index(min(dd)), min(dd) * 100),
                 textcoords="offset points", xytext=(5, -5), fontsize=7, color="#d1495b")
    _thin_xticks(ax2, dates)
    return _finish(fig)


def render_price_vs_index_png(price_hist: list[dict], index_hist: list[dict],
                              ticker: str, index_ticker: str) -> bytes:
    """Chart 1: stock vs home index, both rebased to 100 at the first common date."""
    dates, p, ix = _align_on_dates(price_hist, index_hist)
    if not dates:
        # No overlap — draw an explanatory placeholder rather than fail.
        fig, ax = plt.subplots(figsize=(9, 4.2))
        ax.text(0.5, 0.5, "no overlapping dates for index comparison",
                ha="center", va="center"); ax.set_axis_off()
        return _finish(fig)
    p0, ix0 = p[0], ix[0]
    p_n = [100 * v / p0 for v in p]
    ix_n = [100 * v / ix0 for v in ix]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(dates, p_n, linewidth=1.3, label=ticker, color="#4c78a8")
    ax.plot(dates, ix_n, linewidth=1.1, label=index_ticker, color="#888")
    ax.axhline(100, color="#ccc", linewidth=0.8)
    ax.set_ylabel("Rebased to 100")
    ax.set_title(f"{ticker} vs {index_ticker} (rebased to 100)")
    ax.legend(loc="best", fontsize=8)
    _thin_xticks(ax, dates)
    return _finish(fig)


# --- markdown -> html (lightweight, escape-first) -------------------------

def _markdown_to_html(text: str) -> str:
    import re
    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def inline(s):
        s = esc(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
        return s

    html, in_list = [], False
    for raw in (text or "").split("\n"):
        line = raw.rstrip()
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            if in_list: html.append("</ul>"); in_list = False
            level = len(m.group(1)) + 1  # ## -> h3
            html.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
        elif re.match(r"^[-*]\s+", line):
            if not in_list: html.append("<ul>"); in_list = True
            html.append(f"<li>{inline(line[2:])}</li>")
        elif line == "":
            if in_list: html.append("</ul>"); in_list = False
        else:
            if in_list: html.append("</ul>"); in_list = False
            html.append(f"<p>{inline(line)}</p>")
    if in_list: html.append("</ul>")
    return "\n".join(html)


# --- sidecar --------------------------------------------------------------

def write_sidecar(*, ticker: str, mode: str, note: str, analysis: dict,
                  price_history: dict, index_history: dict | None, out_dir: str) -> str:
    """Write model.json — the complete, self-contained record of one run."""
    os.makedirs(out_dir, exist_ok=True)
    sidecar = {
        "meta": {
            "ticker": ticker,
            "agent": "equity-research-v1",
            "mode": mode,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "note": note,
        "analysis": analysis,                 # copy of the loop's tool results
        "chart_data": {
            "price_history": price_history,
            "index_history": index_history,   # for the price-vs-index chart (may be None)
        },
    }
    path = os.path.join(out_dir, "model.json")
    with open(path, "w") as f:
        json.dump(sidecar, f, indent=2)
    return path


# --- report (rebuildable from the sidecar alone) --------------------------

def build_report(model_json_path: str, out_dir: str | None = None) -> str:
    """Read model.json ONLY, render all charts, write a self-contained report.html."""
    with open(model_json_path) as f:
        sidecar = json.load(f)

    if out_dir is None:
        out_dir = os.path.dirname(os.path.abspath(model_json_path))
    charts_dir = os.path.join(out_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)

    ticker = sidecar["meta"]["ticker"]
    analysis = sidecar.get("analysis", {})
    cd = sidecar["chart_data"]
    price_hist = cd["price_history"]["history"]
    hist_src = cd["price_history"].get("source", "?")
    index_block = cd.get("index_history")

    # Build the five charts. Each entry: (heading, png-bytes-or-None).
    sections = []

    # 1. Price vs home index (needs index history)
    if index_block and index_block.get("history"):
        png = render_price_vs_index_png(price_hist, index_block["history"], ticker,
                                        index_block.get("index_ticker", "index"))
        sections.append(("Price vs. home index (rebased to 100)", "price_vs_index", png))

    # 2. Price + moving averages
    sections.append(("Price & moving averages", "price_ma",
                     render_price_ma_png(price_hist, ticker)))

    # 3. Volatility & drawdown
    sections.append(("Volatility & drawdown", "vol_drawdown",
                     render_vol_drawdown_png(price_hist, ticker)))

    # 4. Peer-multiple scatter (from the sidecar's peer analysis)
    peer = analysis.get("peer_outlier_check")
    if peer and "peer_pes" in peer:
        sections.append(("Peer-multiple check", "peer_scatter",
                         render_peer_scatter_png(peer, ticker)))

    # 5. DCF football field (from the sidecar's DCF analysis)
    dcf = analysis.get("run_dcf")
    if dcf and "value_per_share" in dcf:
        sections.append(("DCF football field", "dcf_footballfield",
                         render_dcf_footballfield_png(dcf, ticker)))

    # Save standalone PNGs and build embedded <img> blocks.
    chart_html = []
    for heading, name, png in sections:
        with open(os.path.join(charts_dir, f"{name}.png"), "wb") as f:
            f.write(png)
        b64 = base64.b64encode(png).decode("ascii")
        chart_html.append(f'<h2>{heading}</h2>\n<img alt="{heading}" '
                          f'src="data:image/png;base64,{b64}">')

    note_html = _markdown_to_html(sidecar.get("note") or "")

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{ticker} — equity research</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a;line-height:1.5}}
 h1{{font-size:1.5rem}} h2{{font-size:1.1rem;margin-top:2rem;border-bottom:1px solid #eee;padding-bottom:.3rem}}
 h3{{font-size:1rem}} .meta{{color:#666;font-size:.85rem;margin-bottom:1rem}}
 img{{max-width:100%;border:1px solid #eee;border-radius:6px;margin:.5rem 0}}
 .src{{color:#888;font-size:.75rem;margin:.5rem 0 1.5rem}}
 .note{{background:#fafafa;border:1px solid #eee;border-radius:6px;padding:.5rem 1.2rem;margin-top:.5rem}}
 .note li{{margin:.2rem 0}}
</style></head><body>
<h1>{ticker} — Equity Research</h1>
<div class="meta">agent: {sidecar['meta']['agent']} &middot; mode: {sidecar['meta']['mode']} &middot; generated: {sidecar['meta']['generated_at']}</div>
{''.join(chart_html)}
<div class="src">chart data source: {hist_src} &middot; all figures from model.json (rebuildable sidecar)</div>
<h2>Analyst note</h2>
<div class="note">{note_html}</div>
</body></html>"""

    path = os.path.join(out_dir, "report.html")
    with open(path, "w") as f:
        f.write(html)
    return path
