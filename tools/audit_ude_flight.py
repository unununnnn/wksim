"""Independent UDE equations plus shared native/physical evidence audit.

No online UDE implementation is imported for expected values. Same double
recomputation tolerance (1e-10) and wire tolerance (1e-6) as PID, unchanged
physical budgets. The original C++ float oracle retains its separate #89 budget.
"""
import argparse
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools import audit_pid_flight as shared

PROTOCOL = '4bca3479d61f73d2ab8253191bdc41938904a43877f6b688c0c55e32567c4590'
require, near = shared.require, shared.near


def recompute(config, state, ref, dt, integral, hover):
    """Old observer integral feeds this cycle; moving references retain history."""
    require(0 < dt <= .2 and math.isfinite(dt), 'UDE dt outside frozen contract')
    q = state['attitude_flu_to_enu']
    require(len(q) == 4 and near(math.hypot(*q), 1., 1e-6), 'Nonunit UDE state quaternion')
    for value in (state['position_enu'], state['velocity_enu'], ref['position_enu'],
                  ref['velocity_enu'], ref['acceleration_enu'], integral):
        require(len(value) == 3 and all(type(x) in (int, float) and math.isfinite(x) for x in value),
                'Invalid UDE vector')
    require(math.isfinite(ref['yaw_enu_rad']) and .1 <= hover <= 1, 'Invalid UDE yaw/hover')
    gains = config['ude']; mass = config['model']['mass_kg']; mg = mass*9.8
    pe = [max(-3., min(3., a-b)) for a,b in zip(ref['position_enu'], state['position_enu'])]
    ve = [max(-3., min(3., a-b)) for a,b in zip(ref['velocity_enu'], state['velocity_enu'])]
    nominal = [ref['acceleration_enu'][i]+gains['kp'][i]*pe[i]+gains['kd'][i]*ve[i] for i in range(3)]
    disturbance = [max(-gains['disturbance_limit'][i], min(gains['disturbance_limit'][i],
        -(gains['kp'][i]*integral[i]+gains['kd'][i]*pe[i]+ve[i])/gains['t_ude_s'])) for i in range(3)]
    integ = [integral[i]+pe[i]*dt if abs(pe[i]) < .5 else 0. for i in range(3)]
    acc = [nominal[i]-disturbance[i] for i in range(3)]
    force = [mass*acc[0], mass*acc[1], mass*acc[2]+mg]
    require(force[2] != 0, 'Undefined zero vertical force')
    capped_z = max(.5*mg, min(2*mg, force[2]))
    if capped_z != force[2]:
        force = [f/force[2]*capped_z for f in force]
    cap = force[2]*math.tan(math.radians(gains['tilt_limit_deg']))
    force[:2] = [max(-cap, min(cap, f)) for f in force[:2]]
    w,x,y,z = q; norm = sum(v*v for v in q)
    yaw = math.atan2(2*(w*z+x*y)/norm, 1-2*(y*y+z*z)/norm)
    fx = math.cos(yaw)*force[0]+math.sin(yaw)*force[1]
    fy = -math.sin(yaw)*force[0]+math.cos(yaw)*force[1]
    rpy = [math.atan2(-fy, force[2]), math.atan2(fx, force[2]), ref['yaw_enu_rad']]
    projected = sum(a*b for a,b in zip(force, (2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y))))
    output = dict(acceleration_enu=acc, force_enu_n=force, roll_pitch_yaw_enu_rad=rpy,
        projected_thrust_n=projected, integral=integ, mass_kg=mass, controller='ude',
        nominal_acceleration_enu=nominal, disturbance_acceleration_enu=disturbance)
    require(all(math.isfinite(v) for v in (*acc,*force,*rpy,*integ,*nominal,*disturbance,projected)),
            'Nonfinite UDE expected output')
    return output, max(.1, min(1., projected/(mg/hover)))


def audit(root):
    return shared.audit(root, controller='ude')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.run_dir.resolve()), 'Audit output must be outside sealed run')
    with args.output.open('x', encoding='utf-8') as stream:
        result = audit(args.run_dir)
        result['command'] = [sys.executable, *sys.argv]
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(status=result['status'], output=str(args.output), failure=result.get('failure'))))
    return 0 if result['status'] == 'recorded_evidence_pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
