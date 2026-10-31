"""Saved news presentation: coverage, text identity and publication restrictions."""
import copy
import json
import shutil

import pytest

from test_native_reports import case, chart, client, hashes, metric, native, legacy, rewrite_artifact
from keystone.workspace.catalog import Catalog, RunV2
from keystone.workspace.report_views.projection import build_view
from keystone.workspace.report_views.publish import project_workspace
from keystone.workspace.report_views.series import prepare_series
from keystone.workspace.report_views.values import canonical, digest


def news_case(native, edit=lambda source: None):
    def update(source):
        edit(source)
        source['inputs']['saved_scores'] = copy.deepcopy(source['record']['result']['scored_items'])
        for key in ('input_items', 'fetched'):
            if key in source['record']:
                source['inputs'][key] = copy.deepcopy(source['record'][key])
        source['content_fingerprint'] = digest(source['inputs'])
        source['bundle_sha256'] = digest({k: v for k, v in source.items() if k != 'bundle_sha256'})
    return case(native, 'news', update)


def table(view, ident):
    return next(t for t in view['tables'] if t['id'] == ident)


def cell(view, table_id, row, column):
    return next(c['text'] for c in table(view, table_id)['rows'][row]['cells'] if c['column_id'] == column)


def funnel_input(source, items):
    from agent3.news_funnel import run_funnel
    from agent3.sentiment import StubScorer
    source['record']['input_items'] = items
    source['record']['result'] = run_funnel(items, {'DEMO'}, StubScorer(), aliases={'DEMO': ['Example Rail']},
        as_of='2026-01-28T23:59:00Z', max_age_days=7, data_mode='fixture')


def test_news_context_retains_cutoff_stories_members_and_exact_diagnostic_values(native):
    view, source, *_ = news_case(native)
    assert view['summary']['template_id'] == 'news-study-summary-v1'
    assert '2 headline clusters' in view['summary']['text']
    assert cell(view, 'news-basis', 0, 'value') == 'retained_records'
    assert cell(view, 'news-basis', 1, 'value') == source['record']['result']['as_of']
    assert len(table(view, 'news-cluster-members')['rows']) == 2
    assert 'scope unspecified' in cell(view, 'news-story-details', 0, 'scope')
    assert metric(view, 'published-tone-0')['value'] is None
    assert metric(view, 'diagnostic-tone-0')['value'] == '0.0'
    assert [p['y'] for p in chart(view, 'news-story-tone')['series'][0]['points']] == ['0.3', '-0.3']
    assert [p['y'] for p in chart(view, 'news-coverage')['series'][0]['points']] == ['2'] * 4
    assert view['state']['financial_approval'] is False


@pytest.mark.parametrize('kind, expected', [('empty', 'empty_saved_input'), ('irrelevant', 'no_relevant_records'), ('failed', 'retrieval_failed'), ('empty-response', 'recorded_empty_response')])
def test_news_distinguishes_empty_inputs_no_relevance_and_failed_retrieval(native, kind, expected):
    def edit(source):
        items = [] if kind != 'irrelevant' else copy.deepcopy(source['record']['input_items'])
        for item in items:
            item['headline'] = 'Unrelated issuer opens a facility'
        funnel_input(source, items)
        if kind == 'failed':
            source['record']['result']['status'] = 'unavailable'
        if kind == 'empty-response':
            source['record']['fetched'] = {'transport': {'status': 'empty', 'http_status': 200}}
    view, *_ = news_case(native, edit)
    assert cell(view, 'news-basis', 0, 'value') == expected
    assert not table(view, 'retained-headlines')['rows']
    assert metric(view, 'published-tone')['value'] is None
    if kind == 'failed':
        assert chart(view, 'news-coverage')['availability'] == 'withheld'
        assert metric(view, 'coverage-raw')['value'] is None
    else:
        assert metric(view, 'coverage-after-dedup')['value'] == '0'
        assert chart(view, 'news-coverage')['availability'] == 'available'


