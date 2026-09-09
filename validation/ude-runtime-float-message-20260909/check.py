import json,shlex,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2];root=Path(__file__).parent
label=sys.argv[1]
admission=json.loads((repo/'validation/ude-runtime-acceptance-20260909/px4-preflight.stdout.log').read_text())
setup='\n'.join('source '+shlex.quote(p) for p in admission['setup_files'])
mods=(['validation.test_ude_runtime.UDERuntimeTests.test_actual_ros_message_accepts_frozen_numeric_preparation']
      if label.startswith('red') else ['validation.test_ude_runtime','validation.test_pid_flight','validation.test_pid_flight_audit'])
command=['/usr/bin/python3','-B','-m','unittest',*mods,'-v']
setup+='\n'
command=['/usr/bin/python3','-B','-c',"import sys,runpy;sys.path.insert(0,'/root/wksim-attitude-audit-deps-g_2y8olg');runpy.run_module('unittest',run_name='__main__')",*mods,'-v']
argv=['wsl','-d','Ubuntu-22.04','-u','root','--','bash','--noprofile','--norc','-c',setup+shlex.join(command)]
done=subprocess.run(argv,cwd=repo,capture_output=True,timeout=60)
for name,data in [('stdout',done.stdout),('stderr',done.stderr)]:
 with (root/(label+'.'+name+'.log')).open('xb') as out:out.write(data)
with (root/(label+'.json')).open('x') as out:json.dump(dict(argv=argv,returncode=done.returncode),out,indent=2)
print(done.stdout.decode(errors='replace'));print(done.stderr.decode(errors='replace'));print('returncode',done.returncode)
