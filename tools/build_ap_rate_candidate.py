"""Build an independent ArduCopter SITL rate-output takeover candidate."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.build_identity import source_snapshot,sha
from rate_control_candidate import replace_once

BASE=Path('/root/wksim-ap-clock-stop-OXQqdR')
PARENT_SHA='f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a'
COMMIT='1511f27194f1dcc3728270883047bdf022b3fd53'
INPUTS=('Simulator/firmware/rate_control/ap_adapter.hpp','Simulator/firmware/rate_control/predictive_rate.hpp',
        'Simulator/firmware/rate_control/generated_ap_design.hpp','Simulator/firmware/rate_control/quad-x-ap-design.json',
        'tools/build_ap_rate_candidate.py','tools/design_rate_control.py','Simulator/wksim_runtime/build_identity.py')


def build():
    raw=(BASE/'wksim-build.json').read_bytes()
    if sha(raw)!=PARENT_SHA:raise ValueError('AP parent receipt changed')
    parent=json.loads(raw)
    if source_snapshot(BASE/'src',commit=COMMIT)!=parent['source']:raise ValueError('AP parent source changed')
    root=Path(tempfile.mkdtemp(prefix='wksim-ap-inner-',dir='/root'))
    print(json.dumps({'candidate_root':str(root)}),flush=True)
    subprocess.run(['cp','-a','--reflink=auto',str(BASE/'src'),str(root/'src')],check=True)
    source=root/'src';module=source/'libraries/AC_AttitudeControl'
    for name in INPUTS:
        target=root/'inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/name,target)
    for name in ('ap_adapter.hpp','predictive_rate.hpp','generated_ap_design.hpp'):
        shutil.copyfile(root/'inputs/Simulator/firmware/rate_control'/name,module/name)
    header=module/'AC_AttitudeControl_Multi.h';text=header.read_text()
    text=replace_once(text,'class AC_AttitudeControl_Multi :',
        '#if CONFIG_HAL_BOARD == HAL_BOARD_SITL\n#include "ap_adapter.hpp"\n#endif\n\nclass AC_AttitudeControl_Multi :')
    text=replace_once(text,'protected:',
        'protected:\n#if CONFIG_HAL_BOARD == HAL_BOARD_SITL\n    WksimAPRateAdapter _wksim_rate;\n#endif')
    header.write_text(text)
    cpp=module/'AC_AttitudeControl_Multi.cpp';text=cpp.read_text()
    text=replace_once(text,'    _pd_scale_used = _pd_scale;',
        '#if CONFIG_HAL_BOARD == HAL_BOARD_SITL\n'
        '    if (_wksim_rate.update(_motors, ang_vel_body, gyro_rads, dt, _rate_gyro_time_us)) {\n'
        '        get_rate_roll_pid().set_integrator(0.f);\n'
        '        get_rate_pitch_pid().set_integrator(0.f);\n'
        '        get_rate_yaw_pid().set_integrator(0.f);\n'
        '    }\n#endif\n\n    _pd_scale_used = _pd_scale;')
    cpp.write_text(text)
    defaults=source/'Tools/autotest/default_params/copter.parm'
    defaults.write_text(defaults.read_text()+'\n# Explicit shared rate-experiment conditions\nSCHED_LOOP_RATE 250\n'
        'MOT_THST_EXPO 0.65\nMOT_SPIN_MIN 0.15\nMOT_SPIN_MAX 0.95\nARMING_SKIPCHK 0\n')
    configure=['./waf','configure','--board','sitl','--enable-DDS','--out',str(source/'build')]
    recipe=['./waf','copter','-j4']
    env=dict(os.environ,PATH='/root/wksim-dds-VxM6Ni/src/Micro-XRCE-DDS-Gen/scripts:'+os.environ['PATH'])
    for argv,name in ((configure,'configure.log'),(recipe,'build.log')):
        with (root/name).open('w') as log:subprocess.run(argv,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    binary=source/'build/sitl/bin/arducopter'
    record=dict(schema='wksim.inner-loop-candidate.v1',state='built',family='ardupilot',target='copter_sitl',
        stack='arducopter',candidate_root=str(root),source_root=str(source),upstream_commit=COMMIT,
        parent_manifest_sha256=PARENT_SHA,production_admitted=False,algorithms=['native','pid','lqr','mpc'],
        control_stage='firmware_body_rate',integration='RPY PID+FF output takeover; native PID still computes',
        activity_basis='armed motor spool unlimited; conservative superset of airborne operation',scheduler_hz=250,
        design_file='quad-x-ap-design.json',design_sha256=sha((root/'inputs/Simulator/firmware/rate_control/quad-x-ap-design.json').read_bytes()),
        repository_inputs={name:sha((root/'inputs'/name).read_bytes()) for name in INPUTS},
        configure_argv=configure,build_argv=recipe,source=source_snapshot(source,commit=COMMIT),
        binary=str(binary),binary_sha256=sha(binary.read_bytes()))
    path=root/'candidate.json';path.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'manifest':str(path),'sha256':sha(path.read_bytes())}),flush=True)


def verify(path,checksum):
    path=Path(path);root=path.parent
    if (root.parent!=Path('/root') or not root.name.startswith('wksim-ap-inner-') or path.name!='candidate.json'
            or path.resolve(strict=True)!=path or sha(path.read_bytes())!=checksum):raise ValueError('Invalid AP inner-loop receipt')
    record=json.loads(path.read_text());source=root/'src'
    if (record['schema']!='wksim.inner-loop-candidate.v1' or record['family']!='ardupilot' or record['target']!='copter_sitl'
            or record['source_root']!=str(source) or record['upstream_commit']!=COMMIT
            or record['parent_manifest_sha256']!=PARENT_SHA or record['production_admitted'] is not False
            or sha((BASE/'wksim-build.json').read_bytes())!=PARENT_SHA
            or source_snapshot(source,commit=COMMIT)!=record['source']):raise ValueError('AP candidate identity changed')
    if record['binary']!=str(source/'build/sitl/bin/arducopter') or sha(Path(record['binary']).read_bytes())!=record['binary_sha256']:
        raise ValueError('AP candidate executable changed')
    for name,expected in record['repository_inputs'].items():
        if sha((root/'inputs'/name).read_bytes())!=expected:raise ValueError('AP build input changed: '+name)
    return record


if __name__=='__main__':build()
