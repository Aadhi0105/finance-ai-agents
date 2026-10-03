"""Recovery must distinguish unavailable providers from genuinely empty searches."""
from copy import deepcopy
from datetime import datetime
import json
import pytest
from agent3 import news_live, news_execution, run_news, bundles
from agent3.execution import Attempt
from agent3.news_funnel import run_funnel, render_news
from agent3.sentiment import LoughranMcDonaldScorer

ASOF = '2026-10-03T12:00:00+00:00'


@pytest.fixture(autouse=True)
def fixed_provider_clock(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(ASOF)
    monkeypatch.setattr(news_live, 'datetime', FixedDatetime)


def raw(**kw):
    return {'uuid':'one', 'title':'ASML reports growth', 'publisher':'Example',
            'providerPublishTime':1790985600, 'link':'https://example.org/article?utm_source=test',
            'relatedTickers':['ASML'], **kw}


@pytest.mark.parametrize('status', [404,429,500,None,True])
def test_non_success_status_never_becomes_empty(monkeypatch,status):
    monkeypatch.setattr(news_live,'_search_response',lambda q:({'news':[]},status))
    with pytest.raises(news_live.NewsProviderError,match='provider_http_error'):
        news_live.fetch_entity_news('NVDA')


@pytest.mark.parametrize('payload',[{}, {'message':'secret'}, {'news':None}, {'news':{}},
                                     {'news':[], 'error':'secret'}, {'news':[], 'finance':{'error':'secret'}}])
def test_missing_or_invalid_news_envelope_is_unavailable(monkeypatch,payload):
    monkeypatch.setattr(news_live,'_search_response',lambda q:(payload,200))
    with pytest.raises(news_live.NewsProviderError,match='invalid_provider_response'):
        news_live.fetch_entity_news('NVDA')


def test_transport_size_is_bounded():
    with pytest.raises(news_live.NewsProviderError,match='too_large'):
        news_live._check_transport(200,5_000_001)


def test_empty_success_is_explicit(monkeypatch):
    monkeypatch.setattr(news_live,'_search_response',lambda q:({'news':[]},200))
    result=news_live.fetch_entity_news('NVDA')
    assert result['transport']=={'status':'empty','http_status':200}
    assert result['raw_count']==0 and result['items']==[]


def test_explicit_query_retains_raw_evidence_without_fabricating_language_or_entity(monkeypatch):
    queries=[]
    def search(q):
        queries.append(q); return {'news':[raw()]},200
    monkeypatch.setattr(news_live,'_search_response',search)
    fetched=news_live.fetch_entity_news('ASML.AS',query='ASML')
    assert queries==['ASML'] and fetched['query']=='ASML'
    assert fetched['raw_items']==[raw()]
    item=fetched['items'][0]
    assert item['entities']==['ASML'] and item['query_ticker']=='ASML.AS'
    assert item['language'] is None and item['body']==''
    assert item['text_scope']=='headline_only'
    assert item['url']=='https://example.org/article'


def test_provider_exception_message_not_persisted(monkeypatch,tmp_path):
    def fail(q): raise RuntimeError('credential=secret')
    monkeypatch.setattr(news_live,'_search_response',fail)
    attempt=Attempt.create(tmp_path, {'ticker':'NVDA','scorer':'lm','data_mode':'live',
                                     'aliases':['NVIDIA'],'as_of':None,'max_age_days':7})
    assert news_execution.execute(attempt)==4
    evidence=attempt.record['provider_failure']
    assert evidence['reason']=='provider_request_failed' and evidence['error_type']=='RuntimeError'
    assert 'secret' not in attempt.path.read_text()
    bundle=bundles.read_bundle(bundles.seal(attempt))
    assert bundle['record']['provider_failure']==evidence
    assert bundles.replay(bundle)['verification']=='not_rebuildable'


def test_populated_worker_replays_and_preserves_headline_hold(monkeypatch,tmp_path):
    monkeypatch.setattr(news_live,'_search_response',lambda q:({'news':[raw()]},200))
    attempt=Attempt.create(tmp_path, {'ticker':'ASML.AS','news_query':'ASML','scorer':'lm','data_mode':'live',
                                     'aliases':['ASML'],'as_of':ASOF,'max_age_days':7})
    assert news_execution.execute(attempt)==3
    result=attempt.record['result']
    assert result['funnel']['after_relevance']==1
    assert 'headline_only_evidence' in result['review_reasons']
    assert 'unsupported_or_unknown_language' in result['review_reasons']
    assert result['signals'][0]['level'] is None
    bundle=bundles.read_bundle(bundles.seal(attempt))
    replay=bundles.replay(bundle)
    assert replay['verification']=='matched'
    assert 'headline_only' in bundles.export_html(bundle,replay)


def test_search_tags_and_query_do_not_establish_relevance(monkeypatch):
    monkeypatch.setattr(news_live,'_search_response',lambda q:({'news':[raw(title='Chip sector overview')]},200))
    fetched=news_live.fetch_entity_news('ASML.AS',query='ASML')
    for item in fetched['items']:item['retrieved_at']=ASOF
    result=run_funnel(fetched['items'],{'ASML.AS'},LoughranMcDonaldScorer(),aliases={'ASML.AS':['ASML']},as_of=ASOF,data_mode='live')
    assert not result['scored_items']
    assert result['exclusions'][0]['reason']=='no_headline_entity_evidence'


@pytest.mark.parametrize('query',['',' '*3,'x'*201])
def test_invalid_cli_query_never_starts_worker(query,monkeypatch):
    monkeypatch.setattr(run_news,'run_bounded',lambda *a,**kw:pytest.fail('worker started'))
    assert run_news.main(['NVDA','--news-query',query])==2


def test_http_failure_bundle_preserves_status(monkeypatch,tmp_path):
    monkeypatch.setattr(news_live,'_search_response',lambda q:({'message':'secret'},404))
    attempt=Attempt.create(tmp_path, {'ticker':'NVDA','scorer':'lm','data_mode':'live',
                                     'aliases':['NVIDIA'],'as_of':None,'max_age_days':7})
    assert news_execution.execute(attempt)==4
    assert attempt.record['provider_failure']['http_status']==404
    assert attempt.record['reason']=='provider_http_error'
    assert 'result' not in attempt.record


def test_populated_acceptance_detects_missing_evidence_and_escapes_links(monkeypatch,tmp_path):
    from scripts.check_agent3_news_acceptance import verify
    monkeypatch.setattr(news_live,'_search_response',lambda q:({'news':[raw(title='ASML <script>alert(1)</script> growth')]},200))
    attempt=Attempt.create(tmp_path, {'ticker':'ASML.AS','news_query':'ASML','scorer':'lm','data_mode':'live',
                                     'aliases':['ASML'],'as_of':ASOF,'max_age_days':7})
    news_execution.execute(attempt)
    bundle=bundles.read_bundle(bundles.seal(attempt))
    result, html=verify(bundle)
    assert result['status']=='passed'
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'href="https://example.org/article"' in html
    changed=deepcopy(bundle);changed['record']['fetched']['raw_items']=[]
    with pytest.raises(ValueError,match='raw count mismatch'):verify(changed)


def test_genuinely_empty_worker_is_held_not_unavailable(monkeypatch,tmp_path):
    monkeypatch.setattr(news_live,'_search_response',lambda q:({'news':[]},200))
    attempt=Attempt.create(tmp_path, {'ticker':'NVDA','scorer':'lm','data_mode':'live',
                                     'aliases':['NVIDIA'],'as_of':ASOF,'max_age_days':7})
    assert news_execution.execute(attempt)==3
    assert attempt.record['fetched']['transport']['status']=='empty'
    assert attempt.record['result']['review_reasons']==['no_relevant_usable_news']


@pytest.mark.parametrize('tags', [['ASML','^GSPC'], ['^IXIC'], ['^hsi','ASML','ASML']])
def test_valid_index_metadata_does_not_discard_relevant_headline(tags,monkeypatch):
    monkeypatch.setattr(news_live,'_search_response',lambda q:({'news':[raw(relatedTickers=tags)]},200))
    items=news_live.fetch_entity_news('ASML.AS',query='ASML')['items']
    items[0]['retrieved_at']=ASOF
    result=run_funnel(items,{'ASML.AS'},LoughranMcDonaldScorer(),aliases={'ASML.AS':['ASML']},as_of=ASOF,data_mode='live')
    assert result['funnel']['ingested']==result['funnel']['after_relevance']==1
    assert result['scored_items'][0]['entities']==['ASML.AS']
    assert result['scored_items'][0]['provider_entities']==sorted(set(t.upper() for t in tags))


def test_malformed_tags_have_specific_exclusion_reason(monkeypatch):
    monkeypatch.setattr(news_live,'_search_response',lambda q:({'news':[raw(relatedTickers=['^bad<script>'])]},200))
    items=news_live.fetch_entity_news('ASML.AS',query='ASML')['items'];items[0]['retrieved_at']=ASOF
    result=run_funnel(items,{'ASML.AS'},LoughranMcDonaldScorer(),aliases={'ASML.AS':['ASML']},as_of=ASOF,data_mode='live')
    assert result['exclusions'][0]['reason']=='invalid_entity_tags'
