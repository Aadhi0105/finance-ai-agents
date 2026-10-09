"""Strict snapshot inventory contract, separate from financial/provider validation."""
from pathlib import Path, PurePosixPath
import re

ROLES = {'agent1_evidence', 'agent2_state', 'agent2_audits', 'agent3_state',
         'agent3_evidence', 'agent4_state', 'agent4_evidence', 'inputs', 'configuration', 'logs'}


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Invalid relative inventory path')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ('', '.', '..') for x in value.split('/')) or ':' in value:
        raise ValueError('Unsafe inventory path')
    return p


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {'schema_version', 'scope', 'sources', 'datasets'} or type(plan['schema_version']) is not int or plan['schema_version'] != 1:
        raise ValueError('Unsupported inventory schema')
    if not isinstance(plan['scope'], str) or not plan['scope'].strip():
        raise ValueError('Explicit inventory scope required')
    if not isinstance(plan['sources'], list) or not plan['sources']:
        raise ValueError('Sources required')
    seen = []; origins = []
    for item in plan['sources']:
        if not isinstance(item, dict) or set(item) != {'name', 'path', 'kind', 'role'}:
            raise ValueError('Invalid source fields')
        name = relative(item['name'])
        if name.parts[0] == 'restore-receipt.json':
            raise ValueError('Reserved restore receipt path')
        if any(name == old or name in old.parents or old in name.parents for old in seen):
            raise ValueError('Overlapping inventory names')
        seen.append(name)
        if item['role'] not in ROLES or item['kind'] not in {'file', 'tree', 'database'}:
            raise ValueError('Invalid source kind/role')
        if item['role'] in {'agent2_state','agent3_state','agent4_state'} and item['kind'] != 'database':
            raise ValueError('State must be an explicit database entry')
        if not isinstance(item['path'], str) or not Path(item['path']).is_absolute():
            raise ValueError('Source paths must be absolute')
        origin = Path(item['path']).resolve()
        if str(origin) != item['path']:
            raise ValueError('Use canonical resolved absolute source paths')
        if any(origin == old or origin in old.parents or old in origin.parents for old in origins):
            raise ValueError('Overlapping source paths')
        origins.append(origin)
    if not isinstance(plan['datasets'], list) or not plan['datasets']:
        raise ValueError('Declare data contracts, even for synthetic inputs')
    ids = set()
    for data in plan['datasets']:
        fields = {'id','source','classification','period','currency','units','permission','permission_evidence','freshness_policy','source_names'}
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError('Invalid dataset contract fields')
        if any(not isinstance(data[k], str) or not data[k].strip() for k in fields - {'source_names'}):
            raise ValueError('Contract metadata must be explicit; use unknown where necessary')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',data['id']) or data['id'] in ids:
            raise ValueError('Invalid/duplicate dataset ID')
        ids.add(data['id'])
        if data['classification'] not in {'synthetic','public_provider','issuer','confidential'} or data['permission'] not in {'synthetic_only','pending','reviewed'}:
            raise ValueError('Invalid data classification/permission')
        if data['permission'] == 'synthetic_only' and data['classification'] != 'synthetic':
            raise ValueError('Real inputs cannot use synthetic permission')
        if data['permission'] == 'reviewed' and data['permission_evidence'].lower() in {'unknown','pending','none'}:
            raise ValueError('Reviewed permission needs evidence reference')
        if not isinstance(data['source_names'], list) or not data['source_names'] or any(x not in [str(s) for s in seen] for x in data['source_names']):
            raise ValueError('Dataset references unknown source')
    if set(x for d in plan['datasets'] for x in d['source_names']) != set(map(str, seen)):
        raise ValueError('Every source must have a dataset contract')
    return plan


def release_holds(plan):
    """Metadata checks do not authenticate permissions or financial source truth."""
    holds = []
    for d in plan['datasets']:
        if d['permission'] == 'pending':
            holds.append(f"{d['id']}: source permission unresolved")
        for key in ('period','currency','units','freshness_policy'):
            if d[key].lower() in {'unknown','pending'}:
                holds.append(f"{d['id']}: {key} unresolved")
    return holds
