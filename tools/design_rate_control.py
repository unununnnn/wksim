"""Generate a reproducible hover-linear LQR and box-constrained MPC design.

PX4's normalized torque is converted with its normalized quad-X allocation
geometry and the retained generated model's local motor force slope. This is
a local engineering model, not a full nonlinear vehicle identification.
"""
import hashlib
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_core.model_parameters import FIXED, SOURCE

DESTINATION = REPO/'Simulator/firmware/rate_control'
DT = .004
HORIZON = 12


def riccati(a,b,q,r):
    p=q.copy()
    for iteration in range(20000):
        k=np.linalg.solve(r+b.T@p@b,b.T@p@a)
        following=q+a.T@p@a-a.T@p@b@k
        if np.max(np.abs(following-p))<1e-11:
            p=following
            k=np.linalg.solve(r+b.T@p@b,b.T@p@a)
            if max(abs(np.linalg.eigvals(a-b@k)))>=1:
                raise ValueError('LQR closed loop is not stable')
            return p,k,iteration+1
        p=following
    raise ValueError('Riccati iteration did not converge')


def design(family='px4'):
    value=lambda name:FIXED[name]['value']
    mass=1.515
    inertia=np.array(value('ModelParam_uavJ')).reshape(3,3).diagonal()
    ct,cm,cr=(value(n) for n in ('ModelParam_rotorCt','ModelParam_rotorCm','ModelParam_motorCr'))
    omega=math.sqrt(mass*9.8/(4*ct))
    force_slope=2*ct*omega*cr
    arm=value('ModelParam_uavR')
    # PX4 normalized roll/pitch mixer magnitudes are 1/sqrt(2), yaw is 1.
    authority=np.array([2*arm*force_slope/inertia[0],2*arm*force_slope/inertia[1],
                        4*cm/ct*force_slope/inertia[2]])
    motor_tau=value('ModelParam_motorT')
    # Native yaw output LPF (2 Hz) remains after the seam. Match its DC gain
    # and first moment with the motor lag; do not remove it to help a result.
    tau=[motor_tau,motor_tau,motor_tau+1/(2*math.pi*2)]
    if family=='arducopter':
        # AP's mixer magnitudes are .5 on each axis, followed by its thrust
        # linearization. These exact parameters are fixed in this candidate.
        spin_min,spin_max,expo=.15,.95,.65
        hover=(omega-value('ModelParam_motorWb'))/cr
        ratio=(hover-spin_min)/(spin_max-spin_min)
        slope=(spin_max-spin_min)/(1-expo+2*expo*ratio)
        authority*=np.array([1/math.sqrt(2),1/math.sqrt(2),.5])*slope
        tau=[motor_tau]*3
    elif family!='px4':raise ValueError('Unsupported firmware design')
    axes=[]
    for i in range(3):
        decay=math.exp(-DT/tau[i])
        a=np.array([[1,tau[i]*(1-decay)],[0,decay]])
        b=np.array([[authority[i]*(DT-tau[i]*(1-decay))],[authority[i]*(1-decay)]])
        q=np.diag([1.,.00001]);r=50. if i<2 else 25.
        terminal,gain,iterations=riccati(a,b,q,r)
        fx=np.vstack([np.linalg.matrix_power(a,k) for k in range(1,HORIZON+1)])
        fu=np.zeros((2*HORIZON,HORIZON));w=np.zeros((2*HORIZON,2*HORIZON))
        for k in range(HORIZON):
            w[2*k:2*k+2,2*k:2*k+2]=terminal if k==HORIZON-1 else q
            for j in range(k+1):fu[2*k:2*k+2,j:j+1]=np.linalg.matrix_power(a,k-j)@b
        h=fu.T@w@fu+r*np.eye(HORIZON)
        f=fu.T@w@fx
        if not np.allclose(np.linalg.solve(h,f)[0],gain[0],atol=1e-9,rtol=1e-9):
            raise ValueError('Unconstrained MPC does not reproduce terminal-cost LQR')
        axes.append(dict(axis=['roll','pitch','yaw'][i],inertia_kg_m2=float(inertia[i]),
            normalized_torque_acceleration=float(authority[i]),lag_s=tau[i],
            a=a.tolist(),b=b.tolist(),q=q.tolist(),r=r,terminal=terminal.tolist(),
            lqr_gain=gain[0].tolist(),hessian=h.tolist(),linear=f.tolist(),
            closed_loop_poles=[dict(real=float(x.real),imag=float(x.imag)) for x in np.linalg.eigvals(a-b@gain)],
            riccati_iterations=iterations,torque_limit=.3))
    return dict(schema='wksim.quad-x-rate-design.v1',control_stage='firmware_body_rate',
        vehicle_class='multicopter',model_profile='quad_x',model_source=SOURCE,
        mass_kg=mass,dt_s=DT,horizon=HORIZON,state=['rate_error_rad_s','angular_acceleration_rad_s2'],
        output='PX4 normalized torque, before retained yaw LPF and battery scale; not N*m',
        hover_motor_speed_rad_s=omega,motor_force_slope_n_per_command=force_slope,
        solver=dict(method='box coordinate descent',max_sweeps=48,kkt_tolerance=1e-5,deadline_ns=500000),
        axes=axes,scope='Local hover linearization. No optimality or stability claim for the complete nonlinear flight envelope.')


def cpp_array(value):
    if isinstance(value,list):return '{'+','.join(cpp_array(v) for v in value)+'}'
    return format(value,'.17g')


def generate(family='px4'):
    record=design(family)
    if family=='arducopter':
        record.update(family=family,output='ArduCopter normalized RPY mixer input, replacing native PID+FF output; not N*m',
            scheduler_hz=250,thrust_linearization=dict(spin_min=.15,spin_max=.95,expo=.65),
            angular_acceleration_estimator='gyro finite difference with 25Hz first-order lowpass')
    raw=(json.dumps(record,sort_keys=True,indent=2)+'\n').encode()
    checksum=hashlib.sha256(raw).hexdigest()
    text='// Generated by tools/design_rate_control.py; SPDX-License-Identifier: Apache-2.0\n#pragma once\nnamespace wksim_rate {\n'
    text+=f'constexpr unsigned horizon = {HORIZON};\nconstexpr double design_dt = {DT};\n'
    text+=f'constexpr const char *design_sha256 = "{checksum}";\n'
    for name,shape,key in [('gain','[3][2]','lqr_gain'),('hessian',f'[3][{HORIZON}][{HORIZON}]','hessian'),
                           ('linear',f'[3][{HORIZON}][2]','linear')]:
        text+=f'constexpr double {name}{shape} = '+cpp_array([a[key] for a in record['axes']])+';\n'
    text+='constexpr double torque_limit = 0.3;\n}\n'
    (DESTINATION/('quad-x-ap-design.json' if family=='arducopter' else 'quad-x-design.json')).write_bytes(raw)
    (DESTINATION/('generated_ap_design.hpp' if family=='arducopter' else 'generated_design.hpp')).write_text(text)
    print(json.dumps({'design_sha256':checksum,'gains':[a['lqr_gain'] for a in record['axes']]}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--family',choices=['px4','arducopter'],default='px4')
    generate(parser.parse_args().family)
