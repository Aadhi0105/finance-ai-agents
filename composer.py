"""
Output composer (component #6, spec §3.1) — the presentation layer.

Two responsibilities, deliberately split so the report is REBUILDABLE FROM THE
SIDECAR ALONE:

  write_sidecar(...)  -> writes model.json: every analysis number + the note +
                         the chart data (price history). Self-contained record
                         of one run.
  build_report(path)  -> reads model.json and NOTHING ELSE (no yfinance, no
                         model call), renders the chart(s), and writes a
                         self-contained approved or review HTML. Because it reads the
                         sidecar, it structurally proves every chart is driven
                         by a logged number.

Moving averages are computed here in plain Python — the "LLM never does the
math" rule extends to chart data too.
"""

from __future__ import annotations

import base64
import io
import json
import os
from datetime import datetime, timezone

from html import escape
from pathlib import Path
import tempfile
from filelock import FileLock


class _LazyPlot:
    """Saving an analysis must not depend on the chart library importing."""
    def __getattr__(self, name):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as pyplot
        return getattr(pyplot, name)


plt = _LazyPlot()


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
    import math
    out = [None]
    for i in range(1, len(closes)):
        prev, cur = closes[i - 1], closes[i]
        if prev in (None, 0) or cur is None:
            out.append(None); continue
        try:
            r = cur / prev - 1
            out.append(r if math.isfinite(r) else None)
        except (ZeroDivisionError, TypeError):
            out.append(None)
    return out


def _rolling_vol(closes: list[float], window: int = 30) -> list:
    """Annualised rolling volatility of daily returns. None until window fills."""
    import statistics, math
    rets = _daily_returns(closes)
    out = []
    for i in range(len(rets)):
        w = [r for r in rets[max(0, i - window + 1): i + 1]
             if r is not None and math.isfinite(r)]
        if len(w) >= window:
            try:
                out.append(statistics.pstdev(w) * math.sqrt(252))
            except statistics.StatisticsError:
                out.append(None)
        else:
            out.append(None)
    return out


def _drawdown(closes: list[float]) -> list:
    """Drawdown series vs running peak (0 at a new high, negative below)."""
    if not closes:
        return []
    out, peak = [], closes[0]
    for c in closes:
        peak = max(peak, c)
        out.append(c / peak - 1)
    return out


def _placeholder_png(ticker: str, title: str, msg: str = "insufficient data") -> bytes:
    """A labelled placeholder chart when a series is empty/too short, so report
    generation never crashes on missing history."""
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.text(0.5, 0.5, f"{title}\n({msg})", ha="center", va="center",
            fontsize=12, color="#888", transform=ax.transAxes)
    ax.set_title(f"{ticker} — {title}")
    ax.axis("off")
    return _finish(fig)


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
    if not history:
        return _placeholder_png(ticker, "price and moving averages", "no price history")
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


_CCY_SYMBOL = {"EUR": "\u20ac", "USD": "$", "GBP": "\u00a3", "JPY": "\u00a5",
               "CHF": "CHF ", "SEK": "kr ", "DKK": "kr ", "NOK": "kr "}


def _ccy(currency: str | None) -> str:
    return _CCY_SYMBOL.get((currency or "").upper(), (currency or "currency unknown") + " ")


def render_dcf_footballfield_png(dcf: dict, ticker: str, currency: str | None = None) -> bytes:
    """Chart 5: DCF bear/base/bull range vs current price (the valuation gap)."""
    sym = _ccy(currency)
    vps = dcf.get("value_per_share") or {}
    bear, base, bull = vps.get("bear"), vps.get("base"), vps.get("bull")
    weighted = dcf.get("scenario_weighted_per_share")
    price = dcf.get("current_price")

    # With an incomplete net-debt bridge there is no equity per-share to plot —
    # show an honest placeholder rather than a misleading EV-per-share chart.
    if bear is None or base is None or bull is None:
        return _placeholder_png(ticker, "DCF football field",
                                "enterprise value only — no equity per-share "
                                "(equity valuation unavailable)")

    fig, ax = plt.subplots(figsize=(9, 2.8))
    y = 0
    ax.plot([bear, bull], [y, y], linewidth=10, alpha=0.35, solid_capstyle="round",
            color="#4c78a8", zorder=1)
    for val, lab in [(bear, "Bear"), (base, "Base"), (bull, "Bull")]:
        ax.scatter([val], [y], s=40, color="#4c78a8", zorder=3)
        ax.annotate(f"{lab}\n{sym}{val:,.0f}", (val, y), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=7)
    if weighted is not None:
        ax.scatter([weighted], [y], marker="D", s=70, color="#2a2a2a", zorder=4,
                   label=f"Scenario-weighted {sym}{weighted:,.0f}")
    if price:
        ax.axvline(price, color="#d1495b", linestyle="--", linewidth=1.5,
                   label=f"Current price {sym}{price:,.0f}")
    ax.set_yticks([])
    ax.set_xlabel(f"Value per share ({sym.strip()})")
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
    verdict = "indeterminate" if peer.get("is_outlier") is None else "outlier" if peer["is_outlier"] else "not an outlier"
    ax.set_title(f"{ticker} P/E vs peers — {verdict} (robust median/MAD)")
    ax.legend(loc="best", fontsize=7)
    return _finish(fig)


