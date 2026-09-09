"""Real ArduCopter ground sensor probe with stationary truth; NEVER flight evidence."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import uuid

HERE = Path(__file__).resolve().parent

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def audit(path):
    manifest = json.loads((path / 'manifest.json').read_text())
    assert manifest['fault'] == 'none' and manifest['returncode'] == 0
    assert manifest['failure'] is None and manifest['frames_sent'] == 8000
    sent = [bytes.fromhex(json.loads(line)['hex']).strip() for line in (path / 'wire.jsonl').read_text().splitlines()
            if json.loads(line)['direction'] == 'send']
    groups = defaultdict(bytearray)
    json_ticks = []
    received = []
    samples = {}
    warmups = set()
    warmed_generations = set()
    generations = {}
    previous_source = {}
    phases = defaultdict(int)
    for line in (path / 'native.tsv').read_text().splitlines():
        cols = line.split('\t')
        if cols[0] == 'FAIL':
            raise ValueError('native failure: ' + line)
        if cols[0] == 'JSON':
            raw = bytes.fromhex(cols[1])
            received.append(raw)
            value = json.loads(raw)
            tick = int(value['wksim'].split(':')[-1])
            assert value['wksim'] == f"{manifest['run_id']}:{manifest['epoch']}:1:{tick}"
            assert value['position'] == [0, 0, 0]
            assert value['imu'] == {'gyro': [0, 0, 0], 'accel_body': [0, 0, -9.80665]}
            assert abs(value['timestamp'] - tick / 1000) < 1e-10
            json_ticks.append(tick)
        elif cols[0] == 'GENERATION':
            tick, instance, generation = map(int, cols[1:4])
            assert tick < 4000 and generation == generations.get(instance, 0) + 1
            generations[instance] = generation
            previous_source[instance] = -1
        elif cols[0] == 'SAMPLE':
            tick, instance, source_ms, hal_us = map(int, cols[1:5])
            assert int(cols[-1]) == generations[instance]
            assert hal_us == (tick - 1) * 1000
            assert source_ms > previous_source[instance]
            assert (source_ms == 0 and tick < 4000) or 0 <= tick - source_ms <= 500
            previous_source[instance] = source_ms
            samples[tick, instance] = source_ms
        elif cols[0] == 'WARMUP':
            tick, instance = map(int, cols[1:3])
            key = (instance, generations[instance])
            assert key not in warmed_generations
            warmed_generations.add(key)
            warmups.add((tick, instance))
        elif cols[0] == 'WRITE':
            tick, instance, suppressed, ret = map(int, cols[1:5])
            assert int(cols[6]) == generations[instance]
            raw = bytes.fromhex(cols[5])
            assert (tick, instance) in samples
            assert suppressed == int(4000 <= tick < 6000)
            assert ret == (0 if suppressed else len(raw))
            groups[tick, instance].extend(raw)
            phases['suppressed' if suppressed else ('before' if tick < 4000 else 'after')] += ret if not suppressed else len(raw)
    assert json_ticks == list(range(1, 8001))
    assert received == sent
    assert warmups and all(tick < 4000 for tick, _ in warmups)
    assert set(groups) == set(samples) - warmups
    sample_ticks = sorted(tick for tick, instance in samples if instance == 0)
    assert len(sample_ticks) == len(samples)
    assert sample_ticks == list(range(sample_ticks[0], 8001, 200))
    assert all(phases[k] > 0 for k in ['before', 'suppressed', 'after'])
    tow = []
    packet_count = 0
    for (tick, instance), data in sorted(groups.items()):
        offset = 0
        while offset < len(data):
            assert data[offset:offset+2] == b'\xb5\x62'
            size = int.from_bytes(data[offset+4:offset+6], 'little')
            packet = data[offset:offset+8+size]
            assert len(packet) == size + 8
            a = b = 0
            for value in packet[2:-2]:
                a = (a + value) & 255
                b = (b + a) & 255
            assert packet[-2:] == bytes([a, b])
            if packet[2] == 1 and packet[3] in [2, 3, 4, 6, 7, 0x12, 0x20, 0x30]:
                tow.append({'tick': tick, 'instance': instance, 'message': packet[3],
                            'source_ms': samples[tick, instance],
                            'tow_ms': int.from_bytes(packet[6:10], 'little')})
            packet_count += 1
            offset += len(packet)
    assert any(t == 4000 for t, _ in groups) and any(t == 6000 for t, _ in groups)
    return {'scope': 'real native AP serial writes with stationary JSON ground fixture; no flight',
            'json_ticks': len(json_ticks), 'samples': len(samples), 'ubx_packets_including_suppressed': packet_count,
            'byte_counts': dict(phases), 'ubx_time_samples': tow, 'ok': True}

def run(build, out, fault):
    out.mkdir(exist_ok=False)
    run_id, epoch = uuid.uuid4().hex, uuid.uuid4().hex
    binary = build / 'build/sitl/bin/arducopter'
    identity = json.loads((build / 'identity.json').read_text())
    assert digest(binary) == identity['binary_sha256']
    params = out / 'ground.parm'
    params.write_text('SIM_GPS1_ENABLE 1\nSIM_GPS1_TYPE 1\nSIM_GPS1_LAG_MS 100\nSIM_GPS1_HZ 5\nSIM_GPS1_BYTELOS 0\nSIM_GPS2_ENABLE 0\nSIM_GPS2_TYPE 0\nGPS1_TYPE 2\nGPS_AUTO_CONFIG 0\nGPS_DRV_OPTIONS 4\nDDS_ENABLE 0\n')
    cmd = [str(binary), '--model', 'JSON:127.0.0.1', '--rate', '1000', '--speedup', '1',
           '--sim-address', '127.0.0.1', '--sim-port-out', '19002', '--sim-port-in', '19003',
           '--rc-in-port', '19004', '--serial0', 'none', '--serial1', 'none', '--serial2', 'none',
           '--defaults', str(params), '--home', '40.1540302,116.2593683,50,0']
    env = dict(os.environ, WKSIM_RUN=run_id, WKSIM_EPOCH=epoch, WKSIM_GNSS_TRACE=str(out / 'native.tsv'))
    manifest = {'command': cmd, 'run_id': run_id, 'epoch': epoch, 'vehicle': 1, 'fault': fault,
                'probe_sha256': digest(Path(__file__).resolve()),
                'plan': {'start_tick': 4000, 'end_tick': 6000, 'tick_us': 1000,
                         'max_delayed_source_age_ms': 500, 'max_tick': 60000},
                'binary_sha256': digest(binary), 'params_sha256': digest(params), 'build_identity': identity,
                'scope': 'stationary truth fixture into REAL native AP; no arming or flight'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    failure = None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, (out / 'process.log').open('x') as log, (out / 'wire.jsonl').open('x') as wire:
        sock.bind(('127.0.0.1', 19002))
        sock.settimeout(0.2)
        child = subprocess.Popen(cmd, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT)
        manifest['pid'] = child.pid
        manifest['proc_stat'] = Path(f'/proc/{child.pid}/stat').read_text()
        manifest['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        manifest['proc_cmdline_hex'] = Path(f'/proc/{child.pid}/cmdline').read_bytes().hex()
        peer = None
        expected = 0
        deadline = time.monotonic() + 90
        try:
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    break
                try:
                    packet, address = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                wire.write(json.dumps({'direction': 'receive', 'hex': packet.hex(), 'peer': address}) + '\n')
                if peer is None:
                    peer = address
                assert address == peer and len(packet) == 40
                magic, rate, frame, *pwm = struct.unpack('<HHI16H', packet)
                assert magic == 18458 and frame == expected, (magic, frame, expected)
                if expected == 8000:
                    break
                tick = expected + 1
                rid, ep = run_id, epoch
                stamp = tick / 1000
                if tick == 1001:
                    if fault == 'run': rid = 'f' * 32
                    if fault == 'epoch': ep = 'f' * 32
                    if fault == 'duplicate': tick -= 1
                    if fault == 'timestamp': stamp -= 0.001
                data = {'wksim': f'{rid}:{ep}:1:{tick}', 'timestamp': stamp,
                        'imu': {'gyro': [0, 0, 0], 'accel_body': [0, 0, -9.80665]},
                        'position': [0, 0, 0], 'velocity': [0, 0, 0], 'quaternion': [1, 0, 0, 0]}
                raw = ('\n' + json.dumps(data, separators=(',', ':'), allow_nan=False) + '\n').encode()
                sock.sendto(raw, peer)
                wire.write(json.dumps({'direction': 'send', 'hex': raw.hex(), 'tick': tick}) + '\n')
                expected += 1
            else:
                raise TimeoutError('90 second ground probe deadline')
        except Exception as exc:
            failure = repr(exc)
        finally:
            requested_stop = child.poll() is None
            if requested_stop:
                child.terminate()
            try:
                code = child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                code = child.wait(timeout=5)
                failure = failure or 'TERM timeout; owned child killed'
    manifest.update(returncode=code, requested_stop=requested_stop, frames_sent=expected, failure=failure)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if failure:
        raise RuntimeError(failure)
    if fault == 'none':
        result = audit(out)
    else:
        reason = {'run': 'foreign_identity', 'epoch': 'foreign_identity', 'duplicate': 'nonconsecutive_tick',
                  'timestamp': 'timestamp_or_lockstep'}[fault]
        assert code == 109 and reason in (out / 'native.tsv').read_text()
        result = {'ok': True, 'expected_failure': reason, 'native_exit': code, 'scope': 'real native rejection; no flight'}
    (out / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    (out / 'hashes.json').write_text(json.dumps({p.name: digest(p) for p in out.iterdir() if p.is_file()}, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'ubx_time_samples'}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--fault', choices=['none', 'run', 'epoch', 'duplicate', 'timestamp'], default='none')
    args = parser.parse_args()
    run(args.build.resolve(), args.out.resolve(), args.fault)
