"""Fail closed on unsourced model prose; no keyword list or LLM truth detector.

A model cannot certify a claim by adding a URL or calling it an opinion. Until
an issuer-source ingestion/review interface exists, only Python-rendered named
numerical evidence is eligible for the report. Original prose stays in the audit.
"""
import re
from validation.note_grounding import build_evidence_catalog

MARKER = re.compile(r'\[\[claim:([a-z][a-z0-9_]*)\]\]')
NOTICE = ('Financial evidence generated from saved inputs. Unsourced model interpretation '
          'and investment recommendations are withheld. Numerical validation does not '
          'establish provider accuracy or investment suitability.')


def control_note(template, analysis):
    catalog = build_evidence_catalog(analysis)
    rendered, withheld = [], []
    for line in (template or '').splitlines():
        if not line.strip():
            continue
        marker = MARKER.fullmatch(line.strip())
        if marker and marker.group(1) in catalog:
            rendered.append(catalog[marker.group(1)]['rendered'])
        else:
            withheld.append(line)
    return {'policy':'named_evidence_only', 'withheld_lines':withheld,
            'withheld_count':len(withheld), 'qualitative_verification':'not_performed',
            'published_note':NOTICE + '\n\n' + ('\n'.join(rendered) if rendered else
                'No supported numerical statements were selected.')}
