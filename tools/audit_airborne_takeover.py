"""Read-only raw-truth audit; --release-only isolates the airborne-hold symptom."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]


def audit(path, release_only=False):
    path = Path(path)
    result = json.loads(path.read_text(encoding='utf-8'))
    probe = result['task']['takeover_probe']
    check = next(c for c in probe['checks'] if c['label'] == 'released_no_output_physics_continues')
    rows = [json.loads(line) for line in path.with_name('truth.jsonl').read_text().splitlines()]
    for before, after in zip(rows, rows[1:]):
        assert after['time'] > before['time'], 'Physical time did not strictly advance'
    start, end = (check[phase]['truth']['records'] for phase in ('before', 'after'))
    assert 1 <= start < end <= len(rows), 'Invalid release truth cursors'
    for phase, count in (('before', start), ('after', end)):
        assert rows[count-1]['time'] == check[phase]['truth']['final_time'], 'Relabelled physical cursor'
    release = rows[start-1:end]
    heights = [-row['vehicle'][8] for row in release]
    assert all(math.isfinite(h) for h in heights), 'Non-finite physical height'
    metrics = dict(samples=len(release), start_time=release[0]['time'], end_time=release[-1]['time'],
                   min_height_m=min(heights), max_height_m=max(heights),
                   max_height_error_m=max(abs(h-3) for h in heights))
    assert metrics['end_time']-metrics['start_time'] >= 2, 'Insufficient physical release interval'
    assert metrics['min_height_m'] >= 2, 'Released aircraft landed/descended below 2m: '+json.dumps(metrics)
    assert metrics['max_height_error_m'] <= .6, 'Release hover altitude gate exceeded'
    first, last = (check[phase]['received_monotonic_s'] for phase in ('before', 'after'))
    assert last-first >= 2, 'Insufficient observed release interval'
    assert not any(first <= r['received_monotonic_s'] <= last for r in probe['native_outputs']), 'Output during released interval'
    if release_only:
        return dict(status='pass', release=metrics, scope='raw airborne release only; no complete-flight claim')
    assert result['status'] == 'pass' and result['safe_landing'], result.get('error')
    assert result['children_reaped'] and not result['cleanup_errors']
    assert all(c['returncode'] is not None for c in result['children'].values())
    assert abs(-rows[-1]['vehicle'][8]) < .3, 'Final physical ground gate failed'
    assert probe['native_commands_published_by_observers'] == 0
    for source, expected in result['runtime_sha256'].items():
        assert hashlib.sha256((REPO / source).read_bytes()).hexdigest() == expected, 'Runtime source drift: '+source
    for name, expected in result['product_sha256'].items():
        source = REPO / 'ros2/src/prometheus_control/prometheus_control' / name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, 'Product source drift: '+name
    envelopes = result['task']['request_envelopes']
    assert all(e['run_id'] == result['run_id'] and e['control_epoch'] == result['task']['control_epoch'] for e in envelopes)
    assert all(a['request_id'] < b['request_id'] for a, b in zip(envelopes, envelopes[1:]))
    assert len(probe['holds']) == 1
    hold = probe['holds'][0]
    assert hold['reference']['airborne'] and hold['reference']['request_id'] == 6
    reference = hold['reference']
    start, end = (hold[phase]['truth']['records'] for phase in ('before', 'after'))
    assert 1 <= start < end <= len(rows)
    errors, yaw_errors = [], []
    for row in rows[start-1:end]:
        vector = row['vehicle']
        errors.append(math.dist([vector[7], vector[6], -vector[8]], reference['position_enu_m']))
        w, x, y, z = vector[12:16]
        yaw = math.pi/2-math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
        yaw_errors.append(abs(math.remainder(yaw-reference['yaw_enu_rad'], 2*math.pi)))
    assert max(errors) <= .5 and max(yaw_errors) <= .15, 'Actual takeover moved away from captured pose/yaw'
    samples = probe['native_outputs'][hold['native_output_start']:hold['native_output_end']]
    assert len(samples) == hold['samples'] and len(samples) >= 10
    return dict(status='pass', release=metrics, hold=dict(physical_samples=end-start+1,
        max_position_error_m=max(errors), max_yaw_error_rad=max(yaw_errors), native_samples=len(samples)),
        final_height_m=-rows[-1]['vehicle'][8], source_hashes_checked=True,
        scope='real node transition, not GCS interface or MissionTask resume')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    parser.add_argument('--release-only', action='store_true')
    args = parser.parse_args()
    try:
        report = audit(args.result, args.release_only)
    except (AssertionError, ValueError, KeyError, OSError) as error:
        report = dict(status='failed', error=str(error))
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
