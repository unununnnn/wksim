"""Read-only source/issue audit; stdout is the evidence, not a flight test."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = '5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce'
BASE = 'Modules/ego_planner_swarm/'
paths = [BASE + p for p in [
    'plan_manage/src/ego_replan_fsm.cpp', 'plan_manage/src/planner_manager.cpp',
    'plan_env/src/grid_map.cpp', 'bspline_opt/src/uniform_bspline.cpp',
    'traj_utils/msg/Bspline.msg',
    'plan_manage/src_for_prometheus/traj_server_for_prometheus.cpp',
    'plan_manage/launch_for_prometheus/sitl_ego_planner_basic.launch',
    'plan_manage/launch_for_prometheus/advanced_param.xml',
    'plan_manage/CMakeLists.txt', 'plan_manage/package.xml']]
paths += ['LICENSE', 'Simulator/wksim_runtime/task.py',
          'Simulator/wksim_runtime/mission_task.py',
          'Simulator/wksim_runtime/mission_cancel.py',
          'ros2/src/prometheus_msgs/msg/UAVCommand.msg']

def run(*args):
    p = subprocess.run(args, cwd=ROOT, capture_output=True)
    return dict(command=list(args), returncode=p.returncode,
                stdout=p.stdout.decode('utf-8', errors='replace'),
                stderr=p.stderr.decode('utf-8', errors='replace'))

files = []
for path in paths:
    data = (ROOT / path).read_bytes()
    upstream = subprocess.run(['git', 'show', UPSTREAM + ':' + path],
                              cwd=ROOT, capture_output=True)
    blob = run('git', 'rev-parse', UPSTREAM + ':' + path)
    files.append(dict(path=path, sha256=hashlib.sha256(data).hexdigest(),
                      upstream_blob=blob['stdout'].strip() if blob['returncode'] == 0 else None,
                      upstream_equal=(upstream.stdout.replace(b'\r\n', b'\n') ==
                                      data.replace(b'\r\n', b'\n')) if upstream.returncode == 0 else None))
source = (ROOT / (BASE + 'plan_manage/src_for_prometheus/traj_server_for_prometheus.cpp')).read_text(encoding='utf-8')
checks = {
    'local_command_then_increment': source.index('prometheus_msgs::UAVCommand uav_command;') < source.index('uav_command.Command_ID = uav_command.Command_ID + 1;'),
    'stop_reference_overwritten': source.index('if(stop_bspline)') < source.index('uav_command.position_ref[0] = uav_odom') < source.index('uav_command.position_ref[0] = ego_traj_cmd.position.x;'),
    'timer_10ms': 'ros::Duration(0.01), cmdCallback' in source,
    'package_license_TODO': '<license>TODO</license>' in (ROOT / (BASE + 'plan_manage/package.xml')).read_text(),
}
result = dict(kind='static_source_audit_only', upstream=UPSTREAM,
              head=run('git', 'rev-parse', 'HEAD'), branch=run('git', 'branch', '--show-current'),
              files=files, checks=checks,
              issues=[run('gh', 'issue', 'view', str(n), '--repo', 'unununnnn/wksim',
                          '--json', 'number,title,state,body,labels') for n in (100, 39, 29, 33, 101, 102)],
              runtime_started=False, model_setting='requested gpt-6-astra/low; actual unverified')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if all(checks.values()) and all(i['returncode'] == 0 for i in result['issues']) else 1)
