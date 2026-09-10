"""Native home mutation and no-replay gate, called after the raw flight audit."""
import json
import struct
from pymavlink.dialects.v20 import common as mavlink


def require(value, reason):
    if not value: raise ValueError(reason)


def audit_home(root, *, result, requests, events, targets, states, setups, phases):
    parsers = {key: mavlink.MAVLink(None) for key in ('in', 'out')}
    mutations, acks = [], []
    with (root/'home-operator-wire.jsonl').open() as wire:
        for line in wire:
            require(line.endswith('\n'), 'Truncated operator wire record')
            row = json.loads(line)
            require(row['run_id'] == result['run_id'] and row['peer'][0] == '127.0.0.1', 'Foreign operator wire identity')
            for message in parsers[row['direction']].parse_buffer(bytes.fromhex(row['raw_hex'])) or []:
                if row['direction'] == 'out':
                    require(message.get_type() == 'COMMAND_INT' and message.command == 179,
                            'Home actor issued an unrelated command')
                    require((message.get_srcSystem(), message.get_srcComponent()) == (246, 190), 'Wrong operator command source')
                    require(message.target_system == (22 if result['stack'] == 'px4' else 241)
                        and message.target_component == 1 and message.frame == 0 and message.param1 == 0,
                        'Wrong native home command/frame')
                    mutations.append((row, message))
                elif message.get_type() == 'COMMAND_ACK' and message.command == 179:
                    require(message.result == 0 and message.get_srcSystem() == (22 if result['stack'] == 'px4' else 241), 'Home edit not natively accepted')
                    acks.append((row, message))
    require(len(mutations) == 1 and acks, 'Missing single native home request/ACK')
    sent, command = mutations[0]
    before = phases['home_change_requested']['original_binding']
    after = phases['changed_home_observed']['binding']
    home0, home1 = before['home'], after['home']
    require(command.x == int(home0['latitude_deg']*1e7) and command.y == int(home0['longitude_deg']*1e7), 'Home request changed horizontal objective')
    require(abs(command.z-(home0['alt_amsl_m']+.1)) < .00001, 'Home request changed frozen altitude delta')
    # Pinned GCS_Common::location_from_command_t calls Location::set_alt_m:
    # its float multiplication by 100 rounds before the int32 conversion.
    # AP's DDS adapter instead explicitly multiplies in double; do not conflate
    # these two native interfaces or change their flight/quantization budgets.
    expected_alt = (float(command.z) if result['stack'] == 'px4' else
                    int(struct.unpack('<f', struct.pack('<f', command.z*100))[0])/100)
    require(home1['latitude_deg'] == command.x/1e7 and home1['longitude_deg'] == command.y/1e7
        and home1['alt_amsl_m'] == expected_alt, 'New snapshot differs from native home command')
    require(home1['home_generation'] > home0['home_generation'] and home1['identity'] == home0['identity'], 'Wrong home/session generation')
    withdrew = [e for e in events if e['event'] == 'control_revoked'
        and e['emitted_monotonic_ns'] >= sent['monotonic_ns']
        and e.get('reason') in ('global_home_changed', 'native_clock_or_origin_reset')]
    require(withdrew, 'No actual home-triggered withdrawal')
    withdrawal = min(withdrew, key=lambda e: e['emitted_monotonic_ns'])
    require(withdrawal['emitted_monotonic_ns'] <= phases['changed_home_observed']['monotonic_ns'], 'Late home withdrawal')
    quiet_end = phases['home_change_no_automatic_reacquisition']['monotonic_ns']
    require(quiet_end-phases['changed_home_observed']['monotonic_ns'] >= 1_000_000_000, 'No full quiet interval')
    quiet_end_unix = withdrawal['emitted_unix_ns']+quiet_end-withdrawal['emitted_monotonic_ns']
    require(not any(withdrawal['emitted_unix_ns'] <= r['source_timestamp'] <= quiet_end_unix for r in targets), 'Native setpoint replay after home withdrawal')
    observed = [r for r in states if withdrawal['emitted_monotonic_ns']+100_000_000 <= r['monotonic_ns'] <= quiet_end]
    require(observed and all(r['message']['control']['control_state'] == 0 for r in observed), 'Automatic public control reacquisition')
    takeover = [e for e in events if e['event'] == 'setup_completed' and e.get('control_state') == 'COMMAND_CONTROL'
        and e['emitted_monotonic_ns'] > quiet_end]
    require(takeover, 'No explicit new task takeover')
    raw_takeover = [r for r in setups if r['message']['request_id'] == takeover[0]['request_id']]
    require(len(raw_takeover) == 1 and raw_takeover[0]['message']['run_id'] == result['run_id']
        and raw_takeover[0]['message']['control_epoch'] == takeover[0]['control_epoch']
        and raw_takeover[0]['message']['setup']['control_state'] == 'COMMAND_CONTROL'
        and raw_takeover[0]['source_timestamp'] > quiet_end_unix, 'No raw explicit takeover request')
    require(any(r['message']['setup']['px4_mode'] == 'AUTO.LOITER'
        and quiet_end_unix < r['source_timestamp'] < raw_takeover[0]['source_timestamp'] for r in setups),
        'No raw explicit native recovery hold')
    old = [e for e in events if e['event'] == 'global_command_rejected' and e.get('reason') == 'home_changed'
        and e['emitted_monotonic_ns'] >= takeover[0]['emitted_monotonic_ns']]
    require(len(old) == 1 and old[0]['request_id'] in requests, 'No raw old-home request rejection')
    retired = requests[old[0]['request_id']]['command']
    require(retired['home_generation'] == home0['home_generation'], 'Old-home test did not reuse retired home')
    require(not any(e['event'] in ('global_command_accepted', 'global_native_published')
        and e['request_id'] == old[0]['request_id'] for e in events), 'Retired home command escaped rejection')
    fresh = [e for e in events if e['event'] == 'global_command_accepted'
        and e['request_id'] > old[0]['request_id'] and e['resolved']['original']['height_reference'] == 'amsl']
    require(fresh and fresh[0]['request_id'] in requests, 'No explicit new-home global request')
    restored = fresh[0]['resolved']['original']
    frozen = phases['global_target_frozen']
    require(restored['home_generation'] == home1['home_generation']
        and restored['latitude_deg'] == frozen['route']['latitude_deg']
        and restored['longitude_deg'] == frozen['route']['longitude_deg']
        and restored['height_m'] == home0['alt_amsl_m']+frozen['route']['height_relative_m'], 'Recovery silently changed global objective')
    return dict(native_command=179, before=home0, after=home1, quiet_seconds=(quiet_end-phases['changed_home_observed']['monotonic_ns'])/1e9,
        old_request_id=old[0]['request_id'], new_request_id=fresh[0]['request_id'], native_acks=len(acks))
