"""Delivery-time integrity checks; bounded cache stores validation markers only."""
from collections import OrderedDict
import hashlib
from threading import RLock

from ..catalog import read_json
from .errors import NativeViewError
from .sources import adapter_for
from .validation import MAX_VIEW_BYTES, SCHEMA_BYTES, validate_view
from .values import digest

_VALIDATED = OrderedDict()
_LOCK = RLock()
_SCHEMA_HASH = hashlib.sha256(SCHEMA_BYTES).hexdigest()


def validate_registration(run):
    registration = getattr(run, 'native_view', None)
    native_artifacts = [a for a in run.artifacts if a.kind == 'report_view']
    if registration is None:
        if native_artifacts:
            raise NativeViewError()
        return
    by_id = {a.id: a for a in run.artifacts}
    view = by_id.get(registration.artifact_id)
    sources = registration.source_artifact_ids
    if (view is None or native_artifacts != [view] or not view.name.endswith('.json')
            or view.bytes > MAX_VIEW_BYTES or len(set(sources)) != 2 or view.id in sources
            or any(s not in by_id or by_id[s].kind != 'evidence' or not by_id[s].name.endswith('.json') for s in sources)):
        raise NativeViewError()
    adapter, version, _ = adapter_for(run)
    if (registration.view_schema_version != 1 or registration.adapter_id != adapter
            or registration.adapter_version != version):
        raise NativeViewError('unsupported_report_schema')


def load_view(catalog, run):
    validate_registration(run)
    reg = getattr(run, 'native_view', None)
    if reg is None:
        raise NativeViewError('native_view_unavailable')
    try:
        by_id = {a.id: a for a in run.artifacts}
        artifact = by_id[reg.artifact_id]
        sources = [by_id[s] for s in reg.source_artifact_ids]
        data = catalog.read(run.id, artifact)
        raw = [catalog.read(run.id, source) for source in sources]
        # All bytes were re-hashed by Catalog.read, including on a cache hit.
        key = digest([run.model_dump(), _SCHEMA_HASH, artifact.sha256, [s.sha256 for s in sources]])
        with _LOCK:
            valid = key in _VALIDATED
            if valid:
                _VALIDATED.move_to_end(key)
        view = read_json(data)
        if not valid:
            parsed = [read_json(value) for value in raw]
            validate_view(view, run, parsed[0], parsed[1], sources)
            with _LOCK:
                _VALIDATED[key] = True
                _VALIDATED.move_to_end(key)
                while len(_VALIDATED) > 64:
                    _VALIDATED.popitem(last=False)
        return view
    except NativeViewError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError, RecursionError) as exc:
        raise NativeViewError() from exc
