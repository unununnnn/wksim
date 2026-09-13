import base64,json,pathlib,subprocess,time
root=pathlib.Path(__file__).resolve().parent
coord=root.parent
precheck="import json,os,pathlib,time\nmarkers=('arducopter','ardupilot','px4','micro_ros_agent','microxrceagent','prometheus_control','planner_transport_node','roscore','rosmaster','unrealeditor','matlab','cc1plus','g++','bpftrace','run_joint_flight.py','wksim_core.worker','validate_generated_e0_lifecycle.py','pytest','run_e2e.py','first_step_trace_recorder','wksim-native-release-wait','clock_cases','wksim-release-extension-bench','cc1')\nfound=[]\nfor p in pathlib.Path('/proc').iterdir():\n if not p.name.isdigit() or int(p.name)==os.getpid():continue\n try:\n  comm=(p/'comm').read_text().strip()\n  argv=(p/'cmdline').read_bytes().replace(b'\\0',b' ').decode(errors='replace')\n  if comm in ('bash','sh','dash','timeout'):continue\n  if any(m in (comm+' '+argv).lower() for m in markers):\n   found.append(dict(pid=int(p.name),comm=comm,argv=argv[:350]))\n except (FileNotFoundError,ProcessLookupError,PermissionError):pass\nprint(json.dumps(dict(checked_unix=time.time(),distro=os.environ.get('WSL_DISTRO_NAME'),boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),uptime=pathlib.Path('/proc/uptime').read_text().strip(),found=found)))\n"
checks=[]
for distro in ['Ubuntu-22.04','RflySim-20.04']:
 r=subprocess.run(['wsl.exe','-d',distro,'-u','root','--','python3','-'],input=precheck,text=True,capture_output=True,timeout=45)
 assert r.returncode==0,(distro,r.stderr)
 row=json.loads([x for x in r.stdout.splitlines() if x.startswith('{')][-1])
 assert not row['found'],row
 checks.append(row)
(root/'prechecks.json').write_bytes((json.dumps(checks,indent=2)+'\n').encode())
paths=[coord/'ds-perf-self-capability-20260913-01'/n for n in ['perf_self_capability.c','perf_ring_parse.c','perf_ring_parse.h','perf_self_capability_selftest.c']]
paths.append(coord/'ds-perf-independent-cases-20260913-01'/'ds_perf_ring_acceptance.c')
sources={p.name:base64.b64encode(p.read_bytes()).decode() for p in paths}
payload={'checks':checks,'sources':sources}
linux="import base64,hashlib,json,os,pathlib,signal,subprocess,tempfile,time\nchecks=payload['checks'];boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nassert all(c['boot_id']==boot and 0<=time.time()-c['checked_unix']<=60 and not c['found'] for c in checks)\nroot=pathlib.Path(tempfile.mkdtemp(prefix='wksim-perf-c-tests-'))\nfor name,data in payload['sources'].items():(root/name).write_bytes(base64.b64decode(data))\nout={'boot_id':boot,'directory':str(root),'switch_sampling_executed':False,'commands':[],'source_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in payload['sources']}}\nflags=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror']\ncommands=[flags+['-o','probe','perf_self_capability.c','perf_ring_parse.c'],flags+['-o','selftest','perf_self_capability_selftest.c','perf_ring_parse.c'],flags+['-I.','-o','acceptance','ds_perf_ring_acceptance.c','perf_ring_parse.c'],['./selftest'],['./acceptance']]\nfor argv in commands:\n p=subprocess.Popen(argv,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)\n row={'argv':argv,'pid':p.pid}\n try:stdout,stderr=p.communicate(timeout=20)\n except subprocess.TimeoutExpired:\n  os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate();row['timeout']=True\n row.update(exit_code=p.returncode,stdout=stdout,stderr=stderr)\n try:os.killpg(p.pid,0);row['pgid_empty']=False\n except ProcessLookupError:row['pgid_empty']=True\n out['commands'].append(row)\n if p.returncode or not row['pgid_empty']:break\nout['boot_after']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\n(root/'receipt.json').write_text(json.dumps(out,indent=2))\nprint(json.dumps(out))\n"
script='import json,base64\npayload=json.loads(base64.b64decode('+repr(base64.b64encode(json.dumps(payload).encode()).decode())+'))\n'+linux
r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','-u','root','--','python3','-'],input=script,text=True,capture_output=True,timeout=110)
(root/'stdout.txt').write_bytes(r.stdout.encode())
(root/'stderr.txt').write_bytes(r.stderr.encode())
assert r.returncode==0,(r.returncode,r.stderr)
receipt=json.loads([x for x in r.stdout.splitlines() if x.startswith('{')][-1])
(root/'receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode())
print(json.dumps(receipt))
