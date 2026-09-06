"""Real installed ROS node + owned SIGTERM; no FC, Agent or flight commands."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid


@unittest.skipUnless(os.environ.get('WKSIM_JOINT_CONTROL_TESTS')=='1','explicit candidate/private namespace required')
class ShutdownTests(unittest.TestCase):
    def test_sigterm_during_real_publish_does_not_invalidate_callback_context(self):
        from Simulator.wksim_runtime.isolation import check_isolation
        check_isolation()
        root=Path(tempfile.mkdtemp(prefix='wksim-control-stop-window-'))
        marker=root/'publishing'
        print('Evidence: '+str(root),flush=True)
        program=('import pathlib,time; from types import SimpleNamespace; '
                 'import prometheus_control.node as module\n'
                 'Original=module.ControlNode\n'
                 'class Instrumented(Original):\n'
                 ' def __init__(self):\n'
                 '  super().__init__()\n'
                 '  publisher=self.state_pub\n'
                 '  def publish(message):\n'
                 '   pathlib.Path('+repr(str(marker))+').touch()\n'
                 '   time.sleep(.2)\n'
                 '   publisher.publish(message)\n'
                 '  self.state_pub=SimpleNamespace(publish=publish)\n'
                 'module.ControlNode=Instrumented\nmodule.main()\n')
        with (root/'node.log').open('x') as log:
            child=subprocess.Popen([sys.executable,'-B','-c',program,'--ros-args','-p','flight_stack:=px4',
                                    '-p','run_id:=stop-window-'+uuid.uuid4().hex],
                                   stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
            record=dict(pid=child.pid,pgid=os.getpgid(child.pid),
                        start_stat=Path(f'/proc/{child.pid}/stat').read_text(),
                        instrumentation='test-only 200ms delay before real state publisher; no FC')
            try:
                limit=time.monotonic()+8
                while not marker.exists():
                    self.assertIsNone(child.poll())
                    self.assertLess(time.monotonic(),limit)
                    time.sleep(.001)
                child.terminate()
                code=child.wait(timeout=3)
            finally:
                if child.poll() is None: child.kill();child.wait(timeout=3)
                record.update(returncode=child.returncode,pid_absent=not Path(f'/proc/{child.pid}').exists())
                (root/'result.json').write_text(json.dumps(record,indent=2)+'\n')
        self.assertEqual(code,0,(root/'node.log').read_text())

    def test_repeated_sigterm_exits_normally_without_context_race(self):
        from Simulator.wksim_runtime.isolation import check_isolation
        check_isolation()
        source=Path(importlib.util.find_spec('prometheus_control.node').origin)
        root=Path(tempfile.mkdtemp(prefix='wksim-control-stop-'))
        print('Evidence: '+str(root),flush=True)
        rows=[]
        for index,delay in enumerate((.0,.005,.009,.015,.027,.044,.071,.13,.19,.25,.31,.41)):
            logfile=root/(str(index)+'.log')
            with logfile.open('x') as log:
                child=subprocess.Popen([sys.executable,'-B','-m','prometheus_control.node','--ros-args',
                    '-p','flight_stack:=px4','-p','run_id:=shutdown-'+uuid.uuid4().hex],
                    stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                row=dict(pid=child.pid,pgid=os.getpgid(child.pid),delay_s=delay,
                         start_stat=Path(f'/proc/{child.pid}/stat').read_text())
                rows.append(row)
                try:
                    limit=time.monotonic()+8
                    while '"event": "started"' not in logfile.read_text():
                        self.assertIsNone(child.poll(),'Node exited during setup')
                        self.assertLess(time.monotonic(),limit,'Node setup timeout')
                        time.sleep(.005)
                    time.sleep(delay)
                    child.terminate()
                    row['returncode']=child.wait(timeout=3)
                finally:
                    if child.poll() is None:
                        child.kill();child.wait(timeout=3)
                    row['returncode']=child.returncode
                    row['pid_absent']=not Path(f'/proc/{child.pid}').exists()
            (root/'result.json').write_text(json.dumps(dict(source=str(source),
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),children=rows),indent=2)+'\n')
        self.assertTrue(all(row['pid_absent'] for row in rows))
        self.assertEqual([row['returncode'] for row in rows],[0]*len(rows))


if __name__=='__main__':unittest.main()
