import math,json
from unittest.mock import patch
from Simulator.wksim_runtime.pid_task import PIDTask,load_config,CONFIG_PATH
from Simulator.wksim_runtime.attitude_task import AttitudeTask
from prometheus_msgs.msg import UAVCommand
from rclpy.serialization import serialize_message
invalid=[True,False,'2',float('nan'),float('inf'),float('-inf'),complex(1,0)]
checks=0
for value in invalid:
 for kwargs in ({'position':(value,3.,3.)},{'position':(2.,3.,3.),'yaw':value},{'attitude':(0.,0.,value,.5)}):
  task=object.__new__(PIDTask);task.pid_measuring=False
  with patch.object(AttitudeTask,'command') as base:
   try: task.command('invalid',**kwargs)
   except ValueError: pass
   else: raise AssertionError(kwargs)
   base.assert_not_called();checks+=1
with patch.object(AttitudeTask,'command') as base:
 task.pid_measuring=True
 try: task.command('measured',position=(True,3.,3.))
 except RuntimeError: pass
 else: raise AssertionError('measurement guard')
 base.assert_not_called()
def run(method,kwargs):
 task=object.__new__(PIDTask);task.pid_measuring=False;task.command_number=0;task.Cmd=UAVCommand
 task.read_truth=lambda:{'time':1.};task.mark=lambda *a,**k:None;task.convert=lambda m:m;task.native_targets=[];sent=[]
 def send(msg,label):
  sent.append(bytes(serialize_message(msg)))
  if msg.move_mode==msg.XYZ_ATT:task.native_targets.append(dict(thrust=.5,quaternion_xyzw=[0.,0.,0.,1.],physical_time=1.))
 task.send=send;task.wait=lambda label,predicate,timeout:(_ for _ in ()).throw(AssertionError('missing target')) if not predicate() else None
 method(task,'compare',**kwargs);return sent
cfg=load_config(CONFIG_PATH)
for kwargs in ({'position':cfg['point']['position_enu_m'],'yaw':cfg['point']['yaw_rad']},{'attitude':(0.,0.,0.,.5)}):
 assert run(PIDTask.command,kwargs)==run(AttitudeTask.command,kwargs)
print(json.dumps({'invalid_scalar_cases_rejected_before_parent_send':checks,'measurement_guard_first':True,'default_pid_position_and_attitude_wire_bytes_unchanged':True}))
