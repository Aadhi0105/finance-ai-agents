"""Adversarial news contracts and whole-funnel publication regressions."""
from copy import deepcopy
from itertools import permutations
from types import SimpleNamespace
import json
import sys
import subprocess
import pytest

from agent3.news_funnel import ingest, relevance_filter, dedup_cluster, run_funnel, score_items, render_news
from agent3.news_live import shape_items
from agent3 import sentiment, lm_lexicon, news_execution, run_news
from agent3.execution import Attempt, ROOT, read_record

ASOF = '2026-10-02T12:00:00+00:00'


def item(**kw):
    return {'id': 'a', 'headline': 'ASML reports strong growth', 'body': '',
            'published_at': '2026-10-02T09:00:00Z', 'retrieved_at': ASOF,
            'entities': ['ASML.AS'], 'source': 'Publisher', 'url': 'https://example.org/a',
            'language': 'en', **kw}


class Scorer:
    name = 'controlled'
    def __init__(self, value=.3, confidence=None, flagged=False):
        self.value, self.confidence, self.flagged = value, confidence, flagged
        self.calls = 0
    def score(self, it):
        self.calls += 1
        return {'score': self.value, 'confidence': self.confidence, 'scorer': self.name,
                'flag_review': self.flagged, 'review_reasons': ['controlled_review'] if self.flagged else []}


def funnel(items, scorer=None, **kwargs):
    return run_funnel(items, {'ASML.AS'}, scorer or Scorer(), aliases={'ASML.AS': ['ASML']},
                      as_of=ASOF, data_mode='live', **kwargs)


@pytest.mark.parametrize('published', [None, '', 'not-a-date', '2026-10-02',
                                      '2026-10-02T08:00:00', '2099-01-01T00:00:00Z',
                                      '2026-01-01T00:00:00Z', True])
def test_bad_future_stale_or_naive_dates_are_excluded(published):
    result = funnel([item(published_at=published)])
    assert not result['signals'] and len(result['exclusions']) == 1
    assert result['status'] == 'held'


def test_day_is_utc_and_retrieval_is_separate():
    r = ingest([item(published_at='2026-10-02T00:30:00+02:00')], as_of=ASOF)[0]
    assert r['day'] == '2026-10-01'
    assert r['retrieved_at'] != r['published_at']


def test_future_retrieval_cannot_establish_past_archive():
    result = funnel([item(retrieved_at='2026-10-03T00:00:00Z')])
    assert result['exclusions'][0]['reason'] == 'inconsistent_retrieval_time'


def test_provider_query_is_not_entity_evidence():
    shaped = shape_items('SRAIL.SW', [{'uuid': 'x', 'title': 'Bananas are profitable in Canada',
                                     'providerPublishTime': 1790931600, 'link': 'https://example.org/x'}], retrieved_at=ASOF)
    assert shaped[0]['entities'] == [] and shaped[0]['query_ticker'] == 'SRAIL.SW'
    result = run_funnel(shaped, {'SRAIL.SW'}, Scorer(), aliases={'SRAIL.SW': ['Stadler Rail']}, as_of=ASOF)
    assert not result['signals']


def test_nested_provider_metadata_and_invalid_records_are_preserved():
    raw = [{'content': {'id': 'q', 'title': 'ASML update', 'pubDate': '2026-10-02T08:00:00Z',
                       'canonicalUrl': {'url': 'https://example.org/x?utm_source=y'},
                       'provider': {'displayName': 'Wire'}, 'relatedTickers': ['ASML.AS'], 'language': 'en'}},
           None, {'content': None}, {'title': 'ASML update', 'displayTime': ASOF}]
    shaped = shape_items('ASML.AS', raw, retrieved_at=ASOF)
    assert len(shaped) == 4
    assert shaped[0]['url'] == 'https://example.org/x'
    result = funnel(shaped)
    assert len(result['exclusions']) == 3 and result['status'] == 'held'


def test_body_only_passing_mention_and_provider_tags_do_not_pass():
    result = funnel([item(headline='Market outlook', body='ASML mentioned once')])
    assert not result['signals']
    assert result['exclusions'][0]['reason'] == 'no_headline_entity_evidence'


def test_alias_word_boundaries_and_cashtags():
    assert not funnel([item(headline='ASMLike products improve')])['signals']
    r = run_funnel([item(headline='$CAT reports growth', entities=['CAT'])], {'CAT'}, Scorer(), as_of=ASOF, data_mode='live')
    assert r['signals'][0]['entity'] == 'CAT'
    r = run_funnel([item(headline='The cat looks good', entities=['CAT'])], {'CAT'}, Scorer(), as_of=ASOF, data_mode='live')
    assert not r['signals']


def test_multi_entity_tone_is_not_published_as_entity_specific():
    r = funnel([item(entities=['ASML.AS','BESI.AS'])])
    assert r['signals'][0]['level'] is None
    assert 'multi_entity_document_tone' in r['review_reasons']
    assert 'document-level' in r['signals'][0]['tone_scope']


