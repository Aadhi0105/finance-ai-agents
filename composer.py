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
    # Thin the x-axis labels so ~252 dates don't overlap.
    step = max(1, len(dates) // 8)
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)], rotation=45, fontsize=7, ha="right")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    return buf.getvalue()


# --- sidecar --------------------------------------------------------------

def write_sidecar(*, ticker: str, mode: str, note: str, analysis: dict,
                  price_history: dict, out_dir: str) -> str:
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
        "chart_data": {"price_history": price_history},
    }
    path = os.path.join(out_dir, "model.json")
    with open(path, "w") as f:
        json.dump(sidecar, f, indent=2)
    return path


# --- report (rebuildable from the sidecar alone) --------------------------

def build_report(model_json_path: str, out_dir: str | None = None) -> str:
    """Read model.json ONLY, render charts, write a self-contained report.html."""
    with open(model_json_path) as f:
        sidecar = json.load(f)

    if out_dir is None:
        out_dir = os.path.dirname(os.path.abspath(model_json_path))
    charts_dir = os.path.join(out_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)

    ticker = sidecar["meta"]["ticker"]
    history = sidecar["chart_data"]["price_history"]["history"]

    # Render the one chart, save standalone AND embed base64 (self-contained html).
    png = render_price_ma_png(history, ticker)
    with open(os.path.join(charts_dir, "price_ma.png"), "wb") as f:
        f.write(png)
    b64 = base64.b64encode(png).decode("ascii")

    note_html = (sidecar.get("note") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    hist_src = sidecar["chart_data"]["price_history"].get("source", "?")

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{ticker} — equity research</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
 h1{{font-size:1.4rem}} .meta{{color:#666;font-size:.85rem;margin-bottom:1.5rem}}
 img{{max-width:100%;border:1px solid #eee;border-radius:6px}}
 pre{{white-space:pre-wrap;background:#fafafa;border:1px solid #eee;border-radius:6px;padding:1rem;font-size:.9rem;line-height:1.4}}
 .src{{color:#888;font-size:.75rem;margin-top:.3rem}}
</style></head><body>
<h1>{ticker} — Equity Research</h1>
<div class="meta">agent: {sidecar['meta']['agent']} &middot; mode: {sidecar['meta']['mode']} &middot; generated: {sidecar['meta']['generated_at']}</div>
<h2>Price &amp; moving averages</h2>
<img alt="price and moving averages" src="data:image/png;base64,{b64}">
<div class="src">chart data source: {hist_src} &middot; rebuilt from model.json</div>
<h2>Analyst note</h2>
<pre>{note_html}</pre>
</body></html>"""

    path = os.path.join(out_dir, "report.html")
    with open(path, "w") as f:
        f.write(html)
    return path
