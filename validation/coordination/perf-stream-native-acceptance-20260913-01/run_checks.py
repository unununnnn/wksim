import base64,json,pathlib,subprocess
root=pathlib.Path(__file__).resolve().parent
assert not (root/'receipt.json').exists()
pre="import json,os,pathlib,time\nmarkers=('arducopter','ardupilot','px4','micro_ros_agent','microxrceagent','prometheus_control','planner_transport_node','roscore','rosmaster','unrealeditor','matlab','cc1plus','g++','bpftrace','run_joint_flight.py','wksim_core.worker','validate_generated_e0_lifecycle.py','pytest','run_e2e.py','first_step_trace_recorder','wksim-native-release-wait','clock_cases','wksim-release-extension-bench','cc1')\nfound=[]\nfor p in pathlib.Path('/proc').iterdir():\n if not p.name.isdigit() or int(p.name)==os.getpid():continue\n try:\n  comm=(p/'comm').read_text().strip()\n  argv=(p/'cmdline').read_bytes().replace(b'\\0',b' ').decode(errors='replace')\n  if comm in ('bash','sh','dash','timeout'):continue\n  if any(m in (comm+' '+argv).lower() for m in markers):\n   found.append(dict(pid=int(p.name),comm=comm,argv=argv[:350]))\n except (FileNotFoundError,ProcessLookupError,PermissionError):pass\nprint(json.dumps(dict(checked_unix=time.time(),distro=os.environ.get('WSL_DISTRO_NAME'),boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),uptime=pathlib.Path('/proc/uptime').read_text().strip(),found=found)))\n"
checks=[]
for distro in ['Ubuntu-22.04','RflySim-20.04']:
 r=subprocess.run(['wsl.exe','-d',distro,'-u','root','--','python3','-'],input=pre,capture_output=True,text=True,timeout=45)
 assert r.returncode==0,r.stderr
 c=json.loads([x for x in r.stdout.splitlines() if x.startswith('{')][-1]);assert not c['found'],c
 checks.append(c)
(root/'prechecks.json').write_bytes((json.dumps(checks,indent=2)+'\n').encode())
author=root.parent/'ds-perf-stream-recorder-20260913-01'
paths=[author/n for n in ['wksim_perf_stream.c','wksim_perf_stream.h','wksim_perf_stream_demo.c']]+[root/'create_failure_case.c']
sources={p.name:base64.b64encode(p.read_bytes()).decode() for p in paths}
snapshot=root/'sources';snapshot.mkdir(exist_ok=False)
for name,raw in sources.items():(snapshot/name).write_bytes(base64.b64decode(raw))
payload={'checks':checks,'sources':sources}
linux="import base64,hashlib,json,os,pathlib,signal,subprocess,tempfile,time\nboot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nassert all(c['boot_id']==boot and 0<=time.time()-c['checked_unix']<=60 and not c['found'] for c in payload['checks'])\nroot=pathlib.Path(tempfile.mkdtemp(prefix='wksim-stream-native-',dir='/root'))\nfor name,raw in payload['sources'].items():(root/name).write_bytes(base64.b64decode(raw))\nout={'directory':str(root),'boot_id':boot,'commands':[],'source_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in payload['sources']}}\nflags=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread','-I.']\ncommands=[flags+['-o','demo','wksim_perf_stream_demo.c','wksim_perf_stream.c'],flags+['-Wl,--wrap=pthread_create','-o','create_failure','create_failure_case.c','wksim_perf_stream.c'],['./create_failure']]\nfor argv in commands:\n p=subprocess.Popen(argv,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)\n row={'argv':argv,'pid':p.pid}\n try:stdout,stderr=p.communicate(timeout=20)\n except subprocess.TimeoutExpired:\n  os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate();row['timed_out']=True\n row.update(exit_code=p.returncode,stdout=stdout,stderr=stderr)\n try:os.killpg(p.pid,0);row['pgid_empty']=False\n except ProcessLookupError:row['pgid_empty']=True\n out['commands'].append(row)\n if p.returncode or not row['pgid_empty']:break\nout['boot_after']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nout['binary_sha256']={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['demo','create_failure'] if (root/n).exists()}\n(root/'receipt.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))\n"
script='import base64,json\npayload=json.loads(base64.b64decode('+repr(base64.b64encode(json.dumps(payload).encode()).decode())+'))\n'+linux
r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','-u','root','--','python3','-'],input=script,capture_output=True,text=True,timeout=65)
(root/'stdout.txt').write_bytes(r.stdout.encode());(root/'stderr.txt').write_bytes(r.stderr.encode())
assert r.returncode==0,(r.stdout,r.stderr)
out=json.loads([x for x in r.stdout.splitlines() if x.startswith('{')][-1])
(root/'receipt.json').write_bytes((json.dumps(out,indent=2)+'\n').encode())
print(json.dumps(out))
