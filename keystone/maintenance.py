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
def control_write_gate(*, queue_only=False):
    """HTTP control writes join CLI admission without process-wide env/umask changes.

    This lease is never lent to a child. The later worker uses the normal operation
    supervisor and its inherited lease. Threaded HTTP callers must not use gate(),
    which intentionally changes process-wide settings for CLI child creation.
    queue_only covers transactional admission records while an enabled worker
    owns the financial mutator lease; it still excludes exclusive maintenance.
    """
    target = ROOT / 'state' / '.keystone-maintenance.lock'
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptors = []
    try:
        locks = [(target, fcntl.LOCK_SH)]
        if not queue_only:
            locks.append((target.with_name(target.name + '.mutator.lock'), fcntl.LOCK_EX))
        for path, mode in locks:
            fd = _open_lock(path)
            descriptors.append(fd)
            fcntl.flock(fd, mode | fcntl.LOCK_NB)
        yield tuple(descriptors)
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


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
