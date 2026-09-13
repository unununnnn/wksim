"""Independent raw CDR/physics audit of frozen basic-v1 and home-change-v2 cases.

Only v2 also requires native home mutation, no replay and explicit recovery.
These experimental flight gates do not promote the default production profile.
"""
from collections import defaultdict
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

PROFILE_SHA = 'c75dc2a1ee8ed4266ff211f8ad0d435009d844ddd67ee63367237b2d5e574a5a'
HOME_PROFILE_SHA = '097f5430a7a7114d000d40b03d37f5c6d27fa027c42ccd2a055a40211be00548'


def require(value, reason):
    if not value: raise ValueError(reason)


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    with Path(path).open() as stream:
        for line in stream:
            require(line.endswith('\n'), 'Incomplete raw record')
            yield json.loads(line)


def projection(origin, latitude, longitude):
    """Independent pinned spherical formula, north/east in metres."""
    p0, p = map(math.radians, (origin['latitude_deg'], latitude))
    dl = math.radians(longitude-origin['longitude_deg'])
    c = math.acos(max(-1., min(1., math.sin(p0)*math.sin(p)+math.cos(p0)*math.cos(p)*math.cos(dl))))
    k = 1. if c == 0 else c/math.sin(c)
    return (k*6371000*(math.cos(p0)*math.sin(p)-math.sin(p0)*math.cos(p)*math.cos(dl)),
            k*6371000*math.cos(p)*math.sin(dl))


