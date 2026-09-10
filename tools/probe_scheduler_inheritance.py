"""Observe scheduler inheritance in this disposable process, its child and thread only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading


def probe():
    original=os.sched_getscheduler(0);priority=os.sched_getparam(0)
    rows=[]
    try:
        for reset in (False,True):
            policy=os.SCHED_FIFO|(os.SCHED_RESET_ON_FORK if reset else 0)
            os.sched_setscheduler(0,policy,os.sched_param(50))
            row=dict(reset_on_fork=reset,parent_policy=os.sched_getscheduler(0),
                     parent_priority=os.sched_getparam(0).sched_priority)
            code='import os,json;print(json.dumps(dict(policy=os.sched_getscheduler(0),priority=os.sched_getparam(0).sched_priority)))'
            row['child']=json.loads(subprocess.check_output([sys.executable,'-c',code],text=True,timeout=5))
            def read_thread():
                row['thread']=dict(policy=os.sched_getscheduler(0),priority=os.sched_getparam(0).sched_priority)
            thread=threading.Thread(target=read_thread);thread.start();thread.join(timeout=5)
            if thread.is_alive():raise TimeoutError('Own probe thread did not retire')
            rows.append(row)
    finally:os.sched_setscheduler(0,original,priority)
    return dict(scope='Own short-lived process only; no ROS/FC/physics',rows=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=probe()
    with args.output.open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result))
