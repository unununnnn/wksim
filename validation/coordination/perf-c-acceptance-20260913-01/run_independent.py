import json,pathlib,subprocess,base64
root=pathlib.Path(__file__).resolve().parent
pre="import json,os,pathlib,time\nmarkers=('arducopter','ardupilot','px4','micro_ros_agent','microxrceagent','prometheus_control','planner_transport_node','roscore','rosmaster','unrealeditor','matlab','cc1plus','g++','bpftrace','run_joint_flight.py','wksim_core.worker','validate_generated_e0_lifecycle.py','pytest','run_e2e.py','first_step_trace_recorder','wksim-native-release-wait','clock_cases','wksim-release-extension-bench','cc1')\nfound=[]\nfor p in pathlib.Path('/proc').iterdir():\n if not p.name.isdigit() or int(p.name)==os.getpid():continue\n try:\n  comm=(p/'comm').read_text().strip()\n  argv=(p/'cmdline').read_bytes().replace(b'\\0',b' ').decode(errors='replace')\n  if comm in ('bash','sh','dash','timeout'):continue\n  if any(m in (comm+' '+argv).lower() for m in markers):\n   found.append(dict(pid=int(p.name),comm=comm,argv=argv[:350]))\n except (FileNotFoundError,ProcessLookupError,PermissionError):pass\nprint(json.dumps(dict(checked_unix=time.time(),distro=os.environ.get('WSL_DISTRO_NAME'),boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),uptime=pathlib.Path('/proc/uptime').read_text().strip(),found=found)))\n"
checks=[]
for distro in ['Ubuntu-22.04','RflySim-20.04']:
 r=subprocess.run(['wsl.exe','-d',distro,'-u','root','--','python3','-'],input=pre,capture_output=True,text=True,timeout=45)
 assert r.returncode==0,r.stderr
 c=json.loads([s for s in r.stdout.splitlines() if s.startswith('{')][-1]);assert not c['found'],c
 checks.append(c)
(root/'independent-prechecks.json').write_bytes((json.dumps(checks,indent=2)+'\n').encode())
payload={'prior':json.loads((root/'receipt.json').read_text()),'checks':checks}
linux="import hashlib,json,os,pathlib,signal,subprocess,time\nprior=payload['prior'];root=pathlib.Path(prior['directory'])\nboot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nassert all(c['boot_id']==boot and 0<=time.time()-c['checked_unix']<=60 and not c['found'] for c in payload['checks'])\nassert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==sha for n,sha in prior['source_sha256'].items())\np=subprocess.Popen([str(root/'acceptance')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)\ntry:stdout,stderr=p.communicate(timeout=20)\nexcept subprocess.TimeoutExpired:\n os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()\nout={'boot_id':boot,'original_compile_boot':prior['boot_id'],'source_sha256':prior['source_sha256'],'binary_sha256':hashlib.sha256((root/'acceptance').read_bytes()).hexdigest(),'pid':p.pid,'exit_code':p.returncode,'stdout':stdout,'stderr':stderr,'switch_sampling_executed':False}\ntry:os.killpg(p.pid,0);out['pgid_empty']=False\nexcept ProcessLookupError:out['pgid_empty']=True\nout['boot_after']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nprint(json.dumps(out))\n"
script='import json,base64\npayload=json.loads(base64.b64decode('+repr(base64.b64encode(json.dumps(payload).encode()).decode())+'))\n'+linux
r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','-u','root','--','python3','-'],input=script,capture_output=True,text=True,timeout=45)
assert r.returncode==0,(r.stdout,r.stderr)
out=json.loads([s for s in r.stdout.splitlines() if s.startswith('{')][-1])
(root/'independent-receipt.json').write_bytes((json.dumps(out,indent=2)+'\n').encode())
print(json.dumps(out))
