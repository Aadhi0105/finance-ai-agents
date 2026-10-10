"""Prepare a local blind labelling pack from retained bundles; never fetch news."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
from agent3.bundles import read_bundle
from keystone.maintenance import ROOT


def prepare(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False,mode=0o700)
    items=[];sources=[]
    for folder in ('asml-accepted','nvda-accepted'):
        matches=sorted((ROOT/'output/agent3-news-recovery'/folder).glob('*/bundle.json'))
        if len(matches)!=1:raise ValueError('Expected one retained source bundle; do not silently select or fetch another.')
        path=matches[0];record=read_bundle(path)['record']
        source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
        raw=record['input_items']
        if not isinstance(raw,list):raise ValueError('Unsupported retained inputs.')
        sources.append({'path':str(path.relative_to(ROOT)),'sha256':source_hash,'records':len(raw)})
        for index,value in enumerate(raw):
            identity=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            items.append({'id':f'R{len(items)+1:03d}','ticker':record['request']['ticker'],
                          'source_sha256':source_hash,'raw_index':index,'input_sha256':identity,
                          'as_of':record['result']['as_of'],'headline':value.get('headline'),
                          'published_at':value.get('published_at'),'source':value.get('source'),
                          'url':value.get('url'),'human_relevance':None,'human_duplicate_group':None,
                          'human_timestamp_valid':None,'reviewer_notes':''})
    pack={'schema_version':1,'status':'awaiting_human_labels','reviewer':None,'reviewed_at':None,
          'scope':'Retained retrievals only; cannot measure stories the provider never returned.',
          'instructions':'Label headline association with target issuer, duplicate story groups, and timestamp validity. Use true, false or the string uncertain for relevance and timestamp validity; use a shared group ID for duplicates and a unique group ID for a singleton. Do not consult application decisions first. No labels have been supplied by a human.',
          'sources':sources,'items':items}
    (destination/'labels.json').write_text(json.dumps(pack,indent=2,ensure_ascii=False)+'\n')
    rows=''.join('<tr>'+''.join('<td>'+html.escape(str(item.get(k) or ''))+'</td>' for k in ('id','ticker','published_at','headline','source'))+'</tr>' for item in items)
    content='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Keystone news review sample</title><style>body{font:16px system-ui;max-width:1200px;margin:32px auto;padding:0 20px;color:#18232c}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #ccd3da;text-align:left;vertical-align:top}th{background:#edf2f5}p{max-width:85ch}</style><h1>News review sample — labels pending</h1><p>These are retained historical headlines, not current news. This local sample is awaiting human review; it is not an accepted quality benchmark. Application decisions are intentionally omitted. Enter labels and reviewer details in the adjacent labels.json file.</p><p>For each target issuer, decide whether the headline concerns it, which records are duplicates, and whether the publication timestamp is usable. Mark uncertainty explicitly. Source-use permission and wider sample coverage remain separate release requirements.</p><table><thead><tr><th>ID</th><th>Target</th><th>Published</th><th>Headline</th><th>Source</th></tr></thead><tbody>'''+rows+'</tbody></table></html>'
    (destination/'review.html').write_text(content)
    return {'status':'awaiting_human_labels','items':len(items),'sources':sources,
            'labels_sha256':hashlib.sha256((destination/'labels.json').read_bytes()).hexdigest(),
            'application_predictions_shown':False,'production_quality_accepted':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);args=p.parse_args()
    os.umask(0o077)
    print(json.dumps(prepare(args.output),indent=2))
