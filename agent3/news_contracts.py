"""Track B contracts: UTC current-news windows and bounded, auditable inputs."""
from datetime import datetime, timezone
import hashlib
import json
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp must be a timezone-aware ISO string')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('timestamp must have timezone')
    return dt.astimezone(timezone.utc)


def asof(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    return timestamp(value)


def canonical_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        return None
    try:
        u = urlparse(value)
        if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
            return None
        query = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
                 if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
        return urlunparse((u.scheme.lower(), u.netloc.lower(), u.path or '/', '', urlencode(sorted(query)), ''))
    except ValueError:
        return None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
