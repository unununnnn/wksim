"""Independent NE equations plus the shared raw flight audit."""

import argparse
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools import audit_pid_flight as shared


PROTOCOL = '3b09761ad60976aa971f43e81edc0de9bb4ede7065a10b5d512c57c22a478e18'
require, near = shared.require, shared.near


def _vector(value, name, size=3):
    require(isinstance(value, (list, tuple)) and len(value) == size
            and all(type(x) in (int, float) and math.isfinite(x) for x in value),
            'Invalid NE '+name)
    return list(value)


def recompute(config, state, ref, dt, memory, hover):
    """Recompute the fixed NE filters and force from the previous memory."""
    require(0 < dt <= .2 and math.isfinite(dt), 'NE dt outside frozen contract')
    q = _vector(state['attitude_flu_to_enu'], 'quaternion', 4)
    require(near(math.hypot(*q), 1., 1e-6), 'Nonunit NE state quaternion')
    position = _vector(state['position_enu'], 'position')
    velocity = _vector(state['velocity_enu'], 'velocity')
    ref_position = _vector(ref['position_enu'], 'reference position')
    ref_velocity = _vector(ref['velocity_enu'], 'reference velocity')
    ref_acceleration = _vector(ref['acceleration_enu'], 'reference acceleration')
    require(math.isfinite(ref['yaw_enu_rad']) and .1 <= hover <= .8, 'Invalid NE yaw/hover')
    expected_memory = {'integral', 'velocity_integral', 'lpf', 'hpf', 'hpf_input', 'llf', 'llf_input',
                       'initial_position_enu'}
    require(isinstance(memory, dict) and set(memory) == expected_memory, 'NE memory identity differs')
    old = {name: _vector(memory[name], name) for name in expected_memory if name != 'initial_position_enu'}
    initial = _vector(memory['initial_position_enu'], 'initial position')
    gains = config['ne']; mass = config['model']['mass_kg']; mg = mass*9.8
    t = gains['t_ne_s']; denom = t + dt
    pe = [a-b for a, b in zip(ref_position, position)]
    ve = [a-b for a, b in zip(ref_velocity, velocity)]
    hp_input = [a-b for a, b in zip(initial, position)]
    lpf = [t/denom*old['lpf'][i] + dt/denom*velocity[i] for i in range(3)]
    hpf = [(t*old['hpf'][i] + hp_input[i] - old['hpf_input'][i])/denom for i in range(3)]
    noise = [lpf[i]+hpf[i] for i in range(3)]
    nominal = [ref_acceleration[i] + gains['kp'][i]*pe[i] + gains['kd'][i]*(ve[i]+noise[i]) for i in range(3)]
    velocity_integral = [old['velocity_integral'][i] + velocity[i]*dt for i in range(3)]
    llf_input = [velocity_integral[i]-position[i]+initial[i] for i in range(3)]
    llf = [(t*old['llf'][i] + llf_input[i] - old['llf_input'][i]
            + dt*gains['kd'][i]*llf_input[i])/denom for i in range(3)]
    raw_disturbance = [(velocity[i]-old['integral'][i])/gains['t_ude_s'] for i in range(3)]
    integral = [old['integral'][i] + (ref_acceleration[i] + gains['kp'][i]*pe[i]
                                      + gains['kd'][i]*ve[i])*dt if abs(pe[i]) < 100 else 0.
                for i in range(3)]
    for value in (*pe, *ve, *hp_input, *lpf, *hpf, *noise, *nominal, *velocity_integral,
                  *llf_input, *llf, *raw_disturbance, *integral):
        require(math.isfinite(value), 'Nonfinite NE intermediate')
    disturbance = [max(-gains['disturbance_limit'][i], min(gains['disturbance_limit'][i], raw_disturbance[i]))
                   for i in range(3)]
    acceleration = [nominal[i]-disturbance[i] for i in range(3)]
    force = [mass*acceleration[0], mass*acceleration[1], mass*acceleration[2]+mg]
    require(force[2] != 0 and all(math.isfinite(v) for v in force), 'Undefined NE vertical force')
    target = max(.5*mg, min(2*mg, force[2]))
    if target != force[2]:
        force = [v/force[2]*target for v in force]
    tilt = math.tan(math.radians(gains['tilt_limit_deg']))
    for i in range(2):
        force[i] = max(-force[2]*tilt, min(force[2]*tilt, force[i]))
    w, x, y, z = q; norm = sum(v*v for v in q)
    yaw = math.atan2(2*(w*z+x*y)/norm, 1-2*(y*y+z*z)/norm)
    c, s = math.cos(yaw), math.sin(yaw)
    rpy = [math.atan2(s*force[0]-c*force[1], force[2]),
           math.atan2(c*force[0]+s*force[1], force[2]), ref['yaw_enu_rad']]
    body_z = (2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y))
    projected = sum(a*b for a, b in zip(force, body_z))
    output_memory = dict(integral=integral, velocity_integral=velocity_integral, lpf=lpf, hpf=hpf,
                         hpf_input=hp_input, llf=llf, llf_input=llf_input)
    output = dict(acceleration_enu=acceleration, force_enu_n=force,
                  roll_pitch_yaw_enu_rad=rpy, projected_thrust_n=projected, mass_kg=mass,
                  noise_estimator=noise, nominal_acceleration=nominal,
                  disturbance_estimate=disturbance, memory=output_memory, controller='ne',
                  _initial_position_enu=initial)
    require(all(math.isfinite(v) for v in (*acceleration, *force, *rpy, *noise, *nominal,
                                           *disturbance, *integral, projected)),
            'Nonfinite NE output')
    return output, max(.1, min(1., projected/(mg/hover)))


def audit(root):
    return shared.audit(root, controller='ne')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.run_dir.resolve()),
            'Audit output must be outside sealed run')
    with args.output.open('x', encoding='utf-8') as stream:
        result = audit(args.run_dir)
        result['command'] = [sys.executable, *sys.argv]
        import json
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], output=str(args.output), failure=result.get('failure'))))
    return 0 if result['status'] == 'recorded_evidence_pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