def audit(root):
    root = Path(root)
    result = json.loads((root/'result.json').read_text())
    require(result['status'] == 'observed' and result['safe_landing'] and result['children_reaped']
        and not result['cleanup_errors'] and result['source_unchanged'] and result['candidate_unchanged'],
        'Run, identity or cleanup incomplete')
    require(digest(root/'global-profile.json') in (PROFILE_SHA, HOME_PROFILE_SHA), 'Frozen global profile changed')
    profile = json.loads((root/'global-profile.json').read_text())
    for name, checksum in result['source_sha256'].items():
        require(digest(root/'run-source'/name) == checksum, 'Archived source differs: '+name)
    proof = json.loads((root/'datum-proof.json').read_text())
    require(proof['run_id'] == result['run_id'] and proof['stack'] == result['stack']
        and proof['datum'] == 'amsl' and proof['scene_origin']['id'] == result['scene_epoch'], 'Datum identity mismatch')
    require(proof['native_binary']['sha256'] == result['launched_binary_sha256'], 'Datum firmware mismatch')
    require(digest(root/'datum-proof.json') == result['config']['global_reference']['proof_sha256'], 'Datum proof changed')
    scene = proof['scene_origin']
    launch = json.loads((root/'datum-native-launch.json').read_text())
    if result['stack'] == 'arducopter':
        lat, lon, alt, _ = map(float, launch['fc'][launch['fc'].index('--home')+1].split(','))
    else:
        require((root/'datum-model-origin.json').is_file(), 'Configured model origin evidence missing; sensor GPS is not truth origin')
        record = json.loads((root/'datum-model-origin.json').read_text())
        require(record['library_sha256'] == result['admission']['baseline']['identities']['model']['library_sha256']
            and record['probe_sha256'] == digest(root/'model-origin-probe'), 'Configured origin probe/library identity mismatch')
        require(proof['sources'][str(Path(result['run_dir'])/'datum-model-origin.json')] == digest(root/'datum-model-origin.json'),
                'Configured origin record differs from bound proof')
        origin = record['origin']
        require(origin['alt_amsl_m'] == -origin['env_altitude_parameter_m'], 'Configured vertical origin sign differs')
        lat, lon, alt = origin['latitude_deg'], origin['longitude_deg'], origin['alt_amsl_m']
    require((lat, lon, alt) == (scene['latitude_deg'], scene['longitude_deg'], scene['alt_amsl_m']), 'Scene datum differs from native input')

    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rclpy.serialization import deserialize_message
    requests, events, targets, states, observations = {}, [], [], [], defaultdict(list)
    original_native = set()
    setups = []
    dds_count = 0
    for row in rows(root/'rc-dds.jsonl'):
        require(row['type'].split('/')[0] in ('std_msgs', 'prometheus_msgs', 'wksim_msgs', 'px4_msgs', 'ardupilot_msgs'), 'Unexpected DDS type')
        decoded = message_to_ordereddict(deserialize_message(bytes.fromhex(row['cdr_hex']), get_message(row['type'])))
        require(json.dumps(decoded, sort_keys=True) == json.dumps(row['message'], sort_keys=True), 'Raw DDS differs from decoded record')
        dds_count += 1
        if row['type'].split('/')[0] in ('px4_msgs', 'ardupilot_msgs'):
            original_native.add((row['type'], row['cdr_hex'], row['publisher_gid']))
        if row['topic'].endswith('/v2/global_command'):
            request = json.loads(decoded['data'])
            require(request['run_id'] == result['run_id'], 'Foreign global run')
            require(request['request_id'] not in requests, 'Duplicate global request')
            requests[request['request_id']] = request
        elif row['topic'].endswith('/text_info'):
            event = json.loads(decoded['message'])
            require(event['run_id'] == result['run_id'], 'Foreign event run')
            events.append(event)
            if event['event'] == 'global_native_observation':
                cls = ('ardupilot_msgs/msg/WksimState' if result['stack'] == 'arducopter' else
                    {'home': 'px4_msgs/msg/HomePosition', 'global': 'px4_msgs/msg/VehicleGlobalPosition',
                     'local': 'px4_msgs/msg/VehicleLocalPosition'}[event['source']])
                raw = message_to_ordereddict(deserialize_message(bytes.fromhex(event['cdr_hex']), get_message(cls)))
                if 'message' in event:
                    require(raw == event['message'], 'Control native observation differs from original CDR')
                observations[event['source'], event['source_timestamp']].append(dict(event, message=raw, type=cls))
        elif row['topic'].endswith('/v2/state'):
            states.append(row)
        elif row['topic'].endswith('/v2/setup'):
            setups.append(row)
        elif '/in/trajectory_setpoint' in row['topic'] or row['topic'] == '/ap/cmd_gps_pose':
            targets.append(row)
    accepted = {e['request_id']: e for e in events if e['event'] == 'global_command_accepted'}
    published = [e for e in events if e['event'] == 'global_native_published']
    require(accepted and published and targets and observations, 'Missing global raw chain')
    require({'home_relative', 'amsl'} <= {e['resolved']['original']['height_reference'] for e in accepted.values()}, 'Both explicit datums not exercised')
    epochs = {e['control_epoch'] for e in accepted.values()}
    require(len(epochs) == 1, 'Global control epoch changed')
    wire_checks = 0
    for event in published:
        request = requests.get(event['request_id'])
        require(request is not None and event['request_id'] in accepted, 'Publication without raw accepted command')
        target = event['resolved']; command = target['original']; home = target['home']; origin = target['origin']
        require(command == request['command'], 'Published original differs from raw command')
        identity = command['identity']
        require(identity['run_id'] == result['run_id'] and identity['control_epoch'] == int(event['control_epoch'], 16)
            and identity['scene_origin_id'] == result['scene_epoch'], 'Published identity mismatch')
        require(command['issued_monotonic'] <= target['validated_monotonic'] <= command['expires_monotonic']
            and 0 < command['expires_monotonic']-command['issued_monotonic'] <= 2., 'Expired publication')
        for sample in (home, origin):
            require(0 <= target['validated_monotonic']-sample['received_monotonic'] <= 2., 'Stale native publication')
        candidates = observations.get(('home' if result['stack'] == 'px4' else 'local', home['source_timestamp']), [])
        if result['stack'] == 'px4':
            candidates = [r for r in candidates if r['message']['update_count'] == home['update_count']]
        else:
            candidates = [r for r in candidates if [r['message'][k] for k in (
                'home_latitude_e7', 'home_longitude_e7', 'home_altitude_cm')] == home['ap_raw']]
        require(candidates, 'Missing original home sample')
        native = candidates[-1]
        require((native['type'], native['cdr_hex'], native['publisher_gid']) in original_native,
                'Home observation lacks independently captured native CDR/GID')
        message = native['message']
        actual_home = ((message['lat'], message['lon'], message['alt']) if result['stack'] == 'px4' else
                       (message['home_latitude_e7']/1e7, message['home_longitude_e7']/1e7, message['home_altitude_cm']/100))
        require(actual_home == (home['latitude_deg'], home['longitude_deg'], home['alt_amsl_m']), 'Synthetic or wrong home')
        relative = command['height_m'] if command['height_reference'] == 'home_relative' else command['height_m']-actual_home[2]
        require(abs(relative) <= 100 and math.hypot(*projection(home, command['latitude_deg'], command['longitude_deg'])) <= 100, 'Global fence violated')
        candidates = [r['message'] for r in targets if abs(r['source_timestamp']-event['emitted_unix_ns']) < 20_000_000]
        if result['stack'] == 'px4':
            n, e = projection(origin, command['latitude_deg'], command['longitude_deg'])
            expected = (n, e, origin['alt_amsl_m']-(actual_home[2]+relative))
            matches = [m for m in candidates if max(abs(a-b) for a, b in zip(m['position'], expected)) <= .001
                and all(math.isnan(v) for v in m['velocity'])]
        else:
            matches = [m for m in candidates if m['coordinate_frame'] == 6 and m['type_mask'] == 0x9F8
                and m['header']['frame_id'] == 'map' and m['latitude'] == command['latitude_deg']
                and m['longitude'] == command['longitude_deg'] and abs(m['altitude']-relative) < .0001]
        require(matches, 'No matching actual native output for global publication')
        wire_checks += 1
    rejected = [e for e in events if e['event'] == 'global_command_rejected' and e['reason'] == 'horizontal_range']
    require(rejected and all(e['request_id'] in requests and e['request_id'] not in accepted for e in rejected), 'Missing out-of-fence rejection')
    require(all(e['request_id'] not in {r['request_id'] for r in rejected} for e in published), 'Rejected request published')
    phases = {r['phase']: r for r in result['task']['global_flight']['phases']}
    frozen = phases['global_target_frozen']
    route = frozen['route']; home = frozen['binding']['home']
    if result['stack'] == 'px4':
        n, e = projection(scene, route['latitude_deg'], route['longitude_deg'])
    else:
        n = (route['latitude_deg']-scene['latitude_deg'])*1e7*.011131884502145034
        e = (route['longitude_deg']-scene['longitude_deg'])*1e7*.011131884502145034*math.cos(math.radians((route['latitude_deg']+scene['latitude_deg'])/2))
    expected = (e, n, home['alt_amsl_m']+route['height_relative_m']-scene['alt_amsl_m'])
    hold_end = round(phases['global_target_held']['truth']['time']*1000)
    initial_end = round(phases['initial_five_second_hold']['truth']['time']*1000)
    restored_end = (round(phases['home_changed_target_held']['truth']['time']*1000)
                    if 'home_change' in profile else None)
    ticks = stable = initial_stable = restored_stable = 0
    maximum_tilt = 0.
    terminal = None
    last = None
    previous_packet, decoded_input = None, None
    for row in rows(root/'physics-1ms.jsonl'):
        if row['kind'] == 'start':
            require(row['run_id'] == result['run_id'] and row['scene_epoch'] == result['scene_epoch'], 'Physical identity differs')
            continue
        if row['kind'] == 'end': terminal = row; continue
        ticks += 1
        require(row['tick'] == ticks and terminal is None, 'Physical tick discontinuity')
        output = row['output120']; last = output
        packet = row['raw_actuator_packet']
        if packet is None:
            require(result['stack'] == 'px4' and row['input16'] == [0.]*16, 'Missing actuator packet after bootstrap')
            require(previous_packet is None, 'Actuator source disappeared')
        else:
            if packet['packet_hex'] != previous_packet:
                raw = bytes.fromhex(packet['packet_hex'])
                if result['stack'] == 'arducopter':
                    magic, rate, frame, *pwm = struct.unpack('<HHI16H', raw)
                    require(magic == 18458 and rate > 0 and all(v == 0 or 1000 <= v <= 2000 for v in pwm[:4]), 'Invalid original AP actuator packet')
                    decoded_input = [max(0, v-1000)/1000 for v in pwm[:4]]+[0.]*12
                else:
                    from pymavlink.dialects.v20 import common
                    messages = common.MAVLink(None).parse_buffer(raw)
                    require(messages and len(messages) == 1 and messages[0].get_type() == 'HIL_ACTUATOR_CONTROLS', 'Invalid original PX4 actuator packet')
                    msg = messages[0]
                    decoded_input = list(msg.controls[:4])+[0.]*12 if msg.mode & 128 else [0.]*16
                previous_packet = packet['packet_hex']
            require(row['input16'] == decoded_input == packet['decoded_input16'], 'Applied physical input differs from native packet')
        require(len(output) == 120 and all(math.isfinite(v) for v in output), 'Invalid physical state')
        require(abs(output[2]-ticks*.001) < 1e-8, 'Physical time drift')
        position, velocity = (output[7], output[6], -output[8]), output[3:6]
        tilt = max(abs(output[9]), abs(output[10]))
        maximum_tilt = max(maximum_tilt, tilt)
        require(tilt <= profile['maximum_axis_tilt_rad'], 'Physical tilt budget exceeded')
        if initial_end-5000 < ticks <= initial_end:
            require(position[2] >= 2.5 and abs(position[2]-3) <= .6, 'Initial physical hold failed')
            initial_stable += 1
        if hold_end-2000 < ticks <= hold_end:
            require(math.dist(position, expected) <= .5 and math.hypot(*velocity) <= .5, 'Global physical target hold failed')
            stable += 1
        if restored_end is not None and restored_end-2000 < ticks <= restored_end:
            require(math.dist(position, expected) <= .5 and math.hypot(*velocity) <= .5,
                    'Restored global physical target hold failed')
            restored_stable += 1
    require(terminal and terminal['ticks'] == ticks and stable == 2000 and initial_stable == 5000, 'Physical terminal/hold incomplete')
    require(last is not None and abs(last[8]) <= .3 and states and not states[-1]['message']['state']['armed'], 'Physical/public landed state absent')
    home_evidence = None
    if 'home_change' in profile:
        require(restored_stable == 2000, 'Restored physical hold incomplete')
        from tools.audit_global_home_flight import audit_home
        home_evidence = audit_home(root, result=result, requests=requests, events=events,
            targets=targets, states=states, setups=setups, phases=phases)
    return dict(ok=True, scope=('global flight, explicit datums, native home change and new-request recovery'
        if home_evidence else 'basic global flight and explicit datums; home-change scenario still required'),
        run_id=result['run_id'], stack=result['stack'], control_epoch=next(iter(epochs)),
        physical_ticks=ticks, raw_dds_records=dds_count, global_publications=wire_checks,
        maximum_axis_tilt_rad=maximum_tilt, physical_target_enu_m=expected,
        home_change=home_evidence,
        files={p.name: digest(p) for p in root.iterdir() if p.is_file()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try: result = audit(args.root)
    except Exception as error: result = dict(ok=False, error=f'{type(error).__name__}: {error}')
    with args.output.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(result))
    raise SystemExit(0 if result['ok'] else 1)