def render_vol_drawdown_png(history: list[dict], ticker: str) -> bytes:
    """Chart 3: rolling annualised volatility (top) and drawdown (bottom)."""
    import math as _m
    if not history:
        return _placeholder_png(ticker, "volatility & drawdown", "no price history")
    clean = [r for r in history if r.get("close") is not None
             and isinstance(r["close"], (int, float)) and _m.isfinite(r["close"]) and r["close"] > 0]
    if len(clean) < 2:
        return _placeholder_png(ticker, "volatility & drawdown", "insufficient clean price data")
    dates = [r["date"] for r in clean]
    closes = [r["close"] for r in clean]
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

# --- markdown -> html (lightweight, escape-first) -------------------------

def _validation_banner(v: dict | None) -> str:
    if not v:
        return '<div class="banner review">REVIEW DRAFT — validation unavailable</div>'
    passed = v.get('verdict') == 'pass'
    label = 'Passed evidence gate' if passed else 'REVIEW DRAFT — not approved output'
    flags = ''.join('<li>' + escape(str(c.get('check'))) + ': ' + escape(str(c.get('detail'))) + '</li>'
                    for c in v.get('checks', []) if c.get('status') != 'pass')
    return f'<div class="banner {"pass" if passed else "review"}"><strong>{label}</strong> — confidence {escape(str(v.get("confidence")))}<ul>{flags}</ul></div>'


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

def _git_provenance():
    import subprocess
    try:
        root = Path(__file__).resolve().parent
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, stderr=subprocess.DEVNULL, timeout=3).decode().strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, stderr=subprocess.DEVNULL, timeout=3).strip())
        return {'git_commit': commit, 'git_dirty': dirty}
    except Exception:
        return {'git_commit': None, 'git_dirty': None}


