"""Peak-allocation probe for many short reads: per-chunk list vs one bytearray.

The same drip reader (one freshly allocated byte per read) and the same limit are
run against two revisions of the bounded reader:

* ``replay-list-join-20260913-01.py`` - round-1 revision, list of chunks + join
  (sha256 4406b7f4..., git working-tree state delivered in round 1), and
* ``Simulator/wksim_runtime/replay.py`` - delivered single-bytearray revision.

tracemalloc reports the peak traced allocation while the bounded read runs, with
request recording disabled in the reader so the double itself does not dominate.
This measures one synthetic 1-byte-per-read double, not OS or interpreter-total
memory, and no theoretical bound is claimed from it.

Exit 0 when the delivered revision measures below 4 * limit and the round-1
revision does not. No runtime, native, SITL, model, ROS or network resource.
"""
import hashlib
import json
from pathlib import Path
import sys
import tracemalloc
import types
from unittest import mock


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FROZEN = HERE / 'replay-list-join-20260913-01.py'
FROZEN_SHA256 = '4406b7f4e67606c869d5f5aea514e7b89ed1f616c4d00ea4bed4815a23e4f8e2'
LIMIT = 64 * 1024
THRESHOLD_FACTOR = 4


class DripReader:
    """One freshly allocated byte per read; records nothing, so it stays small."""

    def __init__(self, payload):
        self.payload = payload
        self.served = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        if self.served >= len(self.payload):
            return b''
        chunk = self.payload[self.served:self.served + 1]
        self.served += 1
        return chunk


def load_module(path, expected_sha256, name):
    source = path.read_text(encoding='utf-8')
    actual = hashlib.sha256(source.encode('utf-8')).hexdigest()
    if actual != expected_sha256:
        raise SystemExit(f'{path.name} changed: {actual}')
    # Only the relative import is rewritten so the frozen copy can be exec'd.
    source = source.replace('from .config import _unique_object',
                            'from Simulator.wksim_runtime.config import _unique_object', 1)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def probe(module, record, limit):
    reader = DripReader(record)
    with mock.patch.object(module, '_open_record_file', lambda path: reader):
        tracemalloc.start()
        try:
            data = module._read_bounded(Path('unused'), limit)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    return {'accepted': data is not None,
            'bytes_returned': None if data is None else len(data),
            'bytes_served_by_reader': reader.served,
            'hash_matches_record': data is not None and hashlib.sha256(data).hexdigest()
            == hashlib.sha256(record).hexdigest(),
            'peak_traced_bytes': peak,
            'peak_over_limit': round(peak / limit, 3)}


def main():
    sys.path.insert(0, str(REPO))
    import importlib
    delivered = importlib.import_module('Simulator.wksim_runtime.replay')
    round1 = load_module(FROZEN, FROZEN_SHA256, 'replay_list_join_round1')
    record = open_record(LIMIT)
    report = {'limit_bytes': LIMIT,
              'reads_per_record': LIMIT + 1,
              'threshold_factor': THRESHOLD_FACTOR,
              'round1_list_join': probe(round1, record, LIMIT),
              'delivered_single_buffer': probe(delivered, record, LIMIT)}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    threshold = THRESHOLD_FACTOR * LIMIT
    improved = report['delivered_single_buffer']['peak_traced_bytes'] < threshold \
        <= report['round1_list_join']['peak_traced_bytes']
    both_correct = all(part['accepted'] and part['hash_matches_record']
                       for part in (report['round1_list_join'], report['delivered_single_buffer']))
    return 0 if improved and both_correct else 1


def open_record(limit):
    payload = b'{"p":"' + b'x' * (limit - 8) + b'"}'
    assert len(payload) == limit
    return payload


if __name__ == '__main__':
    sys.exit(main())
