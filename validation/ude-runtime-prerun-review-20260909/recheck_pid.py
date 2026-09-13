"""Offline legacy PID audit compatibility; no flight/model/native process launch."""
import json
from pathlib import Path
import shlex
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
runs={'px4':'pid-px4-final-source-20260909-02','ap':'pid-ap-shaped-feedback-20260909-02'}
for name,run_id in runs.items():
    root='/root/wksim-pid-flight-'+run_id+'/'+run_id
    result=json.loads(Path(r'\\wsl.localhost\Ubuntu-22.04'+(root+'/result.json').replace('/','\\')).read_text())
    setup='\n'.join('source '+shlex.quote(p) for p in result['admission']['setup_files'])
    destination='/mnt/c'+HERE.as_posix()[2:]+'/'+name+'-legacy-pid-audit.json'
    command=['/usr/bin/python3','-B','-c',"import sys,runpy;sys.path.insert(0,'/root/wksim-attitude-audit-deps-g_2y8olg');runpy.run_path('tools/audit_pid_flight.py',run_name='__main__')",'--run-dir',root,'--output',destination]
    argv=['wsl.exe','-d','Ubuntu-22.04','-u','root','--','bash','--noprofile','--norc','-c',setup+'\n'+shlex.join(command)]
    start=time.time()
    completed=subprocess.run(argv,cwd=ROOT,capture_output=True)
    for suffix,value in [('stdout.log',completed.stdout),('stderr.log',completed.stderr)]:
        with (HERE/(name+'-audit-command.'+suffix)).open('xb') as stream:stream.write(value)
    with (HERE/(name+'-audit-command.json')).open('x') as stream:
        json.dump(dict(argv=argv,started_unix_s=start,finished_unix_s=time.time(),returncode=completed.returncode),stream,indent=2)
    print(name,completed.returncode,completed.stdout.decode(errors='replace'),flush=True)
