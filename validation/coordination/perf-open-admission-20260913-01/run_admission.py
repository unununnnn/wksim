import base64,json,pathlib,subprocess,time
root=pathlib.Path(__file__).resolve().parent
precheck="import json,os,pathlib,time\nmarkers=('arducopter','ardupilot','px4','micro_ros_agent','microxrceagent','prometheus_control','planner_transport_node','roscore','rosmaster','unrealeditor','matlab','cc1plus','g++','bpftrace','run_joint_flight.py','wksim_core.worker','validate_generated_e0_lifecycle.py','pytest','run_e2e.py','first_step_trace_recorder','wksim-native-release-wait','clock_cases','wksim-release-extension-bench','cc1')\nfound=[]\nfor p in pathlib.Path('/proc').iterdir():\n if not p.name.isdigit() or int(p.name)==os.getpid():continue\n try:\n  comm=(p/'comm').read_text().strip()\n  argv=(p/'cmdline').read_bytes().replace(b'\\0',b' ').decode(errors='replace')\n  if comm in ('bash','sh','dash','timeout'):continue\n  if any(m in (comm+' '+argv).lower() for m in markers):\n   found.append(dict(pid=int(p.name),comm=comm,argv=argv[:350]))\n except (FileNotFoundError,ProcessLookupError,PermissionError):pass\nprint(json.dumps(dict(checked_unix=time.time(),distro=os.environ.get('WSL_DISTRO_NAME'),boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),uptime=pathlib.Path('/proc/uptime').read_text().strip(),found=found)))\n"
checks=[]
for distro in ['Ubuntu-22.04','RflySim-20.04']:
 r=subprocess.run(['wsl.exe','-d',distro,'-u','root','--','python3','-'],input=precheck,text=True,capture_output=True,timeout=45)
 (root/(distro+'-precheck.txt')).write_text(r.stdout+r.stderr,encoding='utf-8')
 assert r.returncode==0,(distro,r.stderr)
 row=json.loads([line for line in r.stdout.splitlines() if line.startswith('{')][-1])
 assert not row['found'],row
 checks.append(row)
(root/'prechecks.json').write_text(json.dumps(checks,indent=2))
source=(root/'open_self.c').read_bytes()
linux="import base64,hashlib,json,os,pathlib,signal,subprocess,tempfile,time\nchecks=json.loads(base64.b64decode(CHECKS_B64))\nboot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nassert all(c['boot_id']==boot and 0<=time.time()-c['checked_unix']<=60 and not c['found'] for c in checks), 'stale or busy precheck'\nroot=pathlib.Path(tempfile.mkdtemp(prefix='wksim-perf-open-'))\nsource=base64.b64decode(SOURCE_B64)\n(root/'open_self.c').write_bytes(source)\nout={'boot_id':boot,'directory':str(root),'kernel':os.uname().release,'paranoid':pathlib.Path('/proc/sys/kernel/perf_event_paranoid').read_text().strip(),'source_sha256':hashlib.sha256(source).hexdigest(),'commands':[]}\nfor argv in [['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-o',str(root/'open_self'),str(root/'open_self.c')],[str(root/'open_self')]]:\n p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)\n row={'argv':argv,'pid':p.pid}\n try:\n  stdout,stderr=p.communicate(timeout=20)\n except subprocess.TimeoutExpired:\n  os.killpg(p.pid,signal.SIGKILL)\n  stdout,stderr=p.communicate()\n  row['timed_out']=True\n row.update(exit_code=p.returncode,stdout=stdout,stderr=stderr)\n try:os.killpg(p.pid,0);row['pgid_empty']=False\n except ProcessLookupError:row['pgid_empty']=True\n out['commands'].append(row)\n if p.returncode or not row['pgid_empty']:break\nbinary=root/'open_self'\nif binary.exists():out['binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()\nout['boot_after']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\n(root/'receipt.json').write_text(json.dumps(out,indent=2))\nprint(json.dumps(out))\n"
linux='CHECKS_B64='+repr(base64.b64encode(json.dumps(checks).encode()).decode())+'\nSOURCE_B64='+repr(base64.b64encode(source).decode())+'\n'+linux
r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','-u','root','--','python3','-'],input=linux,text=True,capture_output=True,timeout=55)
(root/'native-stdout.txt').write_text(r.stdout,encoding='utf-8')
(root/'native-stderr.txt').write_text(r.stderr,encoding='utf-8')
assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
receipt=json.loads([line for line in r.stdout.splitlines() if line.startswith('{')][-1])
(root/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt))
