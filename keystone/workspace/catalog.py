"""Explicit, bounded inventory for generated synthetic reports; never scans output/."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_FILE_BYTES = 20_000_000
ID = r'^[a-z0-9][a-z0-9_-]{0,79}$'


class CatalogError(ValueError):
    """A registered workspace is unavailable or no longer matches its inventory."""


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class Metric(Record):
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(max_length=120)
    basis: str = Field(min_length=1, max_length=240)


class Artifact(Record):
    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=240)
    label: str = Field(min_length=1, max_length=120)
    kind: Literal['report', 'evidence', 'chart', 'input']
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    bytes: int = Field(ge=1, le=MAX_FILE_BYTES)

    @field_validator('name')
    @classmethod
    def safe_name(cls, value):
        safe_relative(value)
        if Path(value).suffix not in {'.html', '.json', '.png'}:
            raise ValueError('unsupported artifact type')
        return value


class Run(Record):
    id: str = Field(pattern=ID)
    agent: Literal['agent1', 'agent2', 'agent3', 'agent4']
    workflow: Literal['research', 'monitoring', 'events', 'news', 'close']
    title: str = Field(min_length=1, max_length=160)
    entity: str = Field(min_length=1, max_length=160)
    period: str = Field(min_length=1, max_length=120)
    prepared_at: str = Field(min_length=1, max_length=80)
    execution_status: Literal['completed', 'held', 'refused', 'unavailable', 'failed']
    review_status: Literal['review_required', 'not_financial_approval']
    summary: str = Field(min_length=1, max_length=1600)
    limitations: list[str] = Field(min_length=1, max_length=20)
    checks: list[str] = Field(max_length=20)
    metrics: list[Metric] = Field(max_length=12)
    artifacts: list[Artifact] = Field(min_length=1, max_length=40)
    report_id: str = Field(pattern=ID)
    source_run_id: str = Field(min_length=1, max_length=200)


class Manifest(Record):
    schema_version: Literal[1]
    kind: Literal['keystone.synthetic-workspace']
    classification: Literal['synthetic']
    prepared_at: str
    code_commit: str | None
    code_worktree_dirty: bool
    preparer_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    production_release_approved: Literal[False]
    runs: list[Run] = Field(max_length=100)


class ArtifactV2(Artifact):
    kind: Literal['report', 'evidence', 'chart', 'input', 'report_view']


class NativeViewRegistration(Record):
    artifact_id: str = Field(pattern=ID)
    view_schema_version: int = Field(ge=1)
    adapter_id: str = Field(pattern=ID)
    adapter_version: str = Field(min_length=1, max_length=40)
    source_artifact_ids: list[str] = Field(min_length=2, max_length=2)


class RunV2(Run):
    artifacts: list[ArtifactV2] = Field(min_length=1, max_length=40)
    native_view: NativeViewRegistration | None = None


class ManifestV2(Manifest):
    schema_version: Literal[2]
    runs: list[RunV2] = Field(max_length=100)


def safe_relative(value):
    if (not isinstance(value, str) or not value or len(value) > 240
            or '\\' in value or '%' in value or '\x00' in value
            or any(part.startswith('.') for part in value.split('/'))
            or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', part) for part in value.split('/'))
            or PurePosixPath(value).is_absolute()):
        raise CatalogError('Invalid registered artifact name.')
    return value


def read_confined(root, relative, limit=MAX_FILE_BYTES):
    """Open each path component without following symlinks; cap reads before parsing."""
    safe_relative(relative)
    descriptors = []
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd)
        parts = relative.split('/')
        for part in parts[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        descriptors.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise CatalogError('Registered file exceeds bounds or is not a regular file.')
        chunks, total = [], 0
        while chunk := os.read(fd, min(65_536, limit + 1 - total)):
            total += len(chunk)
            if total > limit:
                raise CatalogError('Registered file exceeds size limit.')
            chunks.append(chunk)
        return b''.join(chunks)
    except OSError as exc:
        raise CatalogError('Registered evidence is missing or inaccessible.') from exc
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def read_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CatalogError('Duplicate JSON field.')
            result[key] = value
        return result
    def finite_number(value):
        number = float(value)
        if not math.isfinite(number):
            raise CatalogError('Nonfinite JSON value.')
        return number
    try:
        return json.loads(data, object_pairs_hook=unique, parse_float=finite_number, parse_constant=lambda _: (
            _ for _ in ()).throw(CatalogError('Nonfinite JSON value.')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError('Invalid workspace JSON.') from exc


class Catalog:
    def __init__(self, root):
        # The operator chooses this path at server startup; browsers cannot change it.
        self.root = Path(root).absolute()

    def load(self):
        try:
            raw = read_json(read_confined(self.root, 'catalog.json', 2_000_000))
            if not isinstance(raw, dict) or type(raw.get('schema_version')) is not int or raw['schema_version'] not in {1, 2}:
                raise CatalogError('Unsupported workspace inventory version.')
            model = ManifestV2 if isinstance(raw, dict) and type(raw.get('schema_version')) is int and raw['schema_version'] == 2 else Manifest
            manifest = model.model_validate(raw)
            if len({r.id for r in manifest.runs}) != len(manifest.runs):
                raise CatalogError('Duplicate run identity.')
            expected = {'agent1': {'research'}, 'agent2': {'monitoring'},
                        'agent3': {'events', 'news'}, 'agent4': {'close'}}
            if sum(a.bytes for r in manifest.runs for a in r.artifacts) > 100_000_000:
                raise CatalogError('Workspace exceeds the local inventory size limit.')
            for run in manifest.runs:
                if run.workflow not in expected[run.agent]:
                    raise CatalogError('Workflow and agent disagree.')
                if (len({a.id for a in run.artifacts}) != len(run.artifacts)
                        or len({a.name for a in run.artifacts}) != len(run.artifacts)):
                    raise CatalogError('Duplicate artifact identity.')
                report = next((a for a in run.artifacts if a.id == run.report_id), None)
                if report is None or report.kind != 'report' or not report.name.endswith('.html'):
                    raise CatalogError('Registered report is unavailable.')
                # Fail closed rather than showing trusted summaries beside changed evidence.
                for artifact in run.artifacts:
                    self.read(run.id, artifact)
                if isinstance(run, RunV2):
                    from .report_views.delivery import validate_registration, load_view
                    validate_registration(run)
                    if run.native_view:
                        load_view(self, run)
            return manifest
        except (ValueError, TypeError, RecursionError) as exc:
            from .report_views.errors import NativeViewError
            if isinstance(exc, NativeViewError):
                raise
            raise CatalogError('Workspace inventory or evidence is invalid.') from exc

    def read(self, run_id, artifact):
        if not re.fullmatch(ID, run_id):
            raise CatalogError('Invalid run identity.')
        data = read_confined(self.root, f'runs/{run_id}/{artifact.name}')
        if len(data) != artifact.bytes or hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise CatalogError('Registered evidence has changed.')
        return data

    @staticmethod
    def public_run(run):
        value = run.model_dump()
        for artifact in value['artifacts']:
            artifact['url'] = f"/api/runs/{run.id}/files/{artifact['name']}"
        return value
