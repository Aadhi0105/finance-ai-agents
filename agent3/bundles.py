"""Versioned, integrity-checked evidence bundles and offline calculation replay.

Hashes detect accidental changes, not malicious authorship. Files are write-once
through this API; filesystem owners can still replace them. No network or model
is used for replay. Track B reuses saved scores, never invokes model weights.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'completed', 'held', 'refused', 'unavailable', 'failed'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def provenance():
    files = sorted(p for folder in ('agent3', 'tools', 'mcp_server', 'agent')
                   for p in (ROOT / folder).rglob('*.py'))
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    versions = {}
    for name in ('numpy', 'scipy', 'duckdb', 'yfinance', 'anthropic', 'transformers', 'torch'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                text=True, timeout=3, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    return {'git_commit': commit, 'source_sha256': sources,
            'python': platform.python_version(), 'packages': versions}


def write_once(path, value):
    """Publish a complete file atomically, never replace a conflicting existing file."""
    path = Path(path)
    encoded = (canonical(value) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.bundle-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(name, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except FileExistsError:
            if path.read_bytes() != encoded:
                raise ValueError('immutable artifact conflict')
    finally:
        os.unlink(name)
    return path


def retained_inputs(record):
    request = {k: v for k, v in record.get('request', {}).items() if k not in ('db', 'fixture')}
    keys = ('assembled_inputs', 'n_event_types_tested', 'provider_snapshots', 'pinned_peer_set',
            'retry_peer_set', 'peer_proposal_audit', 'input_items', 'as_of', 'fetched')
    inputs = {'request': request, **{k: record[k] for k in keys if k in record}}
    if 'input_items' in record and 'result' in record:
        # Full scored records bind each saved model response to its exact input cluster.
        inputs['saved_scores'] = record['result'].get('scored_items', [])
    return inputs


def seal(attempt):
    from agent3.execution import _redact
    record = _redact(copy.deepcopy(attempt.record))
    if record.get('status') not in TERMINAL:
        raise ValueError('only terminal attempts can be sealed')
    inputs = retained_inputs(record)
    bundle = {'schema_version': 1, 'kind': 'agent3.run_bundle', 'attempt_id': record['run_id'],
              'content_fingerprint': digest(inputs), 'inputs': inputs, 'record': record,
              'provenance': record.get('provenance'),
              'replay_scope': 'normalized windows and saved news scores; no fresh providers or model inference'}
    bundle['bundle_sha256'] = digest(bundle)
    return write_once(attempt.path.with_name('bundle.json'), bundle)


def read_bundle(path):
    from agent3.execution import read_record
    b = read_record(path, max_bytes=100_000_000)
    if (not isinstance(b, dict) or type(b.get('schema_version')) is not int or b['schema_version'] != 1
            or b.get('kind') != 'agent3.run_bundle'):
        raise ValueError('unsupported bundle; legacy run.json cannot provide historical replay')
    payload = {k: v for k, v in b.items() if k != 'bundle_sha256'}
    if b.get('bundle_sha256') != digest(payload):
        raise ValueError('bundle integrity mismatch')
    r = b.get('record', {})
    if r.get('status') not in TERMINAL or b.get('attempt_id') != r.get('run_id'):
        raise ValueError('invalid terminal attempt')
    if b.get('inputs') != retained_inputs(r) or b.get('content_fingerprint') != digest(b['inputs']):
        raise ValueError('input fingerprint mismatch')
    if b.get('provenance') != r.get('provenance'):
        raise ValueError('provenance mismatch')
    return b


def _replay_news(inputs):
    from agent3.news_funnel import ingest, relevance_filter, dedup_cluster, score_items, finalize_news
    from agent3.news_contracts import asof
    request, raw = inputs['request'], inputs['input_items']
    cutoff = asof(inputs['as_of']).isoformat()
    excluded = []
    ingested = ingest(raw, as_of=cutoff, max_age_days=request['max_age_days'], exclusions=excluded)
    aliases = {request['ticker']: request['aliases']}
    relevant = relevance_filter(ingested, {request['ticker']}, aliases=aliases, exclusions=excluded)
    clusters = dedup_cluster(relevant)
    saved = inputs['saved_scores']
    if len(saved) != len(clusters):
        raise ValueError('saved score coverage mismatch')
    scored = []
    for cluster, original in zip(clusters, saved):
        # Verify every pre-scoring field, including member text/provenance and relevance flags.
        if any(original.get(k) != v for k, v in cluster.items() if k != 'review_reasons'):
            raise ValueError('saved score/input mismatch')
        evidence = original['score_evidence']
        class FrozenScore:
            name = original['scorer']
            def score(self, item):
                if 'error_type' in evidence:
                    name = evidence['error_type']
                    if not isinstance(name, str) or not name.isidentifier() or len(name) > 100:
                        raise ValueError('invalid saved failure type')
                    raise type(name, (Exception,), {})()
                return copy.deepcopy(evidence)
        rebuilt = score_items([cluster], FrozenScore())[0]
        if rebuilt != original:
            raise ValueError('saved score derivation mismatch')
        scored.append(rebuilt)
    return finalize_news(scored, ingested, excluded, cutoff=cutoff, aliases=aliases,
                         max_age_days=request['max_age_days'], data_mode=request['data_mode'],
                         counts={'raw': len(raw), 'after_relevance': len(relevant), 'after_dedup': len(clusters)})


def replay(bundle):
    """Recompute deterministic stages, compare with retained output; never promote failure."""
    from agent3.orchestrator import analyze_assembled
    from tools.event_study import run_event_study
    from agent3.execution import hold_terminal_result
    inputs, record = bundle['inputs'], bundle['record']
    answer = {'schema_version': 1, 'kind': 'agent3.replay', 'attempt_id': bundle['attempt_id'],
              'bundle_sha256': bundle['bundle_sha256'], 'content_fingerprint': bundle['content_fingerprint'],
              'original_status': record['status'], 'verification': 'not_rebuildable',
              'scope': bundle['replay_scope']}
    current = provenance()
    old = bundle.get('provenance') or {}
    answer['same_source_and_runtime'] = all(current.get(k) == old.get(k) for k in ('source_sha256', 'python', 'packages'))
    try:
        if 'assembled_inputs' in inputs:
            result = analyze_assembled(inputs['request']['event_type'], inputs['assembled_inputs'],
                                       n_event_types_tested=inputs.get('n_event_types_tested', 1),
                                       calculator=run_event_study)
            if inputs.get('retry_peer_set'):
                result['pinned_peer_set'] = inputs['retry_peer_set']
        elif 'saved_scores' in inputs:
            result = _replay_news(inputs)
        else:
            answer['reason'] = 'attempt ended before complete replay inputs were retained'
            return answer
        hold_terminal_result(result, record['status'])
        match = result == record.get('result')
        answer.update(verification='matched' if match else 'mismatch')
        if match:
            answer['result'] = result
        else:
            answer['reason'] = 'recomputed output differs from retained output; publication blocked'
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        answer.update(verification='mismatch', reason='retained inputs cannot reproduce output; publication blocked')
    return answer


def export_html(bundle, rebuilt):
    """A real export contains only verified fields; no interpolated event paths."""
    from html import escape
    from agent3.orchestrator import render_brief
    from agent3.news_funnel import render_news
    if rebuilt['verification'] == 'mismatch':
        raise ValueError('cannot export a mismatched replay')
    status = bundle['record']['status']
    result = rebuilt.get('result')
    if result is None:
        report = f"{status.upper()}: {bundle['record'].get('reason', 'incomplete evidence')}\nNo analytical output is verified."
    else:
        report = render_news(result) if 'signals' in result else render_brief(result)
    evidence_html = ''
    if result is not None and 'scored_items' in result:
        from agent3.news_contracts import canonical_url
        rows = []
        for item in result['scored_items']:
            title = escape(item['headline'])
            url = canonical_url(item.get('url'))
            link = ('<a href="' + escape(url, quote=True) + '" rel="noreferrer">' + title + '</a>') if url else title
            details = (f"{item.get('source', 'unknown')} | {item['published_at']} | "
                       f"text: {item.get('text_scope', 'unspecified')} | "
                       f"review: {', '.join(item.get('review_reasons', [])) or 'none'}")
            rows.append('<li>' + link + '<p>' + escape(details) + '</p></li>')
        evidence_html = ('<h2>Retained news evidence</h2><p>Links identify provider-returned sources; '
                         'article contents and availability are not verified by replay.</p><ul>'
                         + ''.join(rows) + '</ul>')
    labels = f"Attempt: {bundle['attempt_id']}\nStatus: {status}\nReplay: {rebuilt['verification']}\nIdentical source/runtime: {rebuilt['same_source_and_runtime']}\nInput fingerprint: {bundle['content_fingerprint']}\nBundle SHA-256: {bundle['bundle_sha256']}"
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Agent 3 saved run</title>'
            '<style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:20px;color:#173641}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f6;padding:20px}</style>'
            '<h1>Agent 3 — saved run</h1><p>Historical event diagnostics or current-news document tone. '
            'No return forecast. Hashes check file integrity, not source authenticity.</p><pre>'
            + escape(labels) + '</pre><pre>' + escape(report) + '</pre><p>'
            + escape(rebuilt['scope']) + '</p>' + evidence_html + '</html>')


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle')
    parser.add_argument('--output', help='write-once replay JSON')
    parser.add_argument('--html', help='write-once HTML report')
    parser.add_argument('--index-db', help='reconcile this verified bundle into the local index')
    args = parser.parse_args(argv)
    try:
        b = read_bundle(args.bundle)
        rebuilt = replay(b)
        if args.output:
            write_once(args.output, rebuilt)
        if args.html:
            # Reuse the atomic write-once primitive for text via a separate helper.
            write_text_once(args.html, export_html(b, rebuilt))
        if args.index_db:
            from agent3.catalyst_state import CatalystStore
            store = CatalystStore(args.index_db)
            try:
                store.index_bundle(args.bundle)
            finally:
                store.close()
        print(f"Replay: {rebuilt['verification']}; original status: {rebuilt['original_status']}")
        return 0 if rebuilt['verification'] == 'matched' else 3
    except (OSError, ValueError, KeyError, TypeError):
        print('REFUSED: invalid, conflicting or unsupported bundle/export; no publication allowed.')
        return 2
    except Exception as exc:
        print(f'FAILED: replay/export/index operation ({type(exc).__name__}); retained bundles are unchanged.')
        return 5


def write_text_once(path, content):
    # Same atomic publication contract as JSON, with native HTML bytes.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.export-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(name, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except FileExistsError:
            if path.read_text() != content:
                raise ValueError('immutable export conflict')
    finally:
        os.unlink(name)


if __name__ == '__main__':
    from keystone.maintenance import gate
    with gate():
        raise SystemExit(main())
