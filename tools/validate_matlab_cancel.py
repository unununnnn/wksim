"""Real MATLAB high-level cancel; no native commands or replacement flight path."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_console.workspace import Workspace
from Simulator.wksim_console.server import ConsoleServer
from Simulator.wksim_matlab.server import Bridge,Console
from Simulator.wksim_runtime.mission_evidence import audit_mission_truth
from validate_matlab_flight import alive

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args();root=args.output.resolve();root.mkdir(exist_ok=False,parents=True)
startup=root/'startup';startup.mkdir();(startup/'startup.m').write_text("disp('WKSIM_TASK_STARTUP_ONLY');\n")
workspace=Workspace(root/'console');http=ConsoleServer(workspace,0)
ht=threading.Thread(target=http.serve_forever,daemon=True);ht.start()
api=Console(http.server_port);bridge=Bridge(api,0)
bt=threading.Thread(target=bridge.serve_forever,daemon=True);bt.start()
quote=lambda p:str(p).replace('\\','/').replace("'","''")
command=['D:/matlab/install date/bin/matlab.exe','-wait','-sd',str(startup),'-batch',
    f"assert(strcmp(strrep(which('startup'),char(92),'/'),'{quote(startup/'startup.m')}')); "
    f"addpath('{quote(REPO/'matlab')}'); validate_cancel({bridge.server_address[1]},'{quote(root/'matlab-result.json')}')"]
sources=[Path(__file__),REPO/'matlab/validate_cancel.m',REPO/'matlab/WksimClient.m',REPO/'Simulator/wksim_matlab/server.py']
report=dict(ok=False,scope='Real MATLAB cancel and normal autonomous LAND; no UE',command=command,
            source_sha256={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            console_port=http.server_port,bridge_port=bridge.server_address[1],started_unix_s=time.time())
process=None
try:
    with (root/'matlab.stdout.log').open('wb') as log:
        process=subprocess.Popen(command,cwd=startup,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        report['launcher_pid']=process.pid;report['returncode']=process.wait(timeout=420)
    matlab=json.loads((root/'matlab-result.json').read_text());report['matlab']=matlab
    report['actual_matlab_pid_gone']=not alive(matlab['pid'])
    report['private_startup']=b'WKSIM_TASK_STARTUP_ONLY' in (root/'matlab.stdout.log').read_bytes()
    assert report['returncode']==0 and matlab['ok'] and report['actual_matlab_pid_gone'] and report['private_startup']
    flight=api.call('GET','/api/runs/'+matlab['job_id']);directory=Path(flight['directory'])
    formal=json.loads((directory/'result.json').read_text())
    assert (directory/'result.json').read_text()==matlab['result']['raw_json']
    assert formal['status']=='cancelled' and formal['safe_landing'] and formal['children_reaped'] and not formal['cleanup_errors']
    assert formal['task']['mission']['cancel_request']==matlab['cancel']['request']
    report['physical_audit']=audit_mission_truth(directory/'truth.jsonl',formal['task']['mission'])
    actions=[json.loads(line) for line in (root/'console/http-actions.jsonl').read_text().splitlines()]
    assert sum(r['method']=='POST' and r['path'].endswith('/cancel') for r in actions)==1
    assert sum(r['method']=='POST' and r['path']=='/api/start' for r in actions)==1
    report['formal_result']=str(directory/'result.json');report['ok']=True
except BaseException as error:
    report['error']=repr(error)
finally:
    if process is not None and process.poll() is None:
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
        process.wait(timeout=15)
        report['failed_client_retired']=True
    # Cancel a still-owned failed experiment through the same public policy.
    for job in api.call('GET','/api/runs')['runs']:
        if job['kind']=='flight' and job['status']=='running':
            current=api.call('GET','/api/runs/'+job['id'])
            try:report['failure_cleanup_cancel']=api.call('POST','/api/runs/'+job['id']+'/cancel',
                dict(mission_id=current['live']['mission']['mission_id']))
            except Exception as error:report['cleanup_error']=repr(error)
    deadline=time.monotonic()+180
    while any(p.poll() is None for p in workspace.processes.values()) and time.monotonic()<deadline:time.sleep(.2)
    report['owned_runtime_exitcodes']={key:p.poll() for key,p in workspace.processes.items()}
    if any(value is None for value in report['owned_runtime_exitcodes'].values()):report['ok']=False;report['cleanup_incomplete']=True
    else:workspace.close()
    bridge.shutdown();bridge.server_close();bt.join();http.shutdown();http.server_close();ht.join()
    report['finished_unix_s']=time.time();(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({key:report.get(key) for key in ('ok','error','formal_result','cleanup_incomplete')}))
raise SystemExit(0 if report['ok'] else 1)
