"""Read-only joint Actor correlation; no physics or native flight commands."""
import math

from Simulator.wksim_core.joint_state_stream import validate
from .bridge import actor_errors


def joint_actor_errors(packet,ack):
    original={key:value for key,value in packet.items() if key not in
              ('display_clock','display_wall_time_s','transport_age_bound_s')}
    validate(original,packet['run_id'],packet['instance_id'],now=packet['source_wall_time_s'])
    if (not isinstance(ack,dict) or ack.get('version')!=3 or ack.get('kind')!='joint_actor'
            or any(ack.get(key)!=packet[key] for key in
                   ('run_id','instance_id','epoch','generation','sequence','step','sim_time_ns'))
            or type(ack.get('selected_vehicle_id')) is not int or ack['selected_vehicle_id'] not in (1,2)):
        raise ValueError('Uncorrelated joint Actor identity')
    actual=ack.get('vehicles')
    if not isinstance(actual,list) or len(actual)!=len(packet['vehicles']):
        raise ValueError('Joint Actor count differs')
    by_id={}
    for value in actual:
        if not isinstance(value,dict) or type(value.get('vehicle_id')) is not int or value['vehicle_id'] in by_id:
            raise ValueError('Duplicate or invalid Actor identity')
        by_id[value['vehicle_id']]=value
    if set(by_id)!={v['vehicle_id'] for v in packet['vehicles']}:
        raise ValueError('Joint Actor identities differ')
    errors={}
    for value in packet['vehicles']:
        actual=by_id[value['vehicle_id']]
        stamp=packet['sim_time_ns']/1e9
        common=dict(run_id=packet['run_id'],sequence=packet['sequence'],sim_time_s=stamp)
        errors[value['vehicle_id']]=actor_errors(dict(value,**common),dict(actual,**common))
        for field in ('rotor_rpm','rotor_yaw_deg'):
            numbers=actual.get(field)
            if not isinstance(numbers,list) or len(numbers)!=4 or any(
                    type(n) not in (int,float) or not math.isfinite(n) for n in numbers):
                raise ValueError('Missing actual rotor readback')
        if actual['rotor_rpm']!=value['rotor_rpm']:raise ValueError('Applied rotor RPM differs')
    observed=ack.get('observed_vehicles')
    if (not isinstance(observed,list) or len(observed)!=2
            or {v.get('vehicle_id') for v in observed}!={1,2}
            or any(type(v.get('step')) is not int or not -1<=v['step']<=packet['step']
                   or type(v.get('stale')) is not bool or type(v.get('visible')) is not bool for v in observed)):
        raise ValueError('Invalid complete Actor observation')
    camera=ack.get('camera_position_cm')
    if not isinstance(camera,list) or len(camera)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in camera):
        raise ValueError('Invalid actual camera position')
    return errors
