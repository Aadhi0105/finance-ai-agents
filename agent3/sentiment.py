"""Document-level tone scorers with explicit identity and non-calibrated diagnostics."""
from __future__ import annotations
import math
import os
import re
from importlib.metadata import version
from agent3 import lm_lexicon
from tools.event_contracts import finite


def _text_of(item):
    return f"{item.get('headline', '')} {item.get('body', '')}".strip()


def validate_score(result):
    if not isinstance(result, dict) or not isinstance(result.get('scorer'), str):
        raise ValueError('invalid scorer record')
    if not finite(result.get('score')) or not -1 <= result['score'] <= 1:
        raise ValueError('score must be finite in [-1,1]')
    confidence = result.get('confidence')
    if confidence is not None and (not finite(confidence) or not 0 <= confidence <= 1):
        raise ValueError('invalid confidence')
    if 'flag_review' in result and type(result['flag_review']) is not bool:
        raise ValueError('invalid review flag')
    return result


class StubScorer:
    name = 'stub'
    def score(self, item):
        # No pseudo-random fallback: demo scores require fixture evidence.
        result = {'score': item.get('stub_score'), 'confidence': item.get('stub_confidence'),
                  'scorer': self.name, 'flag_review': True, 'review_reasons': ['synthetic_demo_score']}
        return validate_score(result)


class LoughranMcDonaldScorer:
    name = 'lm'
    def __init__(self):
        self.dictionary = lm_lexicon.load_dictionary()
    def score(self, item):
        r = lm_lexicon.score_text(_text_of(item), self.dictionary)
        reasons = ['lexical_tone_not_contextual_sentiment']
        if r['dictionary']['mode'] == 'curated_subset':
            reasons.append('unverified_dictionary_subset')
        if not r['tone_words']:
            reasons.append('no_lexical_tone_evidence')
        return {**r, 'confidence': None, 'scorer': self.name,
                'flag_review': True, 'review_reasons': reasons}


class FinbertScorer:
    name = 'finbert'
    def __init__(self, model_name='ProsusAI/finbert', revision=None):
        self.model_name = model_name
        self.revision = revision or os.environ.get('AGENT_FINBERT_REVISION')
        if not isinstance(self.revision, str) or not re.fullmatch('[a-fA-F0-9]{40}', self.revision):
            raise ValueError('AGENT_FINBERT_REVISION must pin a 40-character model commit')
        self._pipe = None
    def _pipeline(self):
        if self._pipe is None:
            from transformers import pipeline
            self._pipe = pipeline('text-classification', model=self.model_name,
                                  tokenizer=self.model_name, revision=self.revision,
                                  top_k=None, truncation=True)
        return self._pipe
    def score(self, item):
        text = _text_of(item)
        if not text:
            raise ValueError('empty sentiment text')
        pipe = self._pipeline()
        token_count = len(pipe.tokenizer(text, truncation=False)['input_ids'])
        limit = min(pipe.tokenizer.model_max_length, pipe.model.config.max_position_embeddings)
        out = pipe(text, truncation=True, max_length=limit)[0]
        if len(out) != 3 or {d['label'].lower() for d in out} != {'positive','negative','neutral'}:
            raise ValueError('FinBERT must return three distinct named classes')
        probs = {d['label'].lower(): d['score'] for d in out}
        if not all(finite(p) and 0 <= p <= 1 for p in probs.values()) or not math.isclose(sum(probs.values()), 1, abs_tol=1e-5):
            raise ValueError('invalid FinBERT probability vector')
        ordered = sorted(probs.values(), reverse=True)
        reasons = []
        if token_count > limit:
            reasons.append('input_truncated')
        if ordered[0]-ordered[1] < .1:
            reasons.append('ambiguous_class_probabilities')
        return {'score': probs['positive']-probs['negative'], 'confidence': None,
                'scorer': self.name, 'probs': probs, 'top_class_probability': ordered[0],
                'class_margin': ordered[0]-ordered[1], 'token_count': token_count,
                'token_limit': limit, 'truncated': token_count > limit,
                'model': self.model_name, 'revision': self.revision, 'tokenizer_revision': self.revision,
                'dependencies': {k: version(k) for k in ('transformers', 'torch')},
                'flag_review': bool(reasons), 'review_reasons': reasons,
                'probability_note': 'Model class probabilities, not calibrated reliability or return probabilities'}


class DivergenceScorer:
    name = 'divergence'
    def __init__(self, primary=None, secondary=None, diverge_threshold=.5):
        self.primary = primary if primary is not None else FinbertScorer()
        self.secondary = secondary if secondary is not None else LoughranMcDonaldScorer()
        if not finite(diverge_threshold) or not 0 < diverge_threshold <= 1:
            raise ValueError('invalid divergence threshold')
        self.diverge_threshold = diverge_threshold
    def score(self, item):
        p = validate_score(self.primary.score(item))
        q = self.secondary.score(item)
        reasons = list(p.get('review_reasons', [])) + list(q.get('review_reasons', []))
        ps, qs = p['score'], q.get('score')
        divergence = None
        if qs is None:
            reasons.append('secondary_tone_unavailable')
        else:
            validate_score(q)
            divergence = abs(ps-qs)/2
            if (ps > .05 and qs < -.05) or (ps < -.05 and qs > .05) or (abs(ps) >= .6 and abs(qs) <= .1) or (abs(qs) >= .6 and abs(ps) <= .1) or divergence >= self.diverge_threshold:
                reasons.append('scorers_disagree')
        if p.get('flag_review') or q.get('flag_review'):
            reasons.append('component_requires_review')
        return {'score': ps, 'confidence': None, 'scorer': f'{self.primary.name}+{self.secondary.name}',
                'primary_score': ps, 'secondary_score': qs, 'primary': p, 'secondary': q,
                'divergence': divergence, 'flag_review': bool(reasons),
                'review_reasons': sorted(set(reasons)), 'reason': '; '.join(sorted(set(reasons)))}


def get_scorer(source=None):
    src = source if source is not None else os.environ.get('AGENT_SENTIMENT_SCORER', 'lm')
    factories = {'stub': StubScorer, 'lm': LoughranMcDonaldScorer, 'finbert': FinbertScorer, 'divergence': DivergenceScorer}
    if src not in factories:
        raise ValueError('scorer must be lm, finbert, divergence or explicit stub demo')
    return factories[src]()
