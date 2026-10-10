"""Cooperative checkout-wide admission; direct APIs/other checkouts are outside it."""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import os
import stat

ROOT = Path(__file__).resolve().parents[1]
FD_ENV = 'KEYSTONE_MUTATOR_FD'


def inherited_fds():
    """Explicitly pass the admission lease to supervised child workers."""
    value = os.environ.get(FD_ENV)
    if value is None:
        return ()
    try:
        fd = int(value)
        os.fstat(fd)
        return (fd,)
    except (ValueError, OSError):
        return ()


def _open_lock(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise RuntimeError('Invalid admission lock.')
    return fd


@contextmanager
def gate(exclusive=False, path=None):
    target = Path(path) if path else ROOT / 'state' / '.keystone-maintenance.lock'
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = _open_lock(target)
    mutator = None
    previous = os.environ.get(FD_ENV)
    old_umask = os.umask(0o077)
    try:
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            if not exclusive:
                lease_path = target.with_name(target.name + '.mutator.lock')
                candidate = _open_lock(lease_path)
                borrowed = inherited_fds()
                if borrowed and (os.fstat(borrowed[0]).st_dev, os.fstat(borrowed[0]).st_ino) == (os.fstat(candidate).st_dev, os.fstat(candidate).st_ino):
                    os.close(candidate)
                    # The open file description (not merely an environment token)
                    # is shared with the supervising parent.
                    fcntl.flock(borrowed[0], fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    mutator = candidate
                    fcntl.flock(mutator, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    os.environ[FD_ENV] = str(mutator)
        except BlockingIOError:
            raise RuntimeError('Keystone gate busy; finish active work before retrying.') from None
        yield
    finally:
        if previous is None:
            os.environ.pop(FD_ENV, None)
        else:
            os.environ[FD_ENV] = previous
        if mutator is not None:
            os.close(mutator)
        os.close(fd)
        os.umask(old_umask)
