"""Check pinned native/model resources in their baseline overlays, then RC install."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime import joint_profile
from Simulator.wksim_runtime.config import validate_config
from tools.joint_control_candidate import check


def admit(stack, run_id, manifest, checksum):
    profile = joint_profile.select_profile('joint_quad_dds_v1')
    environment = dict(PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                       HOME='/root', LANG='C.UTF-8', PYTHONDONTWRITEBYTECODE='1')
    script = 'set -e\n'+''.join('source '+shlex.quote(p)+'\n' for p in profile['setup_files'])
    script += 'exec '+shlex.join(['/usr/bin/python3', '-B', str(Path(__file__).resolve()), '--baseline', stack])
    completed = subprocess.run(['bash', '--noprofile', '--norc', '-c', script], cwd=REPO,
        env=environment, text=True, capture_output=True, timeout=300)
    if completed.returncode:
        raise ValueError('Baseline admission failed: '+completed.stderr[-3000:]+completed.stdout[-3000:])
    baseline = json.loads(completed.stdout)
    if not baseline['ok']:
        raise ValueError('Baseline resource rejection: '+str(baseline['reasons']))
    control = check(manifest, checksum)
    config = validate_config(dict(schema_version=1, run_id=run_id, vehicle_id=1, stack=stack,
        model_profile='quad_x', communication='native_dds', control_protocol='session_v1',
        capabilities=['native_position_mission'], dds_workspace=profile['dds_workspace'],
        prometheus_workspace=control['root'], px4_root=str(Path(profile['manifests']['px4']['path']).parent/'src'),
        model_library=profile['model_library'], **(
            dict(ap_candidate=str(Path(profile['manifests']['ap']['path']).parent)) if stack=='arducopter' else {})))
    return dict(ok=True, config=config, library=profile['model_library'], baseline=baseline,
        control=control, control_manifest=manifest, control_sha256=checksum,
        setup_files=profile['setup_files'][:-1]+[control['root']+'/install/local_setup.bash'])


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--baseline':
        raise SystemExit('Use --baseline px4|arducopter')
    print(json.dumps(joint_profile.check_resources(joint_profile.select_profile('joint_quad_dds_v1'),
                                                 stacks=(sys.argv[2],))))
