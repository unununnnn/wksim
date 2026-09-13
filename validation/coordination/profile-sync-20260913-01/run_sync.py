import base64,hashlib,json,pathlib,subprocess
root=pathlib.Path(__file__).resolve().parent
repo=root.parents[2]
assert (repo/'Simulator').exists()
assert not (root/'receipt.json').exists()
pre="import json,os,pathlib,time\nmarkers=('arducopter','ardupilot','px4','micro_ros_agent','microxrceagent','prometheus_control','planner_transport_node','roscore','rosmaster','unrealeditor','matlab','cc1plus','g++','bpftrace','run_joint_flight.py','wksim_core.worker','validate_generated_e0_lifecycle.py','pytest','run_e2e.py','first_step_trace_recorder','wksim-native-release-wait','clock_cases','wksim-release-extension-bench','cc1')\nfound=[]\nfor p in pathlib.Path('/proc').iterdir():\n if not p.name.isdigit() or int(p.name)==os.getpid():continue\n try:\n  comm=(p/'comm').read_text().strip()\n  argv=(p/'cmdline').read_bytes().replace(b'\\0',b' ').decode(errors='replace')\n  if comm in ('bash','sh','dash','timeout'):continue\n  if any(m in (comm+' '+argv).lower() for m in markers):\n   found.append(dict(pid=int(p.name),comm=comm,argv=argv[:350]))\n except (FileNotFoundError,ProcessLookupError,PermissionError):pass\nprint(json.dumps(dict(checked_unix=time.time(),distro=os.environ.get('WSL_DISTRO_NAME'),boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),uptime=pathlib.Path('/proc/uptime').read_text().strip(),found=found)))\n"
checks=[]
for distro in ['Ubuntu-22.04','RflySim-20.04']:
 r=subprocess.run(['wsl.exe','-d',distro,'-u','root','--','python3','-'],input=pre,text=True,capture_output=True,timeout=45)
 assert r.returncode==0,r.stderr
 c=json.loads([x for x in r.stdout.splitlines() if x.startswith('{')][-1]);assert not c['found'],c
 checks.append(c)
(root/'prechecks.json').write_bytes((json.dumps(checks,indent=2)+'\n').encode())
files={n:base64.b64encode((repo/n).read_bytes()).decode() for n in ['Simulator/wksim_runtime/joint_profile.py','validation/test_joint_profile.py']}
deps={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in ['tools/joint_control_candidate.py','tools/joint_message_candidate.py','Simulator/wksim_runtime/build_identity.py']}
payload={'checks':checks,'files':files,'dependencies':deps}
linux="import base64,hashlib,json,os,pathlib,signal,subprocess,time\nrepo=pathlib.Path('/root/wksim-release-acceptance-fe3')\nboot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nassert all(c['boot_id']==boot and 0<=time.time()-c['checked_unix']<=60 and not c['found'] for c in payload['checks'])\nfiles=payload['files']\nstatus=subprocess.run(['git','status','--porcelain','--',*files],cwd=repo,text=True,capture_output=True,check=True)\nassert not status.stdout,status.stdout\nbackup=repo/'validation/profile-sync-20260913-01';backup.mkdir(exist_ok=False)\nout={'boot_id':boot,'backup':str(backup),'files':{},'dependencies':{}}\nfor name in ['tools/joint_control_candidate.py','tools/joint_message_candidate.py','Simulator/wksim_runtime/build_identity.py']:\n actual=hashlib.sha256((repo/name).read_bytes()).hexdigest()\n assert actual==payload['dependencies'][name],name\n out['dependencies'][name]=actual\nfor name,encoded in files.items():\n path=repo/name;old=path.read_bytes();new=base64.b64decode(encoded)\n (backup/path.name).write_bytes(old)\n out['files'][name]={'before_sha256':hashlib.sha256(old).hexdigest(),'after_sha256':hashlib.sha256(new).hexdigest()}\n path.write_bytes(new)\nargv=['python3','-m','unittest','validation.test_joint_profile','-v']\np=subprocess.Popen(argv,cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)\ntry:stdout,stderr=p.communicate(timeout=45)\nexcept subprocess.TimeoutExpired:\n os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()\nout['tests']={'argv':argv,'pid':p.pid,'exit_code':p.returncode,'stdout':stdout,'stderr':stderr}\ntry:os.killpg(p.pid,0);out['tests']['pgid_empty']=False\nexcept ProcessLookupError:out['tests']['pgid_empty']=True\nout['boot_after']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\n(backup/'receipt.json').write_text(json.dumps(out,indent=2))\nprint(json.dumps(out))\n"
script='import json,base64\npayload=json.loads(base64.b64decode('+repr(base64.b64encode(json.dumps(payload).encode()).decode())+'))\n'+linux
r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','-u','root','--','python3','-'],input=script,text=True,capture_output=True,timeout=65)
(root/'stdout.txt').write_bytes(r.stdout.encode());(root/'stderr.txt').write_bytes(r.stderr.encode())
assert r.returncode==0,(r.stdout,r.stderr)
result=json.loads([x for x in r.stdout.splitlines() if x.startswith('{')][-1])
(root/'receipt.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
print(json.dumps(result))
