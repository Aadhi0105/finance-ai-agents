"""Explicit review decisions and transactional, audited effective-history recovery."""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json

from state.store import StateStore, _json_date
from tools.financial_contract import finite


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=_json_date,
                                     allow_nan=False).encode()).hexdigest()


def review_id(review):
    return digest(review)


def candidate_key(candidate):
    # Retrieval timestamps can change on every fetch. The proposed value and
    # definition, not the fetch time, determine whether a rejected candidate recurs.
    value = {key: candidate.get(key) for key in
             ('entity', 'metric', 'covenant_type', 'threshold', 'direction', 'value', 'data_ts')}
    value['definition_hash'] = candidate.get('evidence', {}).get('definition_hash')
    return digest(value)


def _effective_rows(store, item_id):
    rows = []
    for point in store.get_history_series(item_id):
        row = store.get_observation_evidence(item_id, point['data_ts'])
        if row is None:
            raise ValueError('legacy observation evidence unavailable; cannot restate this series')
        rows.append(row)
    return rows


def _recalculate(rows, revision_id):
    from scheduler.cycle import calculate_observation
    calculated = []
    for row in sorted(rows, key=lambda value: value['data_ts']):
        stamp = date.fromisoformat(row['data_ts'])
        history = [dict(cycle=r['cycle'], value=r['value'], data_ts=r['data_ts']) for r in calculated]
        result = calculate_observation(row, row['value'], stamp, row['cycle'],
                                       calculated[-1] if calculated else None, history)
        result['revision_id'] = revision_id
        calculated.append(result)
    return calculated


def decide(db_path, token, action, reviewer, reason, replacement_id=None):
    if action not in ('approve', 'reject'):
        raise ValueError('action must be approve or reject')
    if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(reason, str) or not reason.strip():
        raise ValueError('reviewer and reason are required')
    store = StateStore(db_path)
    try:
        previous = next((d for d in store.decisions() if d['review_id'] == token), None)
        if previous:
            if (previous['action'], previous['reviewer'], previous['reason'], previous.get('replacement_id')) != (
                    action, reviewer, reason, replacement_id):
                raise ValueError('review already decided with different parameters')
            return {**previous, 'replayed': True}
        review = next((r for r in store.reviews() if r['review_id'] == token), None)
        if review is None:
            raise ValueError('review ID is stale or unavailable; inspect current holds')
        item_id = review['item_id']
        candidate = deepcopy(review.get('candidate'))
        if not isinstance(candidate, dict):
            raise ValueError('candidate evidence unavailable')
        decision = {'review_id': token, 'item_id': item_id, 'action': action,
                    'reviewer': reviewer, 'reason': reason, 'replacement_id': replacement_id,
                    'decided_at': datetime.now(timezone.utc).isoformat(), 'review': review,
                    'candidate_key': candidate_key(candidate), 'replayed': False}
        rebuilt = []
        if action == 'reject':
            if replacement_id:
                raise ValueError('replacement ID is only valid for definition approval')
            decision['effect'] = 'retain effective history; suppress only this exact rejected candidate'
        else:
            if not finite(candidate.get('value')) or not finite(candidate.get('threshold')):
                raise ValueError('candidate numbers must be finite')
            stamp = date.fromisoformat(candidate['data_ts'])
            saved = store.get_run(review['cycle'])
            if saved is None or stamp > date.fromisoformat(saved['data_ts']):
                raise ValueError('candidate requires a saved review cycle and valid observation date')
            before = _effective_rows(store, item_id)
            if not before:
                raise ValueError('original series evidence unavailable')
            decision['before'] = before
            proposal = {**candidate, 'item_id': item_id, 'cycle': review['cycle']}
            if 'evidence' in proposal:
                proposal['_evidence'] = proposal.pop('evidence')
            if review['reason'] == 'definition_change_requires_review':
                if not isinstance(replacement_id, str) or not replacement_id.strip() or replacement_id == item_id:
                    raise ValueError('definition approval requires a new replacement item ID')
                if (store.get_current(replacement_id) or store.pending_review(replacement_id)
                        or store.is_retired(replacement_id) or store.get_history_series(replacement_id)):
                    raise ValueError('replacement ID already exists')
                proposal['item_id'] = replacement_id
                if '_evidence' in proposal:
                    from monitoring.live_data import definition
                    proposal['_evidence']['definition']['item_id'] = replacement_id
                    proposal['_evidence']['definition_hash'] = definition(proposal['_evidence']['definition'])
                rebuilt = _recalculate([proposal], token)
                decision['effect'] = 'new baseline series; original series retired and preserved; update watchlist item ID'
            elif review['reason'] == 'correction_requires_review':
                if replacement_id:
                    raise ValueError('replacement ID is only valid for definition approval')
                target = next((r for r in before if r['data_ts'] == candidate['data_ts']), None)
                if target:
                    proposal['cycle'] = target['cycle']
                rows = [r for r in before if r['data_ts'] != candidate['data_ts']] + [proposal]
                rebuilt = _recalculate(rows, token)
                decision['effect'] = 'effective history restated; original cycle reports unchanged'
            else:
                raise ValueError('unsupported review type')
            decision['after'] = rebuilt
        decision = json.loads(json.dumps(decision, default=_json_date, allow_nan=False))
        with store.transaction():
            # Save the entire before/after record in the same transaction as the new view.
            store.con.execute('INSERT INTO review_decisions VALUES (?, ?)',
                              [token, json.dumps(decision, allow_nan=False)])
            if action == 'approve':
                if replacement_id:
                    store.con.execute('INSERT INTO retired_series VALUES (?, ?)', [item_id, replacement_id])
                else:
                    store.con.execute('DELETE FROM observation_details WHERE item_id=?', [item_id])
                    store.con.execute('DELETE FROM history WHERE item_id=?', [item_id])
                for row in rebuilt:
                    store.write_history(row)
                store.upsert_current(rebuilt[-1])
            store.con.execute('DELETE FROM review_queue WHERE item_id=?', [item_id])
        return decision
    finally:
        store.close()


def retry_triage(db_path, cycle, *, live=False, audit_dir=None):
    """New audited attempt against the original saved cycle, never a provider refresh."""
    from monitoring.triage import HistorySnapshot, run_triage_record
    if type(cycle) is not int or cycle < 1:
        raise ValueError('cycle must be a positive integer')
    store = StateStore(db_path)
    try:
        result = store.get_run(cycle)
        if result is None:
            raise ValueError('saved cycle unavailable')
        snapshot = HistorySnapshot.from_cycle(store, result)
    finally:
        store.close()
    return run_triage_record(snapshot, result['surfaced'], live=live, cycle=cycle,
                             audit_dir=audit_dir, retry_context={'kind': 'explicit_cycle_retry',
                             'cycle_digest': digest(result), 'db_path': store.path})
