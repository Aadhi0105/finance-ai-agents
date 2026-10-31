"""Prepare labelled synthetic Agent 3 browser cases in a fresh private workspace.

Operator-only acceptance helper. No provider, model or mutation endpoint is added.
Original registered evidence is copied unchanged; controlled variants are new runs.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from keystone.workspace.catalog import Catalog, ManifestV2
from keystone.workspace.report_views.publish import register_views
from keystone.workspace.report_views.sources import check_source
from keystone.workspace.report_views.values import canonical, digest


def _seal(source):
    record = source['record']
    source['attempt_id'] = record['run_id'] = uuid4().hex
    retained = {'request': {k: v for k, v in record['request'].items() if k not in {'db', 'fixture'}},
                **{k: record[k] for k in ('assembled_inputs', 'n_event_types_tested', 'provider_snapshots', 'pinned_peer_set',
                   'retry_peer_set', 'peer_proposal_audit', 'input_items', 'as_of', 'fetched') if k in record}}
    if 'input_items' in record and 'result' in record:
        retained['saved_scores'] = record['result'].get('scored_items', [])
    source['inputs'] = retained
    source['content_fingerprint'] = digest(retained)
    source['replay_scope'] = 'Controlled synthetic UI acceptance fixture; no independent market evidence or replay claim.'
    source['bundle_sha256'] = digest({k: v for k, v in source.items() if k != 'bundle_sha256'})


def _news(source, kind, count=40):
    from agent3.news_funnel import run_funnel
    from agent3.sentiment import StubScorer
    if kind == 'failed':
        source['record'].pop('result', None)
        source['record'].update(status='unavailable', reason='controlled_qa_retrieval_unavailable')
        return
    items = copy.deepcopy(source['record']['input_items'])
    if kind == 'empty': items = []
    if kind == 'irrelevant':
        for item in items: item['headline'] = 'Unrelated demonstration company update'
    if kind == 'mixed':
        duplicate = copy.deepcopy(items[0]); duplicate.update(id='duplicate', source='Another synthetic bulletin')
        stale = copy.deepcopy(items[0]); stale.update(id='stale', published_at='2020-01-01T00:00:00Z')
        items += [duplicate, stale]
        items[1].update(language='de', text_scope='headline_only',headline='Example Rail fictional delay <img src=x>',body='Synthetic text <script>untrusted text</script>')
    if kind == 'unscored':
        for item in items:item['stub_score']=None
    if kind == 'many':
        seed = items[0]
        items = [{**copy.deepcopy(seed), 'id':'synthetic-'+str(i), 'headline':f'Example Rail fictional record {i+1:04d}',
                  'url':f'https://example.org/keystone-qa-{i+1}',
                  'body':f'Synthetic supplied text {i+1}; no verified company facts.',
                  'stub_score':[-.3,0,.3][i%3]} for i in range(count)]
    source['record']['input_items'] = items
    source['record']['result'] = run_funnel(items, {'DEMO'}, StubScorer(), aliases={'DEMO':['Example Rail']},
        as_of='2026-01-28T23:59:00Z', max_age_days=7, data_mode='fixture')
    if kind == 'unscored':
        source['record']['status']=source['record']['result']['status']='unavailable'


def _event(source, kind):
    result = source['record']['result']; study = result['study']
    if kind == 'repeated':
        study['per_event'][1].update(ticker=study['per_event'][0]['ticker'], issuer_id=study['per_event'][0].get('issuer_id') or study['per_event'][0]['ticker'], car=None)
        study.update(n_issuers=7, caar=None)
        study['inference_reasons'].append('repeated_issuer_dependence')
    if kind == 'ten':
        for i in range(2):
            row=copy.deepcopy(study['per_event'][i]);row.update(ticker='QA'+str(i),issuer_id='QA'+str(i));study['per_event'].append(row)
        study.update(n_events=10,n_issuers=10,caar=statistics.mean(r['car'] for r in study['per_event']),
                     inference_status='available',inference_reasons=[],p_value=.2,caar_significant=False)
        next(c for c in result['gate']['checks'] if c['check']=='inference').update(status='pass',detail='Controlled saved inference check; other restrictions remain')
        next(c for c in result['gate']['checks'] if c['check']=='thin_data').update(status='pass',detail='Controlled ten-issuer sample count met; other restrictions remain')
    if kind == 'many':
        study['per_event'] = [copy.deepcopy(row) for _ in range(250) for row in study['per_event']]
        study.update(n_events=2000,n_issuers=len({r.get('issuer_id') or r['ticker'] for r in study['per_event']}))
        next(c for c in result['gate']['checks'] if c['check']=='thin_data')['detail']='Controlled 2,000 repeated cases from eight issuers; no new independent evidence'
    if kind in {'ten','many'}:
        # Do not reuse spread values from a different sample as eligible diagnostics.
        result['scenario']['n_events'] = 0


def prepare(workspace, destination, large=False):
    from keystone.maintenance import gate
    workspace, destination = Path(workspace).absolute(), Path(destination).absolute()
    if destination.exists() or destination.is_symlink(): raise FileExistsError('Choose a fresh QA destination.')
    if workspace.resolve() in [destination.resolve(), *destination.resolve().parents]: raise ValueError('Destination must be outside the source workspace.')
    if any(p.is_symlink() for p in [destination,*destination.parents]): raise ValueError('Symlink destinations are not supported.')
    mask=os.umask(0o077)
    try:
        with gate(exclusive=True):
            catalog=Catalog(workspace);manifest=catalog.load();raw=manifest.model_dump();raw['schema_version']=2
            commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=False).stdout.strip()
            raw.update(prepared_at=datetime.now(timezone.utc).isoformat(),code_commit=commit or None,code_worktree_dirty=True,
                       preparer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
            destination.mkdir(parents=True,exist_ok=False)
            seeds={};source_hashes={'catalog.json':hashlib.sha256((workspace/'catalog.json').read_bytes()).hexdigest()}
            for run, output_run in zip(manifest.runs,raw['runs']):
                reg=getattr(run,'native_view',None);skip={reg.artifact_id,reg.source_artifact_ids[1]} if reg else set()
                output_run.pop('native_view',None);output_run['artifacts']=[a.model_dump() for a in run.artifacts if a.id not in skip]
                for artifact in run.artifacts:
                    data=catalog.read(run.id,artifact)
                    source_hashes[f'runs/{run.id}/{artifact.name}']=hashlib.sha256(data).hexdigest()
                    if artifact.id in skip:continue
                    path=destination/'runs'/run.id/artifact.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                    if run.workflow in {'events','news'} and artifact.name=='bundle.json':
                        source=json.loads(data);check_source(run,source);seeds[run.workflow]=(run,source)
            variants=[('events','repeated','events-repeated'),('events','ten','events-ten'),
                      ('news','empty','news-empty'),('news','irrelevant','news-irrelevant'),('news','failed','news-failed'),
                      ('news','mixed','news-mixed'),('news','unscored','news-unscored'),('news','many','news-pages')]
            if large:variants += [('events','many','events-large'),('news','many','news-large')]
            for workflow,kind,ident in variants:
                run,source=seeds[workflow];source=copy.deepcopy(source)
                if workflow=='news':_news(source,kind,600 if ident=='news-large' else 40)
                else:_event(source,kind)
                _seal(source)
                folder=destination/'runs'/ident;folder.mkdir(parents=True)
                html=('<!doctype html><html lang="en"><meta charset="utf-8"><title>Controlled synthetic QA fixture</title>'
                      '<h1>'+escape(ident)+'</h1><p>Controlled UI acceptance fixture. No market evidence or verified replay is claimed. '
                      'Inspect the registered native report and source bundle.</p></html>').encode()
                bundle=canonical(source)+b'\n';(folder/'report.html').write_bytes(html);(folder/'bundle.json').write_bytes(bundle)
                output_run=run.model_dump();output_run.pop('native_view',None)
                output_run.update(id=ident,title='Synthetic QA · '+ident,prepared_at=datetime.now(timezone.utc).isoformat(),
                    source_run_id=source['attempt_id'],execution_status=source['record']['status'],summary='Controlled synthetic UI acceptance case; no verified company facts.',
                    metrics=[],checks=['Controlled synthetic acceptance fixture'],report_id='file-0',
                    artifacts=[dict(id='file-'+str(i),name=name,label=label,kind=kind,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
                        for i,(name,label,kind,data) in enumerate([('report.html','QA fixture description','report',html),('bundle.json','Controlled synthetic evidence','evidence',bundle)])])
                raw['runs'].append(output_run)
            register_views(destination,ManifestV2.model_validate(raw))
            for relative,expected in source_hashes.items():
                assert hashlib.sha256((workspace/relative).read_bytes()).hexdigest()==expected,'Source changed during QA preparation'
            return {'workspace':str(destination),'classification':'synthetic','large_cases':large,'source_files_unchanged':len(source_hashes),
                    'cases':[r['id'] for r in raw['runs']],'production_release_approved':False}
    finally:os.umask(mask)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--destination',type=Path,required=True);p.add_argument('--large',action='store_true')
    args=p.parse_args();print(json.dumps(prepare(args.workspace,args.destination,args.large)))