def test_duplicate_entities_cannot_double_count():
    r = funnel([item(entities=['ASML.AS','asml.as','ASML.AS'])])
    assert r['signals'][0]['count'] == 1


def test_negation_numbers_and_changed_body_are_not_merged():
    records = [item(id=str(i), url='https://example.org/'+str(i), headline=head, body=body)
               for i, (head, body) in enumerate([
                   ('ASML outlook is good', ''), ('ASML outlook is not good', ''),
                   ('ASML outlook is good', 'Correction: demand fell'),
                   ('ASML sales rise 10 percent', ''), ('ASML sales rise 20 percent', '')])]
    result = funnel(records)
    assert result['funnel']['after_dedup'] == 5


def test_clustering_is_order_independent_across_midnight_and_scores_once():
    records = [item(id='a', published_at='2026-10-01T23:59:00Z', source='Wire'),
               item(id='b', published_at='2026-10-02T00:01:00Z', source='Copy')]
    results = []
    for perm in permutations(records):
        scorer = Scorer()
        r = funnel(list(perm), scorer)
        assert scorer.calls == 1
        assert r['signals'][0]['count'] == 1 and r['signals'][0]['total_coverage'] == 2
        assert r['signals'][0]['day'] == '2026-10-01'
        assert len(r['scored_items'][0]['members']) == 2
        results.append(r)
    assert results[0] == results[1]


def test_same_url_changed_story_is_separate_and_held():
    r = funnel([item(), item(id='b', headline='ASML suffers a loss')])
    assert r['funnel']['after_dedup'] == 2
    assert 'article_identity_has_changed_text' in r['review_reasons']
    assert all(s['level'] is None for s in r['signals'])


@pytest.mark.parametrize('score,confidence', [(True,None), (float('nan'),None),
                                            (float('inf'),None), (2,None), (.3,100), (.3,True)])
def test_invalid_scorer_values_never_publish(score, confidence):
    r = funnel([item()], Scorer(score, confidence))
    assert r['scored_items'][0]['sentiment'] is None
    assert r['signals'][0]['level'] is None and 'scorer_failure' in r['review_reasons']
    json.dumps(r, allow_nan=False)


def test_late_disagreement_is_retained_in_final_signal_and_render():
    records = [item(id=str(i), url=f'https://example.org/{i}', headline=f'ASML update {i}') for i in range(7)]
    class LateScorer(Scorer):
        def score(self, it):
            r = super().score(it)
            if it['headline'].endswith('6'):
                r.update(flag_review=True, review_reasons=['late_disagreement'])
            return r
    scorer = LateScorer()
    r = funnel(records, scorer)
    text = render_news(r)
    assert scorer.calls == 7 and 'late_disagreement' in text
    assert r['signals'][0]['level'] is None
    assert len(r['scored_items']) == 7 and len(r['signals'][0]['cluster_ids']) == 7


def test_unavailable_scorer_does_not_drop_other_evidence():
    class Broken(Scorer):
        def score(self, it):
            if it['id'] == 'a':
                raise RuntimeError('sensitive provider diagnostic')
            return super().score(it)
    r = funnel([item(), item(id='b', headline='ASML news two', url='https://example.org/b')], Broken())
    assert len(r['scored_items']) == 2 and r['signals'][0]['scored_count'] == 1
    assert 'sensitive provider' not in json.dumps(r)
    assert r['signals'][0]['level'] is None


@pytest.mark.parametrize('language', [None, 'de', 'fr', 'unknown'])
def test_unknown_or_unsupported_language_requires_review(language):
    assert 'unsupported_or_unknown_language' in funnel([item(language=language)])['review_reasons']


def test_unknown_scorer_and_direct_divergence_cannot_use_stub(monkeypatch):
    with pytest.raises(ValueError): sentiment.get_scorer('finbrt')
    monkeypatch.delenv('AGENT_FINBERT_REVISION', raising=False)
    with pytest.raises(ValueError): sentiment.DivergenceScorer()
    assert sentiment.get_scorer().name == 'lm'


def test_lexicon_subset_identity_hits_and_no_evidence():
    scorer = sentiment.LoughranMcDonaldScorer()
    r = scorer.score(item())
    assert r['dictionary']['mode'] == 'curated_subset' and len(r['dictionary']['sha256']) == 64
    assert 'growth' in r['matched_positive'] and r['confidence'] is None and r['flag_review']
    r = scorer.score(item(headline='ASML quarterly update'))
    assert r['score'] is None and 'no_lexical_tone_evidence' in r['review_reasons']


def test_explicit_dictionary_failure_does_not_fall_back(monkeypatch, tmp_path):
    monkeypatch.setenv('LM_DICTIONARY_CSV', str(tmp_path/'missing.csv'))
    with pytest.raises(FileNotFoundError): sentiment.LoughranMcDonaldScorer()


