"""Before/after probe for the load_evidence unbounded-read race (offline, small).

Runs one probe against two module versions:

* ``replay-before-fix.py`` - byte-exact HEAD revision (git blob fd2212a4), and
* ``Simulator/wksim_runtime/replay.py`` - the delivered revision.

The probe lies about the record size through stat() (the TOCTOU window) and spies
on ``pathlib.Path.read_bytes``, so it reports how many bytes each version really
pulls into memory for a record that is over the limit. The pre-fix version does
one unbounded convenience read of the whole record; the delivered version does
none and rejects at limit + 1 bytes.

Exit 0 only when the pre-fix violation and the delivered fix are both observed.
No runtime, native, SITL, model, ROS or network resource is used.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import stat as stat_module
import sys
import tempfile
import types
from unittest import mock


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FROZEN = HERE / 'replay-before-fix.py'
FROZEN_SHA256 = '884da1ec23f0a5f5ed37d040f8081d25c1e58a723ee9db5f62d745ac483088f6'
LIMIT = 64
RECORD_BYTES = 1024 * 1024


def frozen_module():
    source = FROZEN.read_text(encoding='utf-8')
    actual = hashlib.sha256(source.encode('utf-8')).hexdigest()
    if actual != FROZEN_SHA256:
        raise SystemExit(f'frozen pre-fix source changed: {actual}')
    # Only the relative import is rewritten so the frozen copy can be exec'd.
    source = source.replace('from .config import _unique_object',
                            'from Simulator.wksim_runtime.config import _unique_object', 1)
    module = types.ModuleType('replay_before_fix')
    module.__file__ = str(FROZEN)
    exec(compile(source, str(FROZEN), 'exec'), module.__dict__)
    return module


def stale_stat(root, name, size):
    real = Path.stat

    def fake(self, *args, **kwargs):
        if self.parent == root and self.name == name:
            return os.stat_result((stat_module.S_IFREG | 0o644, 0, 0, 1, 0, 0, size, 0, 0, 0))
        return real(self, *args, **kwargs)

    return mock.patch.object(Path, 'stat', fake)


def probe(module, root):
    """Report outcome, unbounded read_bytes usage and bytes pulled per call."""
    calls, pulled, real_read_bytes = [], [], Path.read_bytes

    def spy(self):
        data = real_read_bytes(self)
        calls.append(self.name)
        pulled.append(len(data))
        return data

    with mock.patch.object(Path, 'read_bytes', spy), \
            mock.patch.object(module, 'MAX_BYTES', LIMIT), \
            stale_stat(root, 'result.json', 4):
        try:
            module.load_evidence(root)
            outcome = 'accepted'
        except ValueError as error:
            outcome = str(error)
    return {'outcome': outcome, 'unbounded_read_bytes_calls': calls,
            'bytes_pulled_per_call': pulled,
            'has_bounded_reader_seam': hasattr(module, '_open_record_file')}


def main():
    sys.path.insert(0, str(REPO))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        (root / 'result.json').write_bytes(b'{"run_id":"probe","epoch":1}' + b' ' * RECORD_BYTES)
        size = (root / 'result.json').stat().st_size
        current = importlib.import_module('Simulator.wksim_runtime.replay')
        report = {'limit_bytes': LIMIT, 'record_bytes_on_disk': size,
                  'before_fix': probe(frozen_module(), root),
                  'after_fix': probe(current, root)}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    before, after = report['before_fix'], report['after_fix']
    violated = bool(before['bytes_pulled_per_call']) \
        and max(before['bytes_pulled_per_call']) > LIMIT + 1 \
        and not before['has_bounded_reader_seam']
    fixed = not after['bytes_pulled_per_call'] \
        and 'grew or was replaced' in after['outcome'] \
        and after['has_bounded_reader_seam']
    return 0 if violated and fixed else 1


if __name__ == '__main__':
    sys.exit(main())
