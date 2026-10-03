"""Current-news provider shaping. Query identity never establishes article relevance."""
from datetime import datetime, timezone
from agent3.news_contracts import canonical_url
from tools.event_contracts import finite, ticker as normalize


class NewsProviderError(RuntimeError):
    """Safe, bounded failure evidence; no provider body or credential text."""
    def __init__(self, code, *, http_status=None, error_type=None):
        super().__init__(code)
        self.evidence = {'status': 'unavailable', 'reason': code,
                         'http_status': http_status, 'error_type': error_type}


def _search_response(query):
    """Use the public Search API, checking transport before SDK empty defaults."""
    import yfinance as yf
    from curl_cffi.requests import Session
    from urllib.parse import urlparse

    class CheckedSession(Session):
        news_status = None
        def request(self, method, url, *args, **kwargs):
            response = super().request(method, url, *args, **kwargs)
            if urlparse(str(url)).path == '/v1/finance/search':
                self.news_status = response.status_code
                _check_transport(response.status_code, len(response.content))
            return response

    with CheckedSession(impersonate='chrome') as session:
        search = yf.Search(query, news_count=20, max_results=1, timeout=20, session=session)
        return search.response, session.news_status


def _check_transport(status, size):
    if type(status) is not int or not 200 <= status < 300:
        raise NewsProviderError('provider_http_error', http_status=status)
    if size > 5_000_000:
        raise NewsProviderError('provider_response_too_large', http_status=status)


def _fetch_news(query):
    try:
        response, status = _search_response(query)
        # A cache hit may skip the session. Never certify unknown HTTP status.
        _check_transport(status, 0)
        if (not isinstance(response, dict) or 'news' not in response
                or not isinstance(response['news'], list)
                or response.get('error') or response.get('finance', {}).get('error')):
            raise NewsProviderError('invalid_provider_response', http_status=status)
        raw = response['news']
        if len(raw) > 100:
            raise NewsProviderError('provider_record_limit', http_status=status)
        return raw, {'status': 'empty' if not raw else 'populated', 'http_status': status}
    except NewsProviderError:
        raise
    except Exception as exc:
        raise NewsProviderError('provider_request_failed', error_type=type(exc).__name__) from None


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


def fetch_entity_news(ticker, *, query=None):
    tk = normalize(ticker)
    query = tk if query is None else query
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
        raise ValueError('news query must be a nonempty string of at most 200 characters')
    query = query.strip()
    raw, transport = _fetch_news(query)
    retrieved = datetime.now(timezone.utc).isoformat()
    items = shape_items(tk, raw, retrieved_at=retrieved)
    for item in items:
        item['retrieval_query'] = query
        item['text_scope'] = 'headline_and_provider_summary' if item.get('body') else 'headline_only'
    return {'ticker': tk, 'source': 'yfinance.Search', 'query': query,
            'retrieved_at': retrieved, 'transport': transport, 'raw_items': raw,
            'raw_count': len(raw), 'shaped_count': len(items), 'items': items,
            'scope_note': 'Bounded current search results, not comprehensive coverage; query is not relevance evidence; no full-article or historical point-in-time guarantee'}
