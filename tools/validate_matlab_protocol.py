"""Run installed MATLAB against real local ConsoleServer/Bridge; never start SITL."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_console.server import ConsoleServer
from Simulator.wksim_console.workspace import Workspace
from Simulator.wksim_matlab.server import Bridge, Console


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab', type=Path, default=Path('D:/matlab/install date/bin/matlab.exe'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    startup = output/'startup'
    startup.mkdir()
    # The current startup folder wins MATLAB name resolution. Keep this run
    # out of the user's RflySim auto-registration/configuration startup.
    startup_file = startup/'startup.m'
    startup_file.write_text("disp('WKSIM_TASK_STARTUP_ONLY');\n", encoding='utf-8')
    workspace = Workspace(output/'console')
    http = ConsoleServer(workspace, 0)
    hthread = threading.Thread(target=http.serve_forever, daemon=True); hthread.start()
    bridge = Bridge(Console(http.server_port), 0)
    bthread = threading.Thread(target=bridge.serve_forever, daemon=True); bthread.start()
    quote = lambda path: str(path).replace('\\', '/').replace("'", "''")
    command = [str(args.matlab), '-wait', '-sd', str(startup), '-batch',
               f"assert(strcmp(strrep(which('startup'),char(92),'/'),'{quote(startup_file)}')); "
               f"addpath('{quote(REPO/'matlab')}'); validate_protocol({bridge.server_address[1]}, '{quote(output/'matlab-result.json')}')"]
    sources = [*(REPO/'Simulator/wksim_matlab').glob('*.py'), *(REPO/'matlab').glob('*.m'),
               REPO/'tools/validate_matlab_protocol.py', REPO/'validation/test_wksim_matlab.py',
               REPO/'Simulator/wksim_console/server.py', REPO/'Simulator/wksim_console/workspace.py',
               REPO/'Simulator/wksim_runtime/config.py', REPO/'Simulator/wksim_runtime/mission_plan.py']
    report = dict(scope='Real MATLAB protocol + public product HTTP/config; no SITL or UE', command=command,
                  startup_file=str(startup_file), startup_sha256=hashlib.sha256(startup_file.read_bytes()).hexdigest(),
                  started_unix_s=time.time(), bridge_instance=bridge.instance, console_port=http.server_port,
                  bridge_port=bridge.server_address[1], python=sys.version,
                  source_sha256={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    try:
        with (output/'matlab.stdout.log').open('wb') as log:
            process = subprocess.Popen(command, cwd=startup, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            report['owned_matlab_launcher_pid'] = process.pid
            try:
                report['returncode'] = process.wait(timeout=240)
            except subprocess.TimeoutExpired:
                # Only our launcher tree is targeted; never kill other MATLAB instances.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                process.wait(timeout=15)
                report['error'] = 'MATLAB timed out after 240 seconds'
        report['no_jobs_started'] = workspace.jobs == {} and workspace.processes == {}
        report['saved_config_exists'] = (workspace.config_dir/'matlab-real.json').is_file()
        result = output/'matlab-result.json'
        report['matlab'] = json.loads(result.read_text(encoding='utf-8')) if result.exists() else None
        report['private_startup_executed'] = b'WKSIM_TASK_STARTUP_ONLY' in (output/'matlab.stdout.log').read_bytes()
        report['ok'] = (report.get('returncode') == 0 and report['no_jobs_started'] and report['private_startup_executed']
                        and bool(report['matlab'] and report['matlab']['ok']))
    finally:
        bridge.shutdown(); bridge.server_close(); bthread.join()
        http.shutdown(); http.server_close(); hthread.join(); workspace.close()
        report['finished_unix_s'] = time.time()
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
