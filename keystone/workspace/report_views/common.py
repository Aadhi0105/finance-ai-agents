"""Deterministic presentation construction shared by the five source adapters.

Only saved fields, exact unit conversions, retained series and fixed templates
are used here. These functions perform no I/O and do not import agent engines.
"""
from decimal import Decimal

from .values import currency, decimal_text, digest, get, minor_to_major, resolve

MISSING = object()


class Builder:
    def __init__(self, run, source, series, artifacts, source_schema):
        self.run, self.source, self.series = run, source, series
        self._evidence_ids = set()
        self._point_count = 0
        self.primary_id, self.series_id = artifacts[0].id, artifacts[1].id
        self.raw = {self.primary_id: source, self.series_id: series}
        self.currency = currency(get(source, '/meta/currency'))
        if run.workflow == 'close':
            self.currency = 'EUR'  # Supported saved Agent 4 v1 contract is EUR only.
        self.view = dict(
            schema_version=1, kind='keystone.report-view',
            report_id='report-' + digest({'run': run.id, 'sources': [a.sha256 for a in artifacts],
                                         'adapter': series['adapter_id'], 'version': series['adapter_version']})[:24],
            agent=run.agent, workflow=run.workflow,
            identity=dict(title=run.title, entity=run.entity, ticker=get(source, '/meta/ticker'),
                          source_run_id=run.source_run_id, period_label=run.period,
                          period_end=None, prepared_at=run.prepared_at),
            state=dict(execution=run.execution_status, evidence_gate='held_for_review',
                       financial_approval=False, data_classification='synthetic',
                       integrity='matched', review_refs=[]),
            artifacts=[dict(id=a.id, name=a.name, sha256=a.sha256,
                            source_schema=source_schema if i == 0 else 'keystone.report-series/1')
                       for i, a in enumerate(artifacts)],
            sources=[dict(id='saved-source', label='Saved synthetic evidence', source_type='fixture',
                          observed_at=None, published_at=None, retrieved_at=None,
                          date_reason='Saved demonstration inputs; preparation is not an observation/publication date.',
                          url=None),
                     dict(id='derived-source', label='Retained Python chart series', source_type='derived',
                          observed_at=None, published_at=None, retrieved_at=None,
                          date_reason='Operator-prepared from the registered saved evidence; not new observations.',
                          url=None)],
            evidence=[], metrics=[], findings=[], sections=[], charts=[], tables=[], review_items=[],
            analyst_content=dict(keystone_scope='supported_facts_only' if run.workflow == 'research' else 'not_applicable',
                                 market_consensus=self.analyst_area(), external_research=self.analyst_area()),
            glossary=[])
        self.root_evidence = self.evidence('')
        self.review('data_basis', 'Synthetic demonstration',
                    'These illustrative inputs do not establish verified company facts or financial approval.',
                    'Inspect authorised source evidence before relying on the figures.',
                    ['policy:synthetic-local-review/v1'], [self.root_evidence], global_item=True)
        names = {'research': 'company research', 'monitoring': 'monitoring', 'events': 'historical event',
                 'news': 'news', 'close': 'financial close'}
        self.view['summary'] = dict(
            text=f"Saved synthetic {names[run.workflow]} evidence for {run.entity}. Financial review is required.",
            template_id='saved-summary-v1', metric_refs=[], evidence_refs=[self.root_evidence], review_refs=[])

    @staticmethod
    def analyst_area(availability='not_applicable', reasons=None, metrics=None, evidence=None):
        return dict(availability=availability, reason_codes=reasons or ['workflow_not_research'],
                    metric_refs=metrics or [], evidence_refs=evidence or [])

    def evidence(self, pointer, label='Saved source field', transform='identity', derived=False, method=None):
        aid = self.series_id if derived else self.primary_id
        resolve(self.raw[aid], pointer)  # Never create a reference to a missing field.
        ident = 'e-' + digest([aid, pointer, transform])[:22]
        if ident not in self._evidence_ids:
            if len(self._evidence_ids) >= 5000:
                raise ValueError('Report evidence exceeds bounds')
            self._evidence_ids.add(ident)
            self.view['evidence'].append(dict(id=ident, artifact_id=aid,
                source_id='derived-source' if derived else 'saved-source', pointer=pointer,
                label=str(label)[:240], transform=transform, method=method))
        return ident

    def maybe_evidence(self, pointer, label='Saved source field', **kwargs):
        raw = self.series if kwargs.get('derived') else self.source
        return self.evidence(pointer, label, **kwargs) if get(raw, pointer, MISSING) is not MISSING else self.root_evidence

    def metric(self, ident, label, pointer, unit, *, period=None, visibility='main',
               transform='identity', derived=False, restriction=None, currency_code=MISSING):
        if len(self.view['metrics']) >= 500:
            raise ValueError('Report metrics exceed bounds')
        raw = get(self.series if derived else self.source, pointer, MISSING)
        evidence = self.maybe_evidence(pointer, label, transform=transform, derived=derived,
                                       method='Exact integer minor units / 100.' if transform == 'minor_to_major' else None)
        value = None
        if transform == 'count':
            value = str(len(raw)) if isinstance(raw, (list, dict)) else None
        elif transform == 'minor_to_major':
            value = minor_to_major(raw)
        else:
            value = decimal_text(raw)
        if unit == 'count' and transform != 'count' and (type(raw) is not int or raw < 0):
            value = None
        ccy = (self.currency if currency_code is MISSING else currency(currency_code)) if unit in {'currency', 'currency_per_share'} else None
        available = value is not None and (unit not in {'currency', 'currency_per_share'} or ccy is not None)
        state, reasons = ('available', []) if available else ('unavailable', ['saved_value_unavailable'])
        if unit in {'currency', 'currency_per_share'} and ccy is None:
            state, reasons = 'unavailable', ['currency_unknown']
        if restriction:
            state, reasons = 'withheld', [restriction]
        self.view['metrics'].append(dict(id=ident, label=label, value=value if state == 'available' else None,
            unit=unit, currency=ccy, period_label=period or self.run.period, as_of=None,
            availability=state, visibility=visibility, reason_codes=reasons, evidence_refs=[evidence]))
        return ident

    def observation(self, metric_id, *, diagnostic=False):
        m = next(m for m in self.view['metrics'] if m['id'] == metric_id)
        if m['availability'] != 'available':
            return None
        value = Decimal(m['value'])
        if m['unit'] == 'fraction':
            value_text = f'{value * 100:,.2f}%'
        elif m['unit'] in {'currency', 'currency_per_share'}:
            value_text = f"{m['currency']} {value:,.2f}" + (' per share' if m['unit'] == 'currency_per_share' else '')
        elif m['unit'] == 'multiple':
            value_text = f'{value:f}×'
        else:
            value_text = f'{value:f}'
        ident = 'finding-' + metric_id
        self.view['findings'].append(dict(id=ident, kind='observed_fact',
            visibility='diagnostic' if diagnostic else m['visibility'],
            content=dict(text=f"Saved {m['label'].lower()}: {value_text} ({m['period_label']}).",
                         template_id='metric-observation-v1', metric_refs=[metric_id],
                         evidence_refs=m['evidence_refs'], review_refs=[])))
        return ident

    def section(self, ident, title, purpose, *, metrics=(), findings=(), charts=(), tables=(),
                availability='available', reasons=()):
        self.view['sections'].append(dict(id=ident, title=title, purpose=purpose,
            availability=availability, reason_codes=list(reasons), metric_refs=list(metrics),
            finding_refs=[x for x in findings if x], chart_refs=list(charts), table_refs=list(tables), review_refs=[]))

    def point(self, ident, x, label, pointer, *, derived=False, transform='identity', **extra):
        self._point_count += 1
        if self._point_count > 20_000:
            raise ValueError('Report points exceed bounds')
        source = self.series if derived else self.source
        raw = resolve(source, pointer)
        y = (minor_to_major(raw) if transform == 'minor_to_major'
             else decimal_text(raw) if transform == 'identity' else None)
        return dict(id=ident, x=str(x), label=str(label), y=y,
                    evidence_refs=[self.evidence(pointer, label, transform, derived)],
                    reason_codes=[] if y is not None else ['saved_point_unavailable_or_warmup'], **extra)

    def chart(self, ident, title, purpose, chart_type, unit, series=(), *, x_kind='category',
              x_label='Observation', visibility='main', restriction=None, currency_code=MISSING):
        if len(self.view['charts']) >= 20:
            raise ValueError('Report charts exceed bounds')
        ccy = (self.currency if currency_code is MISSING else currency(currency_code)) if unit in {'currency', 'currency_per_share'} else None
        present = any(p['y'] is not None for s in series for p in s['points'])
        reason = restriction or ('currency_unknown' if unit in {'currency', 'currency_per_share'} and ccy is None else
                                 'saved_series_unavailable' if not present else None)
        self.view['charts'].append(dict(id=ident, title=title, purpose=purpose, type=chart_type,
            availability='withheld' if restriction else 'unavailable' if reason else 'available',
            visibility=visibility, reason_codes=[reason] if reason else [],
            x_axis=dict(kind=x_kind, label=x_label), y_axis=dict(unit=unit, currency=ccy, label=unit),
            series=list(series) if reason is None else [], review_refs=[]))
        return ident

    def table(self, ident, title, columns, rows):
        self.view['tables'].append(dict(id=ident, title=title,
            columns=[dict(id=key, label=label) for key, label in columns], rows=rows, review_refs=[]))
        return ident

    def review(self, category, title, explanation, action, source_refs, evidence_refs,
               *, section_refs=None, global_item=False, impact='section_restriction'):
        if len(self.view['review_items']) >= 200:
            raise ValueError('Report review items exceed bounds')
        ident = 'review-' + digest([category, source_refs])[:20]
        self.view['review_items'].append(dict(id=ident, category=category,
            impact='publication_block' if global_item else impact, title=title,
            explanation=explanation, action=action, section_refs=list(section_refs or []),
            source_check_refs=source_refs, evidence_refs=evidence_refs))
        if global_item:
            self.view['review_items'][-1]['_global'] = True
        return ident

    def checks(self, pointer, category_for, section_for):
        """Group findings while preserving every original item, including repeats."""
        groups = {}
        for i, check in enumerate(get(self.source, pointer, []) or []):
            if not isinstance(check, dict):
                raise ValueError('Invalid saved check')
            if check.get('status') == 'pass':
                continue
            category = category_for(str(check.get('check', 'unknown')))
            groups.setdefault(category, []).append((i, check))
        for category, rows in groups.items():
            for offset in range(0, len(rows), 100):
                batch = rows[offset:offset + 100]
                pointers = [pointer + '/' + str(i) for i, _ in batch]
                self.review(category, category.replace('_', ' ').title() + ' requires review',
                    'Saved findings restrict this part of the report. Original details and every contributing check remain in the linked evidence.',
                    'Inspect all referenced source findings before relying on this section.',
                    [f'artifact:{self.primary_id}#{p}' for p in pointers],
                    [self.evidence(p, c.get('check', 'Saved check')) for p, (_, c) in zip(pointers, batch)],
                    section_refs=section_for(category),
                    impact='publication_block' if any(c.get('status') == 'fail' for _, c in batch) else 'section_restriction')

    def finish(self):
        section_ids = [s['id'] for s in self.view['sections']]
        for item in self.view['review_items']:
            if item.pop('_global', False):
                item['section_refs'] = section_ids[:]
            else:
                item['section_refs'] = [s for s in item['section_refs'] if s in section_ids]
        all_reviews = [r['id'] for r in self.view['review_items']]
        self.view['state']['review_refs'] = all_reviews
        self.view['summary']['review_refs'] = all_reviews
        for section in self.view['sections']:
            section['review_refs'] = [r['id'] for r in self.view['review_items'] if section['id'] in r['section_refs']]
            for key in ('chart_refs', 'table_refs'):
                collection = self.view['charts'] if key == 'chart_refs' else self.view['tables']
                for obj in collection:
                    if obj['id'] in section[key]:
                        obj['review_refs'] = sorted(set(obj['review_refs']) | set(section['review_refs']))
        return self.view


def text_cell(column, text):
    return dict(column_id=column, kind='text', text=str(text) if text is not None else 'Unavailable')


def metric_cell(column, ident):
    return dict(column_id=column, kind='metric_ref', metric_id=ident)
