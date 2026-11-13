"""Closed protected installation observation; no paths or machine credentials."""
from typing import Literal
from pydantic import Field
from .catalog import Record,ID

class Source(Record):
    mode: Literal['checkout','staged','unavailable']
    commit: str|None=Field(pattern=r'^[a-f0-9]{40}$')
    dirty: bool|None
    sha256: str|None=Field(pattern=r'^[a-f0-9]{64}$')

class Mismatch(Record):
    package: str=Field(max_length=80)
    expected: str=Field(max_length=80)
    installed: str|None=Field(max_length=80)

class Runtime(Record):
    platform: str=Field(max_length=80)
    architecture: str=Field(max_length=80)
    python: str=Field(max_length=80)
    supported: bool
    dependency_mismatches: list[Mismatch]=Field(max_length=100)
    lock_sha256: str=Field(pattern=r'^[a-f0-9]{64}$')

class Frontend(Record):
    state: Literal['matched','stale','unavailable']
    source_sha256: str|None=Field(pattern=r'^[a-f0-9]{64}$')
    built_at: str|None=Field(max_length=80)

class Versions(Record):
    inputs: int|None=Field(ge=0,le=2147483647)
    jobs: int|None=Field(ge=0,le=2147483647)
    catalog: int|None=Field(ge=0,le=2147483647)

class Expected(Record):
    inputs: Literal[1]
    jobs: Literal[2]
    catalog: Literal[3]

class Compatibility(Record):
    state: Literal['compatible','migration_required','unsupported','unavailable']
    versions: Versions
    expected: Expected
    automatic_migration: Literal[False]

class Installation(Record):
    schema_version: Literal[1]
    kind: Literal['keystone.installation']
    workspace_id: str=Field(pattern=ID)
    observed_at: str=Field(max_length=80)
    state: Literal['checked','attention']
    running_source: Source
    current_source: Source
    restart_required: bool
    runtime: Runtime
    frontend: Frontend
    compatibility: Compatibility
    automatic_update: Literal[False]
    automatic_migration: Literal[False]
    financial_approval: Literal[False]
    production_release_approved: Literal[False]
