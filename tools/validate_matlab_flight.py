"""Real MATLAB/public-workbench flight acceptance; owns only its local servers.

No native publications, health bypasses, stepping, automatic write retry, or
runtime killing. MATLAB exits while the autonomous flight and optional UE live.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
import threading
import time
import traceback

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_console.server import ConsoleServer
from Simulator.wksim_console.workspace import Workspace
from Simulator.wksim_matlab.server import Bridge, Console
from validate_operator_http import live_captures


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def alive(pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab', type=Path, default=Path('D:/matlab/install date/bin/matlab.exe'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stack', choices=('px4','arducopter'), required=True)
    parser.add_argument('--view', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    startup = output/'startup'; startup.mkdir()
    startup_file = startup/'startup.m'
    startup_file.write_text("disp('WKSIM_TASK_STARTUP_ONLY');\n", encoding='utf-8')
    sources = [*(REPO/'Simulator/wksim_matlab').glob('*.py'), *(REPO/'matlab').glob('*.m'),
               *(REPO/'Simulator/wksim_console').glob('*.py'), Path(__file__),
               *(REPO/'Simulator/wksim_runtime').glob('*.py'),
               *(REPO/'Simulator/wksim_runtime').glob('*.json'),
               *(REPO/'Simulator/wksim_runtime/examples').glob('*-mission.json'),
               *(REPO/'Simulator/wksim_core').glob('*.py'),
               *(REPO/'Simulator/ue55').glob('*.py'),
               *(REPO/'ros2/src/prometheus_control').rglob('*.py'),
               REPO/'Simulator/wksim_core/model.cpp', REPO/'tools/validate_operator_http.py']
    report = dict(ok=False, stack=args.stack, view_requested=args.view, started_unix_s=time.time(),
                  python=sys.version, owner_pid=__import__('os').getpid(), commands=[],
                  scope='Real MATLAB TCP -> public Console HTTP -> real WSL FC/autonomous physics',
                  clock_mapping='Windows unix, WSL monotonic, FC boot and physics time are not equated',
                  source_sha256={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    for source in sources:
        target=output/'sources'/source.relative_to(REPO)
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,target)
    report['git_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    report['startup_sha256']=hashlib.sha256(startup_file.read_bytes()).hexdigest()
    workspace = Workspace(output/'console')
    http = ConsoleServer(workspace, 0)
    hthread = threading.Thread(target=http.serve_forever, daemon=True); hthread.start()
    api = Console(http.server_port)
    bridge = Bridge(api, 0)
    bthread = threading.Thread(target=bridge.serve_forever, daemon=True); bthread.start()
    report.update(console_port=http.server_port, bridge_port=bridge.server_address[1], bridge_instance=bridge.instance)
    save(output/'progress.json',report)
    quote = lambda path: str(path).replace('\\','/').replace("'","''")
    observation = (output/'observations.jsonl').open('w', encoding='utf-8')
    flight = None; view_opened = False; exit_observations = []

    def observe():
        nonlocal flight, view_opened
        runs = api.call('GET','/api/runs')['runs']
        flights = [r for r in runs if r['kind']=='flight']
        if not flights:
            return None
        assert len(flights)==1, 'Unexpected replay or extra flight'
        flight = api.call('GET','/api/runs/'+flights[0]['id'])
        if args.view and not view_opened and flight['status']=='running':
            view_opened = True
            report['view_open'] = api.call('POST','/api/runs/'+flight['id']+'/view', {'action':'open'})
        row = dict(observed_unix_s=time.time(), job=flight)
        truth=Path(flight['directory'])/'truth.jsonl'
        if truth.is_file():
            with truth.open('rb') as source:
                source.seek(max(0,truth.stat().st_size-8192))
                lines=source.read().split(b'\n')
                if len(lines)>2:
                    row['truth_observed']=json.loads(lines[-2])
        observation.write(json.dumps(row,allow_nan=False)+'\n'); observation.flush()
        return row

    def matlab(phase, timeout):
        command = [str(args.matlab),'-wait','-sd',str(startup),'-batch',
                   f"assert(strcmp(strrep(which('startup'),char(92),'/'),'{quote(startup_file)}')); "
                   f"addpath('{quote(REPO/'matlab')}'); validate_flight({bridge.server_address[1]}, '{quote(output)}', '{phase}', '{args.stack}')"]
        report['commands'].append(command)
        with (output/(phase+'.stdout.log')).open('wb') as log:
            process = subprocess.Popen(command,cwd=startup,stdout=log,stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            report[phase+'_launcher_pid']=process.pid
            deadline = time.monotonic()+timeout
            while process.poll() is None:
                observe()
                if time.monotonic()>deadline:
                    # Target only our MATLAB tree. Never terminate flight/console/UE.
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    raise TimeoutError('Owned MATLAB deadline exceeded')
                time.sleep(.5)
            report[phase+'_returncode']=process.returncode
            report[phase+'_exit_observed_unix_s']=time.time()
        report[phase+'_private_startup']=b'WKSIM_TASK_STARTUP_ONLY' in (output/(phase+'.stdout.log')).read_bytes()
        result = json.loads((output/(phase+'-result.json')).read_text(encoding='utf-8'))
        report[phase]=result
        report[phase+'_matlab_pid_gone']=not alive(result['pid'])
        save(output/'progress.json',report)
        assert process.returncode==0 and result['ok'] and report[phase+'_private_startup'], result.get('error','MATLAB launch or startup isolation failed')
        assert report[phase+'_matlab_pid_gone'], 'Actual MATLAB process still alive'
        return result

    try:
        launch = matlab('launch',330)
        report['launch']=launch
        deadline=time.monotonic()+420
        while True:
            row=observe()
            if row:
                exit_observations.append(row)
                if flight['status'] not in ('queued','running'): break
            assert time.monotonic()<deadline, 'Autonomous flight deadline'
            time.sleep(.5)
        report['reconnect']=matlab('reconnect',180)
        live_rows=[r for r in exit_observations if r['job']['status']=='running'
                   and ((r['job'].get('live') or {}).get('mission') or {}).get('state')=='running'
                   and (r['job'].get('live') or {}).get('state',{}).get('armed') is True
                   and r['job']['live']['state']['position'][2]>1
                   and r['job']['live']['freshness']['status']=='live']
        assert len(live_rows)>=2, 'No sustained airborne observation after actual MATLAB exit'
        first,last=live_rows[0],live_rows[-1]
        a,b=first['job']['live']['raw'],last['job']['live']['raw']
        assert a['run_id']==b['run_id']==launch['run_id'] and a['control_epoch']==b['control_epoch']
        assert a['control_epoch']==launch['before_close']['live']['raw']['control_epoch']
        assert a['native_generation']==b['native_generation']
        assert b['sequence']>a['sequence'] and b['source_received_monotonic_s']>a['source_received_monotonic_s']
        assert a['source_clock']==b['source_clock']=='fc_boot'
        stamps=[r['state']['header']['stamp'] for r in (a,b)]
        boot=[s['sec']+s['nanosec']/1e9 for s in stamps]
        assert boot[1]>boot[0]
        report['fc_boot_after_exit_seconds']=boot[1]-boot[0]
        report['autonomous_after_matlab_exit']=dict(first=first,last=last,observations=len(live_rows))
        assert last['truth_observed']['time']>first['truth_observed']['time']
        assert -first['truth_observed']['vehicle'][8]>1 and -last['truth_observed']['vehicle'][8]>1
        report['physical_after_exit_seconds']=last['truth_observed']['time']-first['truth_observed']['time']
        # MATLAB re-encoding collapses singleton struct arrays; raw_json is
        # the exact terminal artifact already preserved by the public API.
        formal=json.loads(report['reconnect']['result']['raw_json'])
        assert formal['status']=='pass' and formal['safe_landing'] and formal['children_reaped']
        assert formal['mission_truth']['ok'], 'Independent physical mission verification failed'
        pauses=formal['task']['mission']['pauses']
        assert len(pauses)==1
        assert pauses[0]['pause_request']==launch['pause_submission']['request']
        assert pauses[0]['resume_request']==launch['resume_submission']['request']
        assert pauses[0]['publications_before']==pauses[0]['publications_after']
        if args.view:
            captures=live_captures(flight['view'],launch['run_id'])
            report['ue_captures']=captures
            views=[r for r in live_rows if (r['job'].get('view') or {}).get('state')=='live'
                   and (r['job'].get('view') or {}).get('latest_actor')]
            report['ue_after_exit']=views
            assert len(views)>=2 and len(captures)>=2, 'UE live continuity evidence missing'
            va,vb=[r['job']['view']['latest_actor']['packet'] for r in (views[0],views[-1])]
            assert va['run_id']==vb['run_id']==launch['run_id']
            assert vb['sequence']>va['sequence'] and vb['sim_time_s']>va['sim_time_s']
            report['ue_captures_after_exit']=[r for r in captures if va['sequence']<=r['sequence']<=vb['sequence']]
            assert report['ue_captures_after_exit'], 'No native captured frame within post-exit live window'
        audit=[json.loads(s) for s in (output/'console/http-actions.jsonl').read_text().splitlines()]
        writes=[r for r in audit if r['method']=='POST']
        assert sum(r['path']=='/api/start' for r in writes)==1
        assert sum(r['path'].endswith('/mission-action') for r in writes)==2
        assert not any(r['path'].endswith('/cancel') for r in writes)
        report['write_counts']=dict(start=1,mission_action=2,cancel=0)
        report['ok']=True
    except Exception as error:
        report['error']=repr(error)
        report['traceback']=traceback.format_exc()
    finally:
        # Explicitly authorized failure cleanup uses the public LAND cancellation.
        # It cannot turn a failed validation into a pass and never kills a runtime.
        if not report['ok'] and flight and flight['status']=='running':
            try:
                observe()
                mission=(flight.get('live') or {}).get('mission') or {}
                report['failure_cleanup_cancel']=api.call('POST','/api/runs/'+flight['id']+'/cancel',
                                                          {'mission_id':mission['mission_id']})
            except Exception as error:
                report['failure_cleanup_error']=repr(error)
        cleanup_deadline=time.monotonic()+180
        while any(p.poll() is None for p in workspace.processes.values()) and time.monotonic()<cleanup_deadline:
            observe(); time.sleep(1)
        if view_opened and flight:
            report['view_close']=api.call('POST','/api/runs/'+flight['id']+'/view',{'action':'close'})
        report['owned_runtime_exitcodes']={k:p.poll() for k,p in workspace.processes.items()}
        report['final_runs']=api.call('GET','/api/runs')
        observation.close()
        bridge.shutdown(); bridge.server_close(); bthread.join()
        http.shutdown(); http.server_close(); hthread.join()
        try:
            workspace.close()
        except ValueError as error:
            report['ok']=False; report['cleanup_incomplete']=str(error)
        report['finished_unix_s']=time.time(); save(output/'report.json',report)
    print(json.dumps({k:report.get(k) for k in ('ok','stack','error','finished_unix_s')}))
    return 0 if report['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
