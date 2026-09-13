"""Private diagnostic-only names for namespace-to-kernel PID correlation.

Activated only through a per-run PYTHONPATH. Production files and process
policy are untouched; only the three exactly bound processes name themselves.
"""
import json
import os
from pathlib import Path
import re
import sys

run_id = os.environ.get('WKSIM_TRACE_RUN')
args = getattr(sys, 'orig_argv', [])
role = epoch = None
if run_id and 'Simulator.wksim_core.worker' in args:
    epoch = args[args.index('--epoch')+1]
    trace = Path(args[args.index('--trace')+1])
    if trace.parent.name == epoch and trace.parent.parent.parent.name == run_id:
        role = {'arducopter-truth.jsonl':'a', 'px4-truth.jsonl':'p'}.get(trace.name)
elif run_id and 'Simulator.wksim_runtime.joint_runtime' in args:
    index = args.index('Simulator.wksim_runtime.joint_runtime')
    directory, epoch = Path(args[index+1]), args[index+2]
    if directory.name == run_id: role = 's'
def assign_name():
    name = 'wk'+epoch[:11]+role
    Path('/proc/self/comm').write_text(name)
    assert Path('/proc/self/comm').read_text().strip() == name
    out = Path(os.environ['WKSIM_TRACE_HOOK_OUTPUT'])
    with (out/('name-'+role+'.json')).open('x') as stream:
        json.dump(dict(pid=os.getpid(),role=role,epoch=epoch,run_id=run_id,name=name,argv=args),stream)

if role and re.fullmatch('[0-9a-f]{32}', epoch or ''):
    if role == 's':
        # Name the main thread only after ROS/DDS initialization. Naming it at
        # interpreter startup makes its native helper threads inherit the same
        # comm and therefore prevents unambiguous kernel-TID correlation.
        previous_profile = sys.getprofile()
        def on_call(frame, event, argument):
            if (event == 'call' and frame.f_code.co_name == 'advance'
                    and frame.f_code.co_filename.endswith('/Simulator/wksim_core/joint.py')):
                sys.setprofile(previous_profile)
                assign_name()
        sys.setprofile(on_call)
    else:
        assign_name()
