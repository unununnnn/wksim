import json,os,pathlib,time
markers=('arducopter','ardupilot','px4','micro_ros_agent','microxrceagent','prometheus_control','planner_transport_node','roscore','rosmaster','unrealeditor','matlab','cc1plus','g++','bpftrace','run_joint_flight.py','wksim_core.worker','validate_generated_e0_lifecycle.py','pytest','run_e2e.py','first_step_trace_recorder','wksim-native-release-wait','clock_cases','wksim-release-extension-bench','cc1')
found=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit() or int(p.name)==os.getpid():continue
 try:
  comm=(p/'comm').read_text().strip()
  argv=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
  if comm in ('bash','sh','dash','timeout'):continue
  if any(m in (comm+' '+argv).lower() for m in markers):
   found.append(dict(pid=int(p.name),comm=comm,argv=argv[:350]))
 except (FileNotFoundError,ProcessLookupError,PermissionError):pass
print(json.dumps(dict(checked_unix=time.time(),distro=os.environ.get('WSL_DISTRO_NAME'),boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),uptime=pathlib.Path('/proc/uptime').read_text().strip(),found=found)))
