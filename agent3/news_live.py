"""Current-news provider shaping. Query identity never establishes article relevance."""
from datetime import datetime, timezone
from agent3.news_contracts import canonical_url
from tools.event_contracts import finite, ticker as normalize


def _fetch_news(ticker):
    import yfinance as yf
    raw = yf.Ticker(ticker).news
    if not isinstance(raw, list):
        raise ValueError('news provider returned an invalid collection')
    return raw


def _epoch_to_iso(value):
    if not finite(value):
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def shape_items(ticker, raw_news, *, retrieved_at=None):
    tk = normalize(ticker)
    retrieved = retrieved_at or datetime.now(timezone.utc).isoformat()
    if not isinstance(raw_news, list):
        raise ValueError('news must be a list')
    out = []
    for n in raw_news:
        if not isinstance(n, dict) or not isinstance(n.get('content', n), dict):
            out.append({'source_error': 'unsupported_provider_shape', 'retrieved_at': retrieved})
            continue
        content = n.get('content', n)
        ts = n.get('providerPublishTime')
        timestamp_source = 'providerPublishTime'
        if ts is None:
            ts = content.get('pubDate')
            timestamp_source = 'pubDate'
        # displayTime may be an update/render timestamp, not original publication.
        published = _epoch_to_iso(ts) if not isinstance(ts, str) else ts
        provider = content.get('provider')
        url = content.get('canonicalUrl')
        if isinstance(url, dict):
            url = url.get('url')
        url = url or content.get('link') or n.get('link')
        tags = content.get('relatedTickers', n.get('relatedTickers', []))
        out.append({'id': n.get('uuid') or content.get('id'), 'published_at': published,
                    'original_timestamp': ts if isinstance(ts, (str, int, float)) and not isinstance(ts, bool) and (isinstance(ts, str) or finite(ts)) else None,
                    'timestamp_source': timestamp_source, 'retrieved_at': retrieved,
                    'query_ticker': tk, 'entities': tags, 'url': canonical_url(url),
                    'headline': content.get('title') or n.get('title'), 'body': content.get('summary') or '',
                    'language': content.get('language') or n.get('language'),
                    'source': provider.get('displayName') if isinstance(provider, dict) else n.get('publisher'),
                    'data_mode': 'live'})
    return out


def fetch_entity_news(ticker):
    tk = normalize(ticker)
    raw = _fetch_news(tk)
    retrieved = datetime.now(timezone.utc).isoformat()
    items = shape_items(tk, raw, retrieved_at=retrieved)
    return {'ticker': tk, 'source': 'yfinance.news', 'retrieved_at': retrieved,
            'raw_count': len(raw), 'shaped_count': len(items), 'items': items,
            'scope_note': 'Current retrieved news; no historical point-in-time guarantee'}