def test_news_clusters_retain_every_duplicate_member_and_original_exclusion(native):
    def edit(source):
        items = copy.deepcopy(source['record']['input_items'])
        duplicate = copy.deepcopy(items[0])
        duplicate.update(id='duplicate', source='Another synthetic bulletin')
        stale = copy.deepcopy(items[1])
        stale.update(id='stale', published_at='2025-01-28T14:00:00Z')
        funnel_input(source, items + [duplicate, stale])
    view, *_ = news_case(native, edit)
    assert metric(view, 'coverage-raw')['value'] == '4'
    assert metric(view, 'coverage-after-relevance')['value'] == '3'
    assert metric(view, 'coverage-after-dedup')['value'] == '2'
    assert len(table(view, 'news-cluster-members')['rows']) == 3
    assert cell(view, 'news-exclusions', 0, 'reason') == 'stale_publication'
    assert metric(view, 'published-tone-0')['value'] is None


@pytest.mark.parametrize('kind', ['out-of-range', 'missing', 'mismatch', 'unknown-scorer'])
def test_news_invalid_story_scores_are_missing_diagnostics_and_never_zero_fill(native, kind):
    def edit(source):
        item = source['record']['result']['scored_items'][0]
        if kind == 'out-of-range': item['sentiment'] = 2
        if kind == 'missing': item.pop('sentiment')
        if kind == 'mismatch': item['score_evidence']['score'] = -.8
        if kind == 'unknown-scorer': item['scorer'] = item['score_evidence']['scorer'] = 'unknown-scorer'
    view, *_ = news_case(native, edit)
    points = chart(view, 'news-story-tone')['series'][0]['points']
    assert points[0]['y'] is None and points[0]['reason_codes']
    assert points[1]['y'] == '-0.3' and len(points) == 2
    assert metric(view, 'diagnostic-tone-0')['value'] is None
    assert metric(view, 'published-tone-0')['value'] is None


def test_news_real_zero_story_score_and_daily_diagnostic_remain_diagnostic(native):
    def edit(source):
        for item in source['record']['result']['scored_items']:
            item['sentiment'] = item['score_evidence']['score'] = 0
    view, *_ = news_case(native, edit)
    assert [p['y'] for p in chart(view, 'news-story-tone')['series'][0]['points']] == ['0', '0']
    assert metric(view, 'diagnostic-tone-0')['value'] == '0.0'
    assert metric(view, 'published-tone-0')['value'] is None
    assert chart(view, 'news-story-tone')['visibility'] == 'diagnostic'


@pytest.mark.parametrize('value', [-2, 2, None])
def test_news_invalid_daily_diagnostic_never_becomes_a_published_level(native, value):
    def edit(source): source['record']['result']['signals'][0]['diagnostic_level'] = value
    view, *_ = news_case(native, edit)
    assert metric(view, 'diagnostic-tone-0')['value'] is None
    assert metric(view, 'published-tone-0')['value'] is None


def test_news_inconsistent_counts_withhold_coverage_and_aggregate_without_recalculation(native):
    def edit(source): source['record']['result']['funnel']['raw'] = 99
    view, *_ = news_case(native, edit)
    assert cell(view, 'news-basis', 0, 'value') == 'coverage_unknown'
    assert all(m['value'] is None for m in view['metrics'] if m['id'].startswith('coverage-'))
    assert chart(view, 'news-coverage')['series'] == []
    assert metric(view, 'diagnostic-tone-0')['value'] is None
    assert len(table(view, 'retained-headlines')['rows']) == 2
    assert view['findings'] == []


def test_news_changed_publication_label_cannot_publish_synthetic_tone(native):
    def edit(source):
        result = source['record']['result']
        result.update(status='completed', publication_state='DESCRIPTIVE', review_reasons=[])
        result['signals'][0].update(level=.8, publication_state='DESCRIPTIVE', review_reasons=[], flag_review=False)
    view, *_ = news_case(native, edit)
    assert metric(view, 'published-tone-0')['availability'] == 'withheld'
    assert metric(view, 'published-tone-0')['value'] is None
    assert view['state']['evidence_gate'] == 'held_for_review'


