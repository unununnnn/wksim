"""Exclusive, retained POSIX storage for one explicit parameter transaction."""
import hashlib
import json
import os
from pathlib import Path
import stat
from uuid import UUID

ROOT = Path('/root')


def _directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (path.resolve() != path or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700
                or (path.stat().st_dev, path.stat().st_ino) != (info.st_dev, info.st_ino)):
            raise ValueError('Unsafe parameter storage directory')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _px4_targets(stack, px4_root):
    if px4_root is None:
        return {}
    root = Path(px4_root)
    if stack != 'px4' or not root.is_absolute():
        raise ValueError('PX4 root requires PX4 stack and absolute real directory')
    targets = {'etc': root / 'build/px4_sitl_default/etc', 'test_data': root / 'test_data'}
    for directory in (root, *targets.values()):
        if not directory.is_dir() or directory.resolve(strict=True) != directory:
            raise ValueError('PX4 root and native targets must be real directories')
    return {name: str(target) for name, target in targets.items()}


def _check_contents(path, targets):
    # Never traverse aliases to factory data or another experiment's files.
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            entry = Path(directory) / name
            info = entry.lstat()
            if (stat.S_ISLNK(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                    and Path(directory) == path and name in targets
                    and entry.resolve(strict=True) == Path(targets[name])):
                if name in dirs:
                    dirs.remove(name)
                continue
            if (not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                    or info.st_uid != os.geteuid()
                    or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)):
                raise ValueError('Unsafe linked or nonlocal parameter storage entry')


class ParameterStorage:
    def __init__(self, transaction_id, stack, *, reopen=False, px4_root=None):
        import fcntl
        if not isinstance(transaction_id, str) or stack not in ('arducopter', 'px4'):
            raise ValueError('Explicit transaction UUID and supported stack required')
        identity = UUID(transaction_id)
        if transaction_id not in (str(identity), identity.hex) or type(reopen) is not bool:
            raise ValueError('Canonical transaction UUID and boolean reopen required')
        directory = ROOT / ('wksim-parameter-state-' + identity.hex)
        self.path, self.fd = directory / 'storage', None
        self.stack = stack
        self.targets = _px4_targets(stack, px4_root)
        self.px4_root = str(Path(px4_root)) if px4_root is not None else None
        marker_data = dict(version=1, transaction_id=str(identity), stack=stack)
        if self.targets:
            marker_data.update(px4_root=self.px4_root, px4_targets=self.targets)
        marker = (json.dumps(marker_data,
                             sort_keys=True, separators=(',', ':')) + '\n').encode()
        self._marker = marker
        if not reopen:
            directory.mkdir(mode=0o700, exist_ok=False)
        try:
            self.fd = _directory(directory)
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError('Parameter storage lease conflict') from error
            marker_path = directory / 'marker.json'
            if not reopen:
                if list(directory.iterdir()):
                    raise ValueError('Initial parameter storage must be empty')
                self.path.mkdir(mode=0o700)
                marker_fd = os.open(marker_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(marker_fd, 'wb') as output:
                    output.write(marker)
                    output.flush()
                    os.fsync(output.fileno())
            self.metadata = dict(path=str(self.path), transaction_id=str(identity), stack=stack,
                                 marker_sha256=hashlib.sha256(marker).hexdigest(), reopened=reopen)
            if self.targets:
                self.metadata.update(px4_root=self.px4_root, px4_targets=dict(self.targets))
            self.check(stack, px4_root=px4_root)
        except BaseException:
            self.close()
            raise

    def check(self, stack, px4_root=None):
        if self.fd is None:
            raise ValueError('Parameter storage lease is closed')
        targets = _px4_targets(stack, px4_root)
        root = str(Path(px4_root)) if px4_root is not None else None
        if stack != self.stack or root != self.px4_root or targets != self.targets:
            raise ValueError('Parameter storage configuration mismatch')
        directory = self.path.parent
        current_fd = _directory(directory)
        try:
            current, held = os.fstat(current_fd), os.fstat(self.fd)
            if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                raise ValueError('Parameter storage directory identity mismatch')
            if set(item.name for item in directory.iterdir()) != {'marker.json', 'storage'}:
                raise ValueError('Unexpected parameter storage root entries')
            marker_path = directory / 'marker.json'
            marker = self._marker
            marker_fd = os.open(marker_path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(marker_fd, 'rb') as source:
                info = os.fstat(source.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
                        or info.st_size != len(marker) or source.read(len(marker) + 1) != marker):
                    raise ValueError('Parameter storage marker identity mismatch')
            os.close(_directory(self.path))
            _check_contents(self.path, targets)
            return dict(self.metadata)
        finally:
            os.close(current_fd)

    def close(self):
        # No LOCK_UN: inherited descriptors share this open-file description.
        # Closing the parent must not release a surviving FC's lease.
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()
