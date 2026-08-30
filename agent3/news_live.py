"""
Track B — LIVE news source (Agent 3). Fetches recent news for an entity and
shapes it into the funnel's input format (the same dicts fixtures/news.json holds).

HONEST SCOPE (decided with the user): free news is essentially CURRENT-only.
yfinance's news endpoint returns recent headlines with real publish timestamps —
good for the daily-sentiment BRIEF, which is Track B's actual job (BREADTH). It
does NOT provide point-in-time HISTORICAL news going back years; that would be
needed for historical sentiment->return analysis, which Track B never does (the
firewall keeps Track B out of Track-A rigor, and Track A owns event timing via
scheduled earnings dates). So current-only news is a fit, not a compromise — but
the code says so plainly rather than implying deep history it doesn't have.

Kept separate from the funnel so the network/fetch code is isolated from the
proven deterministic funnel logic. The fetch seam (_fetch_news) is mocked in
tests; the user runs it live.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _fetch_news(ticker: str) -> list[dict]:
    """Network seam: raw yfinance news for a ticker. Mocked in tests.
    yfinance returns items with keys like title, publisher, providerPublishTime
    (epoch seconds), link, type."""
    import yfinance as yf
    import warnings
    warnings.filterwarnings("ignore")
    raw = getattr(yf.Ticker(ticker), "news", None) or []
    return raw


def _epoch_to_iso(ts) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None


def shape_items(ticker: str, raw_news: list[dict]) -> list[dict]:
    """Convert raw yfinance news into funnel-shaped items. The published TIMESTAMP
    is sacred — items without a usable timestamp are dropped here (the funnel's
    ingest stage would drop them anyway; doing it at the source is cleaner). Pure,
    so this is unit-tested offline against yfinance-shaped fixtures."""
    out = []
    for i, n in enumerate(raw_news):
        # yfinance has shifted schemas across versions; support both the flat form
        # and the newer {'content': {...}} nesting.
        content = n.get("content", n)
        title = content.get("title") or n.get("title")
        if not title:
            continue
        ts = (n.get("providerPublishTime")
              or content.get("pubDate")
              or content.get("displayTime"))
        # epoch seconds -> iso; already-iso strings pass through
        published = _epoch_to_iso(ts) if isinstance(ts, (int, float)) else (ts or None)
        if not published:
            continue
        publisher = (content.get("provider", {}) or {}).get("displayName") \
            if isinstance(content.get("provider"), dict) else n.get("publisher", "")
        out.append({
            "id": n.get("uuid") or content.get("id") or f"{ticker}-{i}",
            "published_at": str(published),
            "entities": [ticker.upper()],
            "headline": title,
            "body": content.get("summary", "") or "",
            "source": publisher or "yfinance",
        })
    return out


def fetch_entity_news(ticker: str) -> dict:
    """Fetch + shape live news for one entity, ready for the funnel. Reports how
    many raw items were returned vs how many survived timestamp-shaping."""
    raw = _fetch_news(ticker)
    items = shape_items(ticker, raw)
    return {
        "ticker": ticker, "source": "yfinance.news",
        "raw_count": len(raw), "shaped_count": len(items),
        "items": items,
        "scope_note": ("current news only (free source); supports the daily "
                       "sentiment brief, not historical sentiment-return analysis"),
    }
