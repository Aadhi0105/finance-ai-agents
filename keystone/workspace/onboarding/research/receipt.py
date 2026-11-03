"""Accepted input readiness, not a completed research run."""
from pathlib import Path
from pydantic import RootModel, model_validator
from ...catalog import read_confined, read_json
from ...job_files import write_new
from .. import contracts as c
from .contracts import semantic, readiness, producer, scope, validate_shape


class LocalReceipt(RootModel[dict]):
    @model_validator(mode='after')
    def shape(self):
        validate_shape('receipt',self.root)
        return self


def validate_import(package,context,folder):
    payload=semantic(package,context['entity'])
    expected=c.fingerprint(scope(package))
    pin=context['research_scope'] or dict(first_version_id=context['research_candidate_version_id'],scope_sha256=expected)
    if pin['scope_sha256']!=expected:raise ValueError('Listing scope changed')
    ready=readiness(payload)
    receipt=dict(schema_version=3,kind='keystone.financial-kit-validation',validator_version='financial-kit/1.0.0',producer=producer(),
        payload_sha256=c.fingerprint(payload),upstream_id=None,period_start=payload['periods'][-1]['period_start'],period_end=payload['periods'][-1]['period_end'],
        validation_status='validated',analytical_execution='not_started',eligible=True,listing_scope=pin,**ready)
    LocalReceipt.model_validate(receipt)
    write_new(Path(folder)/'validation.json',c.canonical(receipt))
