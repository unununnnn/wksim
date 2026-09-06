"""Read-only audit of two real product visual results and current source identities."""
import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(paths):
    flights, outputs = [], []
    for path in paths:
        visual = json.loads(path.read_text(encoding='utf-8'))
        assert visual['status'] == 'pass' and all(visual['checks'].values()), path
        assert visual['display_socket_removed'], 'Owned relay socket was not removed'
        assert visual['unexpected_probe_acks'] == 0
        assert visual['rejected_max'] >= visual['rejection_probes'] == 10
        assert visual['validator_sha256'] == sha(REPO / 'tools/validate_product_visual.py')
        for source, expected in visual['source_sha256'].items():
            assert sha(REPO / source) == expected, source
        flight_path = Path(visual['flight_result'])
        assert sha(flight_path) == visual['flight_result_sha256']
        flight = json.loads(flight_path.read_text(encoding='utf-8'))
        assert flight['status'] == 'pass' and flight['safe_landing'] and flight['children_reaped']
        assert not flight['cleanup_errors']
        assert flight['run_id'] == visual['run_id']
        assert all(c['returncode'] is not None for c in flight['children'].values())
        assert len(flight['task']['sent']) == 6
        assert not any(e['event'] in ('setup_rejected', 'command_rejected', 'control_revoked') for e in flight['task']['events'])
        assert all(e['accepted'] for e in flight['task']['events'] if e['event'] == 'native_ack')
        for source, expected in flight['runtime_sha256'].items():
            assert sha(REPO / source) == expected, source
        rows = []
        for readback in sorted(path.parent.glob('actor-*.jsonl')):
            rows.extend(json.loads(line) for line in readback.read_text().splitlines())
        assert len(rows) == visual['readbacks']
        assert all(row['packet']['run_id'] == flight['run_id'] and row['packet']['version'] == 2 for row in rows)
        assert all(row['packet']['display_clock'] == 'windows_utc_bound' and
                   0 <= row['packet']['transport_age_bound_s'] <= .75 for row in rows)
        assert all(rows[i]['packet']['sequence'] < rows[i+1]['packet']['sequence'] for i in range(len(rows)-1))
        for frame in visual['captures']:
            assert sha(frame['file']) == frame['sha256']
            assert Path(frame['file']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        flights.append(flight)
        outputs.append(dict(stack=flight['stack'], visual_result=str(path), visual_sha256=sha(path),
                            run_result=str(flight_path), run_sha256=sha(flight_path),
                            readbacks=len(rows), truth=flight['truth'], max_error=visual['max_error'],
                            outage=visual['outage'], packets_rejected=visual['rejected_max']))
    assert {f['stack'] for f in flights} == {'px4', 'arducopter'}
    normalized = [[{k: v for k, v in msg.items() if k != 'header'} for msg in f['task']['sent']] for f in flights]
    assert normalized[0] == normalized[1], 'Public task inputs differ'
    common = set(flights[0]['runtime_sha256']) & set(flights[1]['runtime_sha256'])
    assert all(flights[0]['runtime_sha256'][p] == flights[1]['runtime_sha256'][p] for p in common)
    return dict(status='pass', same_six_public_inputs=True, matching_common_sources=len(common),
                scope='two independent product runs, not a joint clock or Full acceptance', runs=outputs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('visual_results', nargs=2, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.visual_results), indent=2))
