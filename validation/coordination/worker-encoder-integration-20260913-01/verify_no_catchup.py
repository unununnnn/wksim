"""Counterexample to catch-up projection, using the actual frozen JointRate."""
import hashlib
import json
from pathlib import Path


def verify(root):
    source = Path(root) / 'Simulator/wksim_runtime/joint_rate.py'
    raw = source.read_bytes()
    expected = '0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4'
    assert hashlib.sha256(raw).hexdigest() == expected
    namespace = {}
    exec(compile(raw, str(source), 'exec'), namespace)
    now = [0]
    events = []

    def forbidden_sleep(_):
        raise AssertionError('fixture provides known eligible release times')

    rate = namespace['JointRate']('f' * 32, .5,
        lambda kind, **fields: events.append(dict(kind=kind, **fields)),
        now=lambda: now[0], sleep=forbidden_sleep)
    rate.reanchor(0, 'fixture')
    rows = []
    for tick, start, work in ((0, 0, 10000000), (4, 10000000, 4000000),
                              (8, 18000000, 4000000), (12, 26000000, 4000000)):
        now[0] = start
        rate.begin_group(tick, lambda: None)
        start_lateness = events[-1]['lateness_ns']
        now[0] = start + work
        rate.end_group(tick + 4)
        rows.append(dict(start_tick=tick, start_lateness_ns=start_lateness,
                         end_lateness_ns=events[-1]['lateness_ns']))
    assert [r['start_lateness_ns'] for r in rows] == [0, 2000000, 2000000, 2000000]
    assert [r['end_lateness_ns'] for r in rows] == [2000000, 0, 0, 0]
    return dict(source_sha256=expected, observations=rows, performance_evidence=False)


if __name__ == '__main__':
    print(json.dumps(verify(Path(__file__).resolve().parents[3]), indent=2))
