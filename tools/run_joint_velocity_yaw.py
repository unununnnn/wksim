"""Run the formal public velocity+yaw joint scene with argv arrays and owned cleanup."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.evidence import write_json
from tools.validate_joint_velocity_yaw import run

evidence=Path(tempfile.mkdtemp(prefix='joint-velocity-yaw-',dir=REPO/'validation'))
output=Path(tempfile.mkdtemp(prefix='wksim-formal-joint-',dir='/root'))
config=dict(schema_version=1,kind='joint_scene',run_id='joint-velocity-yaw-'+output.name.rsplit('-',1)[-1],
            runtime_profile='joint_quad_dds_v1',task='public_velocity_yaw')
write_json(evidence/'config.json',config)
command=['bash',str(REPO/'tools/run-wksim.sh'),str(evidence/'config.json'),'--output-root',str(output)]
print(json.dumps(dict(evidence=str(evidence),output_root=str(output),config=config)),flush=True)
with (evidence/'service.log').open('w') as log:
    process=subprocess.Popen(command,cwd=REPO,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    write_json(evidence/'launch.json',dict(command=command,pid=process.pid,output_root=str(output)))
    code=1
    try:
        flow=run(output/config['run_id'],evidence/'flow.json')
        process.wait(timeout=20)
        code=process.returncode or (0 if flow['status']=='pass' else 1)
    finally:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        if (output/config['run_id']).exists():
            shutil.copytree(output/config['run_id'],evidence/'run')
        write_json(evidence/'exit.json',dict(returncode=process.returncode))
print(json.dumps(dict(status='pass' if code==0 else 'failed',evidence=str(evidence))),flush=True)
raise SystemExit(code)