def atomic_write(path, content):
    """Same-directory replace: readers see either the previous or complete file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', delete=False) as stream:
            temporary = stream.name
            stream.write(content if isinstance(content, bytes) else content.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def save_record(path, record):
    atomic_write(path, json.dumps(record, indent=2, allow_nan=False))


def write_sidecar(*, ticker, mode, note, analysis, price_history=None, index_history=None,
                  validation=None, out_dir, calls=None, model_id=None, currency=None,
                  execution=None, artifacts=None, note_template=None, run_id=None,
                  provenance=None):
    fin = (analysis.get('get_financials') or {}).get('financials', {}) or {}
    record = {
        'schema_version': 2,
        'meta': {'ticker': ticker, 'agent': 'equity-research-v1', 'mode': mode,
                 'run_id': run_id, 'generated_at': datetime.now(timezone.utc).isoformat(),
                 'model_id': model_id, **(provenance if provenance is not None else _git_provenance()),
                 'data_source': 'fixture' if mode == 'offline' else 'yfinance',
                 'statement_period': fin.get('period'), 'currency': currency},
        'execution': execution or {'status': 'unknown'},
        'artifacts': artifacts or {'status': 'pending', 'errors': []},
        'validation': validation, 'note': note,
        'note_template': note_template if note_template is not None else note,
        'analysis': analysis, 'call_history': calls or [],
        'chart_data': {'price_history': price_history or {'history': [], 'source': 'not_fetched'},
                       'index_history': index_history},
    }
    path = str(Path(out_dir) / 'model.json')
    save_record(path, record)
    return path


def _valid_history(history):
    """Refuse a damaged series rather than quietly bridging missing observations."""
    from datetime import date
    from tools.financial_contract import finite
    if not history:
        raise ValueError('price history unavailable')
    previous = None
    for row in history:
        current = date.fromisoformat(row['date'])
        if (previous is not None and current <= previous) or not finite(row.get('close')) or row['close'] <= 0:
            raise ValueError('invalid price history')
        previous = current
    return history


def build_report(model_json_path: str, out_dir: str | None = None) -> str:
    """Revalidate, render independently, and atomically publish a self-contained report.

    A lock serializes rebuilds. Prior reports are invalidated BEFORE reading or
    rendering, so a failure cannot leave an old approved report as current.
    Chart failures produce labelled omissions and a review report; analysis is
    already saved. Rebuilding never fetches external data or calls a model.
    """
    from validation.publication import assess_record
    from agent.state import utc_now
    out = Path(out_dir) if out_dir is not None else Path(model_json_path).parent
    out.mkdir(parents=True, exist_ok=True)
    with FileLock(str(out / '.report.lock'), timeout=0):
        for name in ('report.html', 'report_REVIEW.html'):
            (out / name).unlink(missing_ok=True)
        record = None
        try:
            with open(model_json_path) as stream:
                record = json.load(stream)
            meta = record['meta']
            ticker = meta['ticker']
            analysis = record.get('analysis', {})
            cd = record.get('chart_data') or {}
            history = (cd.get('price_history') or {}).get('history', [])
            index = cd.get('index_history') or {}
            artifacts = record.setdefault('artifacts', {})
            # Retry rendering errors; acquisition failures remain until a new
            # recorded data acquisition succeeds. Rebuild never fakes recovery.
            errors = [e for e in artifacts.get('errors', []) if e.get('stage', '').startswith('fetch_')]
            artifacts.update(status='building', errors=errors, charts=[], rebuilt_at=utc_now())
            record['validation'], record['note'] = assess_record(record)
            save_record(model_json_path, record)
            charts = out / 'charts'
            charts.mkdir(exist_ok=True)
            tasks = [
                ('Price vs. home index', 'price_vs_index', lambda: render_price_vs_index_png(_valid_history(history), _valid_history(index.get('history', [])), ticker, index.get('index_ticker', 'index'))),
                ('Price & moving averages', 'price_ma', lambda: render_price_ma_png(_valid_history(history), ticker)),
                ('Volatility & drawdown', 'vol_drawdown', lambda: render_vol_drawdown_png(_valid_history(history), ticker)),
                ('Peer multiples', 'peer_scatter', lambda: render_peer_scatter_png(analysis.get('peer_outlier_check') or {}, ticker)),
                ('DCF valuation', 'dcf_footballfield', lambda: render_dcf_footballfield_png(analysis.get('run_dcf') or {}, ticker, meta.get('currency'))),
            ]
            chart_html = []
            for heading, name, render in tasks:
                path = charts / (name + '.png')
                path.unlink(missing_ok=True)
                try:
                    png = render()
                    atomic_write(path, png)
                    chart_html.append(f'<h2>{escape(heading)}</h2><img alt="{escape(heading)}" src="data:image/png;base64,{base64.b64encode(png).decode("ascii")}">')
                    artifacts['charts'].append(name)
                except Exception as exc:
                    errors.append({'stage': 'chart_' + name, 'error_type': type(exc).__name__})
                    chart_html.append(f'<h2>{escape(heading)}</h2><p>Chart unavailable; see saved artifact diagnostics.</p>')
                    # Close incomplete figures without making failure recovery
                    # itself depend on matplotlib being installed.
                    try:
                        plt.close('all')
                    except Exception:
                        pass
            artifacts.update(errors=errors)
            record['validation'], record['note'] = assess_record(record)
            approved = record['validation']['verdict'] == 'pass'
            filename = 'report.html' if approved else 'report_REVIEW.html'
            artifacts['report'] = filename
            save_record(model_json_path, record)
            html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{escape(ticker)} — equity research</title>
<style>body{{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;line-height:1.5}}img{{max-width:100%}}.banner{{padding:1rem;border:1px solid #bbb}}.review{{background:#fff0e4}}.pass{{background:#eef7ee}}.meta{{color:#666}}</style>
</head><body><h1>{escape(ticker)} — Equity Research</h1>
<p class="meta">Mode: {escape(str(meta.get('mode')))} · Run: {escape(str(meta.get('run_id')))} · Execution: {escape(str(record.get('execution', {}).get('status', 'unknown')))}</p>
{_validation_banner(record['validation'])}
<h2>Analyst note</h2>{_markdown_to_html(record['note'])}
{''.join(chart_html)}
<p>Chart data and numerical evidence are preserved in model.json. Rebuilt {escape(artifacts['rebuilt_at'])}.</p>
</body></html>"""
            path = str(out / filename)
            atomic_write(path, html)
            artifacts['status'] = 'degraded' if errors else 'complete'
            save_record(model_json_path, record)
            return path
        except BaseException as exc:
            for name in ('report.html', 'report_REVIEW.html'):
                (out / name).unlink(missing_ok=True)
            if isinstance(record, dict):
                artifacts = record.setdefault('artifacts', {})
                artifacts.update(status='failed', report=None)
                artifacts.setdefault('errors', []).append({'stage': 'report', 'error_type': type(exc).__name__})
                try:
                    save_record(model_json_path, record)
                except Exception:
                    pass  # Prior atomic checkpoint remains intact.
            raise
