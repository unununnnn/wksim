"""Independent artifact/source/process audit; no process launch or flight commands."""
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.telemetry_dialect import load_dialect
from validate_product_isolation import identity, group_members


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(accepted, attempts):
    current_original = identity(828)
    report = dict(status='pass', original=current_original, attempts=[], accepted=[],
                  audit_sha256=digest(__file__), scope='telemetry foundation, not QGC or Full acceptance')
    groups = set()
    for folder in attempts:
        top = json.loads((folder / 'result.json').read_text())
        for observation in top['results']:
            path = Path(observation['runtime_result'])
            result = json.loads(path.read_text())
            own = {child['pgid'] for child in result['children'].values()}
            groups.update(own)
            assert result['children_reaped'] and not result['cleanup_errors'] and not group_members(own)
            assert observation['original_before'] == observation['original_final'] == current_original
            assert not Path(result['config']['telemetry_socket']).exists()
            report['attempts'].append(dict(run_id=result['run_id'], runtime_status=result['status'],
                gate_status=observation['status'], error=observation.get('error'), result=str(path), sha256=digest(path)))
            if folder != accepted:
                continue  # retain failed histories; never reclassify them as final passes
            assert observation['status'] == result['status'] == 'pass'
            assert result['safe_landing'] and result['stop_kind'] == 'landed_stop'
            assert result['run_id'] == observation['run_id'] == result['config']['run_id']
            assert digest(result['fc_binary']) == result['fc_sha256']
            for relative, expected in result['runtime_sha256'].items():
                assert digest(REPO / relative) == expected, relative + ': post-flight source changed'
            assert result['telemetry']['observer_exit'] == 0
            final = result['telemetry']['final_report']
            assert final['counters']['invalid'] == final['counters']['wrong_peer'] == 0
            assert final['counters']['dropped'] > 0 and not final['control_path']
            steps = observation['steps']
            assert [s['event'] for s in steps] == ['consumer_detached_airborne', 'new_receiver_same_run', 'owned_observer_stopped']
            assert steps[0]['truth']['height_m'] > 2 and steps[1]['truth']['time'] > steps[0]['truth']['time']
            assert steps[2]['sequence'] > steps[0]['sequence'] and observation['commands_sent'] == 0
            heights, last_time = [], -1
            with path.with_name('truth.jsonl').open() as source:
                for line in source:
                    row = json.loads(line)
                    assert math.isfinite(row['time']) and row['time'] > last_time
                    last_time = row['time']
                    heights.append(-row['vehicle'][8])
            assert max(heights) >= 2.5 and abs(heights[-1]) < 0.3
            assert last_time > steps[2]['truth']['time']
            # Decode the original bytes directly through the generated upstream
            # parser, not the product's decode_datagram/forward implementation.
            module, decoder = load_dialect(result['stack'])
            assert decoder == final['decoder']
            ids, sequence, count, armed, boot_times = set(), 0, 0, False, []
            capture = folder / (result['stack'] + '-native.jsonl')
            for line in capture.read_text().splitlines():
                wrapper = json.loads(line)
                row = wrapper['observation']
                wire = base64.b64decode(row['packet_base64'], validate=True)
                messages = module.MAVLink(None).parse_buffer(wire)
                assert b''.join(bytes(m.get_msgbuf()) for m in messages) == wire
                assert [m.get_msgId() for m in messages] == row['message_ids']
                assert row['run_id'] == result['run_id'] and row['sequence'] > sequence
                sequence = row['sequence']
                for message in messages:
                    assert message.get_srcSystem() == result['resources']['native_system_id']
                    assert message.get_srcComponent() == 1
                    ids.add(message.get_msgId())
                    if message.get_type() == 'HEARTBEAT':
                        armed |= bool(message.base_mode & 128)
                    if message.get_type() == 'ATTITUDE':
                        assert all(math.isfinite(v) for v in (message.roll, message.pitch, message.yaw))
                    if message.get_type() == 'GLOBAL_POSITION_INT':
                        boot_times.append(message.time_boot_ms)
                        assert abs(message.lat) <= 900000000 and abs(message.lon) <= 1800000000
                count += 1
            assert count == observation['records'] and armed and {0, 30, 33}.issubset(ids)
            assert len(boot_times) > 2 and boot_times[-1] > boot_times[0]
            report['accepted'].append(dict(stack=result['stack'], run_id=result['run_id'],
                native_records=count, native_message_ids=sorted(ids), capture_sha256=digest(capture),
                runtime_result_sha256=digest(path), max_height_m=max(heights), final_height_m=heights[-1],
                final_time=last_time, observer_counters=final['counters'], steps=steps))
    assert {row['stack'] for row in report['accepted']} == {'px4', 'arducopter'}
    report['owned_group_count'] = len(groups)
    report['remaining_groups'] = group_members(groups)
    assert not report['remaining_groups']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accepted', type=Path, required=True)
    parser.add_argument('--attempts', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.accepted.resolve(), [p.resolve() for p in args.attempts])
    with args.output.open('x') as target:
        target.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], accepted=len(report['accepted']),
                         attempts=len(report['attempts']), groups=report['owned_group_count'])))


if __name__ == '__main__':
    main()
