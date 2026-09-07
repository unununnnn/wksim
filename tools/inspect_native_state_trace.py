"""Explain actual native freshness decisions from opt-in Control observations."""
import argparse
import json
from pathlib import Path

from audit_joint_flight import digest, lines, require


def inspect(root):
    from rclpy.serialization import deserialize_message
    from prometheus_msgs.msg import UAVState
    from px4_msgs.msg import (VehicleStatus,VehicleLocalPosition,VehicleAttitude,SensorGps,EstimatorStatusFlags)
    classes = dict(status=VehicleStatus,position=VehicleLocalPosition,attitude=VehicleAttitude,
                   gps=SensorGps,estimator=EstimatorStatusFlags)
    result = json.loads((root/'result.json').read_text())
    records = list(lines(root/'px4-native-state-trace.jsonl'))
    require(result['native_state_trace_requested'],'No actual trace requested')
    require(all(row['tag']=='DEBUG-wksim-native-state' for row in records),'Wrong trace identity')
    native = [row for row in records if row['kind']=='native_callback' and row['key']=='estimator' and row['accepted']]
    transitions = []
    for row in records:
        if row['kind']!='state_transition' or not row['armed']:
            continue
        require(row['run_id']==result['run_id'] and row['scene_epoch']==result['scene_epoch'], 'Foreign trace')
        public = deserialize_message(bytes.fromhex(row['public_state_cdr_hex']), UAVState)
        require(public.odom_valid==row['odom_valid'] and public.connected==row['connected'], 'Public state trace differs')
        checks = [check for check in row['checks'] if check['keys']==list(classes)]
        if not checks or any(row['sources'][key].get('missing') for key in classes):
            continue
        check = checks[-1]
        require(check['stale_seconds']==2., 'Approved freshness threshold changed')
        values = {key:deserialize_message(bytes.fromhex(row['sources'][key]['cdr_hex']),cls) for key,cls in classes.items()}
        flags = dict(gps_fix=values['gps'].fix_type>=3, xy=values['position'].xy_valid,
            z=values['position'].z_valid, v_xy=values['position'].v_xy_valid, v_z=values['position'].v_z_valid,
            tilt=values['estimator'].cs_tilt_align, yaw=values['estimator'].cs_yaw_align,
            not_dead_reckoning=not values['position'].dead_reckoning, not_failsafe=not values['status'].failsafe)
        expired = [key for key,age in check['ages_s'].items() if age is None or not 0<=age<=2.]
        for key, source in row['sources'].items():
            require(abs(check['evaluated_monotonic_s']-source['received_monotonic_s']-check['ages_s'][key])<1e-8,
                    'Decision age differs from actual accepted receive time')
        estimator = row['sources']['estimator']
        matching = [sample for sample in native if sample['accepted_received_monotonic_s']==estimator['received_monotonic_s']]
        require(matching and matching[-1]['cdr_hex']==estimator['cdr_hex'],'Estimator decision has no actual callback provenance')
        transitions.append(dict(last_public_sequence=row['last_public_sequence'],source_position_us=values['position'].timestamp,
            mode=row['mode'], connected=row['connected'],odom_valid=row['odom_valid'],native_generation=row['native_generation'],
            clock_invalid=row['clock_invalid'], evaluated_monotonic_s=check['evaluated_monotonic_s'],
            actual_received_monotonic_s={key:value['received_monotonic_s'] for key,value in row['sources'].items()},
            ages_s=check['ages_s'],freshness_result=check['result'],expired_sources=expired,native_health_flags=flags,
            estimator_expiry_with_healthy_native_flags=bool(not public.odom_valid and public.connected
                and not check['result'] and expired==['estimator'] and all(flags.values()) and not row['clock_invalid'])))
    task_file = root/'px4-recovery/result.json'
    task = json.loads(task_file.read_text()) if task_file.is_file() else {}
    output = dict(scope=__doc__,status='observed',run_status=result['status'],run_error=result.get('error'),
        result_sha256=digest(root/'result.json'),trace_sha256=digest(root/'px4-native-state-trace.jsonl'),
        inspection_source_sha256=digest(Path(__file__)), transitions=transitions,
        estimator_callbacks=len(native), maximum_estimator_receive_gap_s=max(
            (b['accepted_received_monotonic_s']-a['accepted_received_monotonic_s'] for a,b in zip(native,native[1:])),default=0),
        task_status=task.get('status'),task_error=task.get('error'),
        message_publisher_gid_available=any(sample['receipt']['publisher_gid'] is not None for sample in native),
        publisher_identity_note='This Humble binding exposes timestamps only; discovered GIDs are recorded separately.')
    pacing = [row for row in lines(root/'joint-wire.jsonl') if row['kind']=='diagnostic_land_pacing_started']
    if pacing:
        require(len(pacing)==1 and pacing[0]['minimum_barrier_wall_seconds']==.012,'Unexpected diagnostic pacing')
        after = [sample for sample in native if sample['source_timestamp_us']>=pacing[0]['tick']*1000]
        barriers = [row for row in lines(root/'joint-wire.jsonl') if row['kind']=='barrier' and row['tick']>pacing[0]['tick']]
        output['diagnostic_landing'] = dict(start_tick=pacing[0]['tick'],barriers=len(barriers),
            estimator_callbacks=len(after),
            maximum_estimator_receive_gap_s=max((b['accepted_received_monotonic_s']-a['accepted_received_monotonic_s']
                                                 for a,b in zip(after,after[1:])),default=None),
            estimator_source_delta_us=sorted({b['source_timestamp_us']-a['source_timestamp_us'] for a,b in zip(after,after[1:])}),
            minimum_observed_barrier_gap_s=min((b['wall']-a['wall'] for a,b in zip(barriers,barriers[1:])),default=None),
            achieved_sim_seconds_per_wall_second=(barriers[-1]['tick']-barriers[0]['tick'])/1000/
                (barriers[-1]['wall']-barriers[0]['wall']) if len(barriers)>1 else None)
    (root/'native-state-inspection.json').write_text(json.dumps(output,indent=2)+'\n')
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    print(json.dumps(inspect(args.directory),indent=2))