def test_news_text_language_truncation_and_unknown_reasons_remain_source_linked(native):
    def edit(source):
        item = source['record']['result']['scored_items'][0]
        item.update(language='de', text_scope='headline_only', review_reasons=['headline_only_evidence', 'unsupported_or_unknown_language', 'new_unknown_reason'])
        item['score_evidence'].update(review_reasons=['input_truncated'], truncated=True, token_count=600, token_limit=512)
        item['body'] = 'Retained text ' * 150
    view, source, *_ = news_case(native, edit)
    assert 'display excerpt; inspect original' in cell(view, 'news-story-details', 0, 'excerpt')
    assert len(source['record']['result']['scored_items'][0]['body']) > 1000
    assert cell(view, 'news-story-details', 0, 'language') == 'de'
    assert cell(view, 'news-story-details', 0, 'scope') == 'headline_only'
    codes = [c['text'] for r in table(view, 'news-review-reasons')['rows'] for c in r['cells'] if c['column_id'] == 'code']
    assert {'input_truncated', 'new_unknown_reason', 'unsupported_or_unknown_language'} <= set(codes)
    refs = {r for item in view['review_items'] for r in item['source_check_refs']}
    assert 'artifact:file-1#/record/result/scored_items/0/score_evidence/review_reasons/0' in refs


@pytest.mark.parametrize('version',['1.0.0','1.1.0'])
def test_news_prior_versions_and_fresh_projection_preserve_original_sources(native, tmp_path,version):
    root = tmp_path / 'old-news'
    shutil.copytree(native, root)
    run = next(r for r in Catalog(root).load().runs if r.workflow == 'news')
    primary = next(a for a in run.artifacts if a.id == run.native_view.source_artifact_ids[0])
    source = json.loads(Catalog(root).read(run.id, primary))
    old = run.model_copy(update={'native_view': run.native_view.model_copy(update={'adapter_version': version})})
    series = prepare_series(old, source, primary)
    rewrite_artifact(root, run.id, 'native-series', lambda value: (value.clear(), value.update(series)))
    manifest = json.loads((root / 'catalog.json').read_text())
    raw = next(r for r in manifest['runs'] if r['id'] == run.id)
    raw['native_view']['adapter_version'] = version
    (root / 'catalog.json').write_bytes(canonical(manifest))
    old = RunV2.model_validate(raw)
    artifacts = {a.id: a for a in old.artifacts}
    view = build_view(old, source, series, [primary, artifacts['native-series']])
    rewrite_artifact(root, run.id, 'native-view', lambda value: (value.clear(), value.update(view)))
    response = client(root).get('/api/runs/news-example/report-view')
    assert response.status_code == 200
    assert len(response.json()['charts']) == (0 if version=='1.0.0' else 2)
    before = hashes(root)
    upgraded = project_workspace(root, tmp_path / 'new-news')
    response = client(upgraded).get('/api/runs/news-example/report-view')
    assert response.status_code == 200 and len(response.json()['charts']) == 2
    assert hashes(root) == before


@pytest.mark.parametrize('status',['failed','unavailable','refused','completed','held'])
def test_news_missing_result_is_an_incomplete_attempt_not_a_successful_empty_feed(native,status):
    import hashlib
    from keystone.workspace.report_views.validation import validate_view
    catalog=Catalog(native);run=next(r for r in catalog.load().runs if r.workflow=='news')
    artifacts={a.id:a for a in run.artifacts};primary=artifacts[run.native_view.source_artifact_ids[0]]
    source=json.loads(catalog.read(run.id,primary));source['record'].pop('result')
    source['record'].update(status=status,reason='controlled_retrieval_failure')
    source['inputs'].pop('saved_scores');source['content_fingerprint']=digest(source['inputs'])
    source['bundle_sha256']=digest({k:v for k,v in source.items() if k!='bundle_sha256'})
    run=run.model_copy(update={'execution_status':status})
    primary=primary.model_copy(update={'sha256':hashlib.sha256(canonical(source)).hexdigest()})
    series=prepare_series(run,source,primary)
    secondary=artifacts[run.native_view.source_artifact_ids[1]].model_copy(update={'sha256':hashlib.sha256(canonical(series)).hexdigest()})
    if status in {'completed','held'}:
        with pytest.raises(ValueError):build_view(run,source,series,[primary,secondary])
        return
    view=build_view(run,source,series,[primary,secondary]);validate_view(view,run,source,series,[primary,secondary])
    assert view['summary']['template_id']=='news-retrieval-summary-v1'
    assert view['state']['execution']==status and view['state']['financial_approval'] is False
    assert all(m['value'] is None for m in view['metrics'])
    assert cell(view,'news-basis',0,'value')=='retrieval_failed'
    assert chart(view,'news-coverage')['availability']=='withheld'
