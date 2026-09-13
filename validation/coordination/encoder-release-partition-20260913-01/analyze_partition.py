"""Exact identities for one pinned failed rate stream, not a causal model."""
import gzip
import hashlib
import json
from pathlib import Path


def analyze(path):
    raw = gzip.decompress(Path(path).read_bytes())
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == '288c3305aedeae68e57ef3b44621064c946b94a15a3dafae195c7b5958a9bc0e'
    rows = [json.loads(line) for line in raw.splitlines()]
    starts = [r for r in rows if r['kind'] == 'rate_group_start']
    ends = [r for r in rows if r['kind'] == 'rate_group_end']
    assert len(starts) == len(ends) == 7141
    period = 8000000
    over, residual, release = [], [], []
    for index, (start, end) in enumerate(zip(starts, ends)):
        assert start['segment_id'] == end['segment_id'] == 1
        for field in ('epoch', 'start_tick', 'end_tick', 'actual_start_ns',
                      'ideal_start_ns', 'ideal_end_ns', 'requested_rate'):
            assert start[field] == end[field]
        assert start['requested_rate'] == .5
        work = end['actual_end_ns'] - start['actual_start_ns']
        over.append(max(0, work - period))
        assert end['lateness_ns'] == max(0, start['lateness_ns'] + work - period)
        if index:
            previous = starts[index - 1]
            assert start['start_tick'] == previous['start_tick'] + 4
            assert start['earliest_start_ns'] == max(start['ideal_start_ns'],
                                                     previous['actual_start_ns'] + period)
            excess = start['actual_start_ns'] - start['earliest_start_ns']
            remainder = excess - over[index - 1]
            assert remainder >= 0
            assert start['lateness_ns'] - previous['lateness_ns'] == excess
            residual.append(remainder)
            release.append(excess)
    # This identity uses the observed final group being over its own period.
    assert over[-1] > 0
    first = starts[0]['lateness_ns']
    assert first + sum(release) == starts[-1]['lateness_ns']
    assert first + sum(over) + sum(residual) == ends[-1]['lateness_ns']
    return dict(raw_rate_sha256=sha, first_start_lateness_ns=first,
                sum_all_work_over_ns=sum(over),
                sum_transition_release_excess_ns=sum(release),
                sum_release_excess_minus_previous_work_over_ns=sum(residual),
                last_end_lateness_ns=ends[-1]['lateness_ns'],
                max_residual_ns=max(residual),
                max_residual_start_tick=starts[1 + residual.index(max(residual))]['start_tick'],
                start_drift_closes=True, end_partition_closes=True,
                causal_attribution=None)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[3]
    path = root / 'validation/coordination/worker-encoder-integration-20260913-01/flight/rate.jsonl.gz'
    print(json.dumps(analyze(path), indent=2))
