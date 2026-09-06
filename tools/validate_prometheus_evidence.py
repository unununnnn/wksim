"""Read-only audit of two public-interface flights and their exact installed sources."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

REPO = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(path):
    data = json.loads(path.read_text())
    assert data['status'] == 'pass' and data['children_reaped']
    assert not data['dds']['commands'] and not data['dds']['received_counts'].get('setpoints_sent', 0)
    assert digest(Path(data['fc_binary'])) == data['fc_binary_sha256']
    for file, expected in data['implementation_sha256'].items():
        assert digest(REPO/file) == expected, file
    workspace = Path(data['prometheus_workspace'])
    package = workspace/'install/prometheus_control/local/lib/python3.10/dist-packages/prometheus_control'
    for file, expected in data['prometheus']['implementation_sha256'].items():
        assert all(digest(folder/file) == expected for folder in (
            REPO/'ros2/src/prometheus_control/prometheus_control',
            workspace/'src/prometheus_control/prometheus_control', package)), file
    if 'ap_dds_candidate' in data:
        source = Path(data['ap_dds_candidate'])/'src'
        for file, expected in data['candidate_source_sha256'].items():
            assert digest(source/file) == expected, file
    records = [json.loads(line) for line in path.with_name('prometheus.jsonl').read_text().splitlines()]
    states = [record['message'] for record in records if record.get('topic') == '/uav1/prometheus/state']
    armed = [i for i, state in enumerate(states) if state['armed']]
    assert armed and max(state['position'][2] for state in states if state['odom_valid']) >= 2.5
    assert min(math.dist(state['position'], [2., 3., 3.]) for state in states if state['odom_valid']) <= .5
    stale = [i for i, state in enumerate(states) if i > armed[-1] and not state['connected']]
    assert stale, 'Product state did not report ground DDS loss'
    assert states[-1]['connected'] and not states[-1]['armed'] and abs(states[-1]['position'][2]) < .3
    events = data['prometheus']['events']
    assert not any(e['event'] in ('setup_rejected', 'command_rejected', 'control_revoked') for e in events)
    ack_count = sum(e['event'] == 'native_ack' and e['accepted'] for e in events)
    assert ack_count >= 6
    inputs = [{key: value for key, value in item.items() if key != 'header'} for item in data['prometheus']['sent']]
    assert len(inputs) == 6
    return dict(result=str(path.relative_to(REPO)), result_sha256=digest(path), stack=data['stack'],
                log_sha256=digest(path.with_name('prometheus.jsonl')), states=len(states),
                accepted_native_acks=ack_count, stale_states_after_landing=len(stale),
                identical_source_files_checked=len(data['prometheus']['implementation_sha256']),
                fc_binary_sha256=data['fc_binary_sha256'], reconnect=data['dds_reconnect']), inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arducopter_result', type=Path)
    parser.add_argument('px4_result', type=Path)
    parser.add_argument('unit_log', type=Path)
    args = parser.parse_args()
    ap, ap_input = audit(args.arducopter_result.resolve())
    px, px_input = audit(args.px4_result.resolve())
    assert (ap['stack'], px['stack']) == ('arducopter', 'px4') and ap_input == px_input
    log = args.unit_log.read_text()
    match = re.search(r'Ran (\d+) tests in .*\n\nOK\s*$', log)
    assert match, 'Missing successful full unit run'
    hashes = {str(file.relative_to(REPO)): digest(file) for file in (
        args.unit_log.resolve(), REPO/'validation/test_prometheus_native.py', Path(__file__).resolve(),
        REPO/'patches/arducopter/0001-dds-global-position-yaw.patch', REPO/'patches/arducopter/0002-dds-local-state.patch')}
    print(json.dumps(dict(status='pass', unit_tests=int(match[1]), identical_public_input=True,
                          flights=[ap, px], artifacts_sha256=hashes), indent=2))


if __name__ == '__main__':
    main()