def test_csv_removed_membership_and_frozen_dictionary_identity(monkeypatch, tmp_path):
    p=tmp_path/'selected.csv'; p.write_text('Word,Positive,Negative\nGAIN,2009,0\nLOSS,0,2009\nREMOVED,-2020,0\n')
    monkeypatch.setenv('LM_DICTIONARY_CSV',str(p))
    scorer=sentiment.LoughranMcDonaldScorer()
    r=scorer.score(item(headline='GAIN LOSS REMOVED'))
    assert r['pos_hits']==r['neg_hits']==1 and r['dictionary']['mode']=='configured_csv'
    p.write_text('broken')
    assert scorer.score(item(headline='GAIN'))['dictionary']==r['dictionary']
    with pytest.raises(ValueError):sentiment.LoughranMcDonaldScorer()


def finbert(monkeypatch, probabilities, length=10):
    monkeypatch.setattr(sentiment,'version',lambda k:'test-version')
    class Pipe:
        tokenizer=SimpleNamespace(model_max_length=512)
        model=SimpleNamespace(config=SimpleNamespace(max_position_embeddings=512))
        def __call__(self,*a,**kw):return [[{'label':k,'score':v} for k,v in probabilities.items()]]
    class Tokenizer:
        model_max_length=512
        def __call__(self,*a,**kw):return {'input_ids':[1]*length}
    pipe=Pipe();pipe.tokenizer=Tokenizer()
    scorer=sentiment.FinbertScorer(revision='a'*40);scorer._pipe=pipe
    return scorer


def test_finbert_ambiguous_probabilities_are_not_high_confidence(monkeypatch):
    r=finbert(monkeypatch,{'positive':.5,'negative':.5,'neutral':0}).score(item())
    assert r['score']==0 and r['confidence'] is None and r['class_margin']==0
    assert r['flag_review'] and r['revision']=='a'*40


@pytest.mark.parametrize('probs',[{'positive':.7,'negative':.7,'neutral':0},
                                 {'LABEL_0':1,'LABEL_1':0,'LABEL_2':0},
                                 {'positive':True,'negative':0,'neutral':0}])
def test_finbert_invalid_probability_vectors_refused(monkeypatch,probs):
    with pytest.raises(ValueError):finbert(monkeypatch,probs).score(item())


def test_finbert_truncation_preserved_to_final_signal(monkeypatch):
    r=funnel([item()],finbert(monkeypatch,{'positive':.8,'negative':.1,'neutral':.1},length=600))
    assert 'input_truncated' in r['review_reasons'] and r['signals'][0]['level'] is None
    assert r['scored_items'][0]['score_evidence']['token_count']==600


def test_cli_live_stub_is_refused_and_typo_does_not_run(monkeypatch,tmp_path):
    monkeypatch.setattr(run_news,'run_bounded',lambda *a,**k:pytest.fail('should not start'))
    assert run_news.main(['ASML.AS','--scorer','stub'])==2
    monkeypatch.setenv('AGENT_SENTIMENT_SCORER','finbrt')
    assert run_news.main(['ASML.AS'])==2


def test_cli_fixture_worker_saves_scored_evidence(tmp_path):
    env={'PATH':__import__('os').environ['PATH']}
    p=tmp_path/'fixture.json';p.write_text(json.dumps({'items':[item(stub_score=.7,stub_confidence=.9)]}))
    result=subprocess.run([sys.executable,'-m','agent3.run_news','ASML.AS','--alias','ASML','--scorer','stub',
                           '--demo','--fixture',str(p),'--as-of',ASOF,'--output-dir',str(tmp_path/'runs')],
                          cwd=ROOT,capture_output=True,text=True,timeout=30,env=env)
    assert result.returncode==3,result.stderr
    record=read_record(next((tmp_path/'runs').glob('*/run.json')))
    assert record['result']['scored_items'][0]['score_evidence']['score']==.7
    assert record['result']['signals'][0]['level'] is None and 'HELD' in result.stdout


def test_worker_provider_failure_is_saved_without_raw_exception(monkeypatch,tmp_path):
    request={'ticker':'ASML.AS','scorer':'lm','data_mode':'live','aliases':['ASML'],'as_of':None,'max_age_days':7}
    attempt=Attempt.create(tmp_path,request)
    monkeypatch.setattr(news_execution,'fetch_entity_news',lambda *a:(_ for _ in ()).throw(RuntimeError('secret')))
    assert news_execution.execute(attempt)==4
    assert attempt.record['stage']=='news_fetch'
    assert 'secret' not in attempt.path.read_text()


@pytest.mark.parametrize('mutation', [lambda r:r['signals'][0].update(level=float('nan')),
                                    lambda r:r['signals'][0].update(level=.99),
                                    lambda r:r['signals'][0].update(count=99),
                                    lambda r:r['scored_items'][0]['score_evidence'].update(flag_review=True)])
def test_saved_signal_cannot_publish_from_stale_descriptive_label(mutation):
    r=funnel([item()])
    assert 'DESCRIPTIVE' in render_news(r)
    mutation(r)
    text=render_news(r)
    assert 'HELD_FOR_REVIEW' in text and 'tone=HELD' in text
