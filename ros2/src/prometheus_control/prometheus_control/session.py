# SPDX-License-Identifier: Apache-2.0
"""One control epoch and durable, non-reused native ACK identities for a run.

The Linux lock is held for the whole node lifetime. The counter is committed
before publishing a native command; an interrupted write cannot reuse a token.
This is local ownership/replay protection, not remote authentication.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import uuid


class RunSession:
    VERSION = 1
    MAX_NATIVE_REQUESTS = 55 * 255

    def __init__(self, run_id, uav_id, directory=None):
        if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', run_id):
            raise ValueError('Explicit valid run_id is required; legacy unscoped control is disabled')
        if type(uav_id) is not int or not 1 <= uav_id <= 255:
            raise ValueError('uav_id must be an integer in 1..255')
        self.run_id, self.uav_id = run_id, uav_id
        if directory is None:
            base = Path('/tmp') / f'wksim-control-{os.getuid()}'
            self._private_directory(base)
            directory = base / f'{run_id}--{uav_id}'
        self.directory = Path(directory)
        self._private_directory(self.directory)
        self.lock = os.open(self.directory / 'owner.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            mode = os.fstat(self.lock)
            if not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.getuid() or stat.S_IMODE(mode.st_mode) != 0o600:
                raise ValueError('Unsafe control ownership file')
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.counter_path = self.directory / 'counter.json'
            if self.counter_path.exists() or self.counter_path.is_symlink():
                if self.counter_path.is_symlink() or not self.counter_path.is_file():
                    raise ValueError('Unsafe native request counter')
                self.counter = json.loads(self.counter_path.read_text(encoding='utf-8'))
                if (not isinstance(self.counter, dict) or set(self.counter) != {'run_id', 'uav_id', 'next_native'}
                        or self.counter['run_id'] != run_id or self.counter['uav_id'] != uav_id
                        or type(self.counter['next_native']) is not int
                        or not 0 <= self.counter['next_native'] <= self.MAX_NATIVE_REQUESTS):
                    raise ValueError('Invalid native request counter; cannot prove no reuse')
            else:
                self.counter = dict(run_id=run_id, uav_id=uav_id, next_native=0)
                self._commit()
        except BaseException:
            os.close(self.lock)
            self.lock = None
            raise
        self.epoch = uuid.uuid4().hex
        self.last_request = 0

    @staticmethod
    def _private_directory(path):
        if not path.is_absolute() or path.is_symlink() or path.resolve() != path:
            raise ValueError('Control storage must be an absolute non-symlink Linux directory')
        path.mkdir(mode=0o700, exist_ok=True)
        mode = path.stat()
        if not path.is_dir() or mode.st_uid != os.getuid() or stat.S_IMODE(mode.st_mode) != 0o700:
            raise ValueError('Control storage must be owned by current UID with mode0700')

    def _commit(self):
        temporary = self.directory / ('.counter-' + uuid.uuid4().hex)
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                json.dump(self.counter, output, allow_nan=False)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.counter_path)
            descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def accept(self, request):
        if self.lock is None:
            raise ValueError('Control session is closed')
        if type(request.version) is not int or request.version != self.VERSION:
            raise ValueError('unsupported_request_version')
        if request.run_id != self.run_id or request.control_epoch != self.epoch:
            raise ValueError('wrong_run_or_control_epoch')
        number = request.request_id
        if type(number) is not int or not self.last_request < number < 2**64:
            raise ValueError('request_id_not_increasing')
        # Even a later semantic rejection consumes the envelope ID. Retry is a new request.
        self.last_request = number
        return number

    def native_identity(self):
        if self.lock is None:
            raise ValueError('Control session is closed')
        serial = self.counter['next_native']
        # ponytail: 14025 native setup operations per run; start a new run on exhaustion.
        # Streamed setpoints do not consume this space. Never cycle it inside a run.
        if serial >= self.MAX_NATIVE_REQUESTS:
            raise ValueError('Native request identity space exhausted; start a new run')
        self.counter['next_native'] += 1
        try:
            self._commit()
        except BaseException:
            self.close()  # Persistence uncertain: no further command may be published.
            raise
        return 200 + serial // 255, 1 + serial % 255

    def close(self):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
