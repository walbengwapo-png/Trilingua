"""Parent-owned scratch, with leases so startup cleanup skips live jobs."""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import tempfile
import time

DEFAULT_STALE_SECONDS = 86400


def root():
    path = Path(os.environ.get('OCR_SCRATCH_ROOT', str(Path(tempfile.gettempdir())/'trilingua-pdf-jobs'))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _lease(stream):
    stream.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def remove(path, parent):
    path, parent = Path(path), Path(parent).resolve()
    if path.is_symlink() or path.resolve().parent != parent or not path.name.startswith('job-'):
        raise ValueError('Scratch removal target escaped its owned root')
    shutil.rmtree(path)


@contextmanager
def owned_scratch():
    parent = root()
    directory = Path(tempfile.mkdtemp(prefix='job-', dir=parent))
    lease = (directory/'lease').open('w+b')
    try:
        lease.write(b'0');lease.flush();_lease(lease)
        yield str(directory)
    finally:
        lease.close()
        remove(directory, parent)


def sweep_stale():
    parent = root()
    age = int(os.environ.get('OCR_SCRATCH_MAX_AGE_SECONDS', DEFAULT_STALE_SECONDS))
    if age <= 0:
        raise ValueError('Scratch retention age must be positive')
    removed = []
    for directory in parent.glob('job-*'):
        if directory.is_symlink() or not directory.is_dir() or directory.resolve().parent != parent:
            continue
        marker = directory/'lease'
        if not marker.is_file() or time.time()-marker.stat().st_mtime <= age:
            continue
        try:
            with marker.open('r+b') as lease:
                _lease(lease)
            remove(directory, parent)
            removed.append(directory.name)
        except (OSError, FileNotFoundError):
            continue
    return removed
