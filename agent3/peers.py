"""Audited peer proposals. A pinned proposal is not a comparability approval."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from agent.models import AnthropicModel
from tools.event_contracts import ticker as normalize

_PROPOSE_SYSTEM = '''Propose 5-10 listed peers for a historical earnings study.
Return ONLY a JSON object with sector (string), peers (ticker string list),
rationale (string), and assessments (list of objects with ticker, rationale,
source_urls). Explain business-model comparability and material differences for
each peer. Cite public company/issuer URLs in source_urls. These are unverified
source leads, not verified evidence. Do not claim comparability has been reviewed.
Use exchange suffixes and exclude the target. Do not invent a peer if uncertain;
return an empty peers list to refuse. No tools or markdown.'''

_STUB_PEERS = {
    'ALO.PA': {'sector': 'rail rolling-stock & signalling',
               'peers': ['SIE.DE', 'KNRRY', 'WAB', 'ABBNY', 'SU.PA'],
               'rationale': 'Illustrative rail & industrial automation peers'},
    'ASML.AS': {'sector': 'semiconductor capital equipment',
                'peers': ['ASM.AS', 'BESI.AS', 'LRCX', 'AMAT', 'KLAC', 'TER'],
                'rationale': 'Illustrative front/back-end equipment makers'},
}


class PeerProposalError(ValueError):
    def __init__(self, code, audit):
        super().__init__(code)
        self.code, self.audit = code, audit


def _pin(ticker, proposal, source):
    tk = normalize(ticker)
    if not isinstance(proposal, dict) or not isinstance(proposal.get('peers'), list):
        raise ValueError('peer proposal must contain a list of ticker strings')
    if len(proposal['peers']) > 20:
        raise ValueError('at most 20 peers supported')
    peers = list(dict.fromkeys(normalize(p) for p in proposal['peers'] if normalize(p) != tk))
    for key in ('sector', 'rationale'):
        if key in proposal and (not isinstance(proposal[key], str) or len(proposal[key]) > 10000):
            raise ValueError(f'{key} must be bounded text')
    return {'ticker': tk, 'sector': proposal.get('sector', 'unspecified'),
            'peers': peers, 'rationale': proposal.get('rationale', ''),
            'proposed_by': source, 'n_peers': len(peers),
            'comparability_status': 'unverified'}


def _validate_model(proposal, ticker):
    pinned = _pin(ticker, proposal, 'model')
    if not pinned['peers']:
        raise ValueError('model returned no peers')
    for key in ('sector', 'rationale'):
        if not pinned[key].strip() or key not in proposal:
            raise ValueError(f'model requires {key}')
    assessments = proposal.get('assessments')
    if not isinstance(assessments, list) or len(assessments) != len(pinned['peers']):
        raise ValueError('one assessment per accepted peer is required')
    cleaned = []
    for item in assessments:
        if not isinstance(item, dict):
            raise ValueError('assessment must be an object')
        tk = normalize(item.get('ticker'))
        rationale = item.get('rationale')
        urls = item.get('source_urls')
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 10000:
            raise ValueError('assessment requires bounded rationale')
        if not isinstance(urls, list) or not 1 <= len(urls) <= 5:
            raise ValueError('assessment requires source leads')
        for url in urls:
            if not isinstance(url, str) or len(url) > 2048:
                raise ValueError('invalid source URL')
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError('invalid source URL')
        cleaned.append({'ticker': tk, 'rationale': rationale, 'source_urls': urls,
                        'evidence_status': 'unverified_model_claim'})
    if len({a['ticker'] for a in cleaned}) != len(cleaned) or {a['ticker'] for a in cleaned} != set(pinned['peers']):
        raise ValueError('assessment universe differs from accepted peers')
    pinned['assessments'] = cleaned
    return pinned


def propose_peers(ticker, override=None, live=False, checkpoint=None):
    tk = normalize(ticker)
    if override is not None:
        pinned = _pin(tk, {'sector': 'user-specified', 'peers': override,
                          'rationale': 'explicit peer override'}, 'override')
    elif live:
        pinned = _propose_via_model(tk, checkpoint=checkpoint)
    else:
        stub = _STUB_PEERS.get(tk, {'sector': 'unknown', 'peers': [],
                                  'rationale': 'no offline stub for this ticker'})
        pinned = _pin(tk, stub, 'stub')
    if checkpoint:
        checkpoint('peer_selection', {'pinned_peer_set': pinned})
    return pinned


def _propose_via_model(ticker, checkpoint=None):
    model = AnthropicModel()
    messages = [{'role': 'user', 'content': f'Ticker: {ticker}. Propose comparable listed peers.'}]
    audit = {'created_at': datetime.now(timezone.utc).isoformat(), 'model': model.model,
             'system': _PROPOSE_SYSTEM, 'messages': messages, 'status': 'requested'}
    def save():
        if checkpoint:
            checkpoint('peer_selection', {'peer_proposal_audit': audit})
    def fail(code):
        audit.update(status='refused', reason=code)
        save()
        raise PeerProposalError(code, audit)
    save()
    if not os.environ.get('ANTHROPIC_API_KEY', '').strip():
        fail('missing_credentials')
    try:
        # Keep the shared adapter; disable implicit paid retries for this bounded call.
        model._client = model._lazy_client().with_options(max_retries=0, timeout=45.0)
        resp = model.respond(system=_PROPOSE_SYSTEM, messages=messages, tools=[])
    except Exception as exc:
        audit['error_type'] = type(exc).__name__
        fail('model_unavailable')
    audit.update(stop_reason=resp.stop_reason, request_id=resp.request_id, usage=resp.usage,
                 response=[{'type': getattr(b, 'type', 'unknown'),
                            'text': getattr(b, 'text', '')} for b in resp.content])
    save()
    if resp.stop_reason != 'end_turn' or not resp.content or any(getattr(b, 'type', None) != 'text' for b in resp.content):
        fail('incomplete_or_refused_model_response')
    raw = ''.join(b.text for b in resp.content).strip()
    if len(raw) > 100000:
        fail('oversized_model_response')
    fenced = re.fullmatch(r'```(?:json)?\s*\n([\s\S]*?)\n```', raw)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        # Parse the entire response (or one exact fence), never extract from refusal prose.
        def unique(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError('duplicate JSON key')
                obj[key] = value
            return obj
        proposal = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        pinned = _validate_model(proposal, ticker)
    except (ValueError, TypeError, KeyError):
        fail('invalid_peer_schema')
    audit.update(status='accepted_unverified', accepted_peers=pinned['peers'])
    pinned['proposal_audit'] = audit
    save()
    return pinned
