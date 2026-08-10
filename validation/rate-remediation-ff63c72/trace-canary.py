"""Short self-only tracefs canary; never changes global tracing controls."""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import uuid

repo = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('trace_owner', repo/'validation/rate-syscall-scheduler-plan-20260909/collect_tracefs.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
output = Path(sys.argv[1]); output.mkdir(mode=0o700)
before = module.preflight()
libc = ctypes.CDLL(None, use_errno=True)
old = ctypes.create_string_buffer(16)
assert libc.prctl(16, old, 0, 0, 0) == 0
name = 'wk'+uuid.uuid4().hex[:12]
assert libc.prctl(15, name.encode(), 0, 0, 0) == 0
instance = module.TRACE/'instances'/('wksim-rate-'+uuid.uuid4().hex)
record = dict(name=name, pid=os.getpid(), identity=module.identity(os.getpid()),
              namespace_status=Path('/proc/self/status').read_text(), before=before)
inode = None
try:
    instance.mkdir(); stat=instance.stat(); inode=(stat.st_dev, stat.st_ino)
    def put(path, value):
        module.guarded_instance(instance, inode)
        (instance/path).write_text(str(value)+'\n')
    put('tracing_on', 0); put('current_tracer', 'nop'); put('events/enable', 0); put('trace_clock', 'mono')
    record['cpumask'] = (instance/'tracing_cpumask').read_text()
    record['ftrace_enabled'] = Path('/proc/sys/kernel/ftrace_enabled').read_text()
    put('events/sched/sched_switch/filter', f'prev_comm == "{name}" || next_comm == "{name}"')
    put('events/sched/sched_switch/enable', 1)
    put('events/syscalls/sys_enter_write/filter', f'common_pid == {os.getpid()}')
    put('events/syscalls/sys_enter_write/enable', 1)
    put('tracing_on', 1)
    with (output/'canary-bytes').open('wb', buffering=0) as file:
        for i in range(20):
            file.write(b'canary\n'); time.sleep(.01)
    put('tracing_on', 0)
    raw=(instance/'trace').read_bytes(); (output/'trace.txt').write_bytes(raw)
    record['trace_bytes']=len(raw)
    record['stats']=module.statistics(instance)
finally:
    if inode is not None:
        module.guarded_instance(instance,inode)
        (instance/'tracing_on').write_text('0\n')
        instance.rmdir()
    libc.prctl(15, old, 0, 0, 0)
    record['global_controls_unchanged'] = module.preflight()['global_controls'] == before['global_controls']
    (output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:record[k] for k in ('pid','name','trace_bytes','ftrace_enabled','cpumask','global_controls_unchanged')}))
