"""Cooperative POSIX maintenance gate for this checkout's command-line writers.

Direct Python APIs and other checkouts must be quiesced separately. Shared locks
allow normal agent parent/worker processes; exclusive snapshots fail fast if busy.
"""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import os

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def gate(exclusive=False, path=None):
    target = Path(path) if path else ROOT / 'state' / '.keystone-maintenance.lock'
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Keystone maintenance gate busy; finish active work before retrying.') from None
        yield
    finally:
        os.close(fd)
