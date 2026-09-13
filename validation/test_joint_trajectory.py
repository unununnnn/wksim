"""Formal trajectory wiring and fail-closed boundaries; no flight evidence."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from Simulator.wksim_runtime.config import ConfigError
from Simulator.wksim_runtime.evidence import write_json
from Simulator.wksim_runtime.joint_actions import Mailbox
from Simulator.wksim_runtime.joint_config import FIXED_TASKS,validate_joint_config
from Simulator.wksim_runtime.joint_evidence import verify_tasks
from Simulator.wksim_runtime.joint_task import JointTask,JointPVTask,JointMixedTask,task_class
from Simulator.wksim_runtime.joint_trajectory import RECORDER,coordinate_legs,supported_actions,validate_initialized
from Simulator.wksim_runtime.runtime import launch_spec
from Simulator.wksim_runtime.task import Task
from tools.pv_trajectory_task import PVTask
from tools.mixed_control_task import MixedTask


class JointTrajectoryTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('WKSIM_TEST_PRIVATE_ROS')=='1','requires isolated generated ROS messages')
    def test_real_formal_monitor_probe_graph_and_scene_lease(self):
        import rclpy
        from Simulator.wksim_runtime.joint_monitor import JointMonitor
        from tools.pv_trajectory_task import PVProbe
        from wksim_msgs.msg import SetupRequest,CommandRequest
        self.assertNotEqual(os.readlink('/proc/self/ns/net'),os.readlink('/proc/1/ns/net'))
        rclpy.init(args=[])
        nodes=[];resources=[]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);clock=NS(epoch='a'*32,tick=0)
                supervisor=rclpy.create_node(RECORDER);nodes.append(supervisor)
                monitor=JointMonitor(supervisor,root,clock);resources.append(monitor)
                probe=PVProbe(supervisor,clock,root,time.monotonic());resources.append(probe)
                controller=rclpy.create_node('wksim_joint_arducopter_control');nodes.append(controller)
                controller.create_subscription(SetupRequest,'/uav1/prometheus/v2/setup',lambda m:None,1)
                controller.create_subscription(CommandRequest,'/uav1/prometheus/v2/command',lambda m:None,1)
                task=JointPVTask(root,lambda:None,lambda p:None,'arducopter',run_id='formal-graph',
                    protocol='session_v1',uav_id=1,use_sim_time=True,scene_epoch=clock.epoch,trajectory_epoch=clock.epoch)
                resources.append(task)
                deadline=time.monotonic()+5
                while not task.request_graph_ready() and time.monotonic()<deadline:
                    rclpy.spin_once(task.node,timeout_sec=.02)
                self.assertTrue(task.request_graph_ready())
                self.assertIsNotNone(task.scene_lease)
                self.assertEqual(task.scene_lease.epoch,clock.epoch)
                self.assertEqual(task.sent,[])
                # Extra observer must fail even though both approved names remain.
                extra=rclpy.create_node('unexpected_recorder');nodes.append(extra)
                extra.create_subscription(SetupRequest,task.topic_root+'v2/setup',lambda m:None,1)
                deadline=time.monotonic()+5
                while task.setup_pub.get_subscription_count()!=3 and time.monotonic()<deadline:
                    rclpy.spin_once(task.node,timeout_sec=.02)
                self.assertEqual(task.setup_pub.get_subscription_count(),3)
                self.assertFalse(task.request_graph_ready())
                for resource in reversed(resources):resource.close()
                resources.clear()
        finally:
            for resource in reversed(resources):resource.close()
            for node in reversed(nodes):node.destroy_node()
            rclpy.shutdown()

    def test_fixed_profile_and_timing_reject_before_runtime(self):
        base=dict(schema_version=1,kind='joint_scene',run_id='formal-pv',runtime_profile='joint_quad_dds_mixed_pv_v1')
        for task in FIXED_TASKS:
            config=dict(base,task=task)
            self.assertEqual(validate_joint_config(config)['task_dwell_seconds'],{'hold':5,'waypoint':2})
            for fields in ({'runtime_profile':'joint_quad_dds_v1'},{'requested_rate':1},
                           {'task_dwell_seconds':{'hold':6}},{'task_dwell_seconds':{'waypoint':3}}):
                with self.subTest(task=task,fields=fields),self.assertRaises(ConfigError):
                    validate_joint_config(dict(config,**fields))
        legacy=validate_joint_config(dict(base,runtime_profile='joint_quad_dds_v1',task='public_position',
                                         requested_rate=1,task_dwell_seconds={'hold':35,'waypoint':35}))
        self.assertEqual(legacy['requested_rate'],1)

    def test_launch_flags_only_from_admission_and_only_for_ap(self):
        config=dict(stack='arducopter',dds_workspace='/dds',px4_root='/px4',ap_candidate='/ap',run_id='test',
                    arducopter_pv_profile=FIXED_TASKS[0],arducopter_mixed_profile=FIXED_TASKS[1])
        def plan(stack,caps=()):
            return launch_spec(dict(config,stack=stack),Path('/run'),Path('/model.so'),admitted_capabilities=caps)['control']
        self.assertFalse(any('arducopter_pv_profile:=' in value or 'arducopter_mixed_profile:=' in value for value in plan('arducopter')))
        argv=plan('arducopter',FIXED_TASKS)
        self.assertEqual(argv.count('arducopter_pv_profile:='+FIXED_TASKS[0]),1)
        self.assertEqual(argv.count('arducopter_mixed_profile:='+FIXED_TASKS[1]),1)
        self.assertFalse(any('arducopter_pv_profile:=' in value or 'arducopter_mixed_profile:=' in value for value in plan('px4',FIXED_TASKS)))

    def test_diamond_uses_original_executor_and_formal_dwell_and_scene_lease(self):
        for cls,executor in ((JointPVTask,PVTask),(JointMixedTask,MixedTask)):
            self.assertIs(cls.execute,PVTask.execute)
            self.assertIs(cls.fly_leg,executor.fly_leg)
            self.assertIs(cls.dwell,JointTask.dwell)
            self.assertEqual(cls.__mro__.count(Task),1)
            with patch.object(Task,'__init__',return_value=None) as init:
                task=cls(Path('/task'),None,None,'arducopter',trajectory_epoch='a'*32,scene_epoch='a'*32,
                         run_id='run',protocol='session_v1',use_sim_time=True)
                self.assertEqual(init.call_args.kwargs['scene_epoch'],'a'*32)
                self.assertTrue(init.call_args.kwargs['use_sim_time'])
                self.assertEqual(task.scene_epoch,'a'*32)
                self.assertEqual(task.recorder_name,RECORDER)
        self.assertIs(task_class('public_position'),JointTask)
        self.assertEqual(PVTask.recorder_name,'wksim_joint_flight_clock')

    def test_named_graph_requires_two_unique_live_endpoints(self):
        task=JointPVTask.__new__(JointPVTask)
        task.flight_stack,task.uav_id='arducopter',1
        endpoints=[NS(node_name='wksim_joint_arducopter_control',node_namespace='/',endpoint_gid=[1]*16),
                   NS(node_name=RECORDER,node_namespace='/',endpoint_gid=[2]*16)]
        task.node=NS(get_subscriptions_info_by_topic=lambda name:endpoints)
        task.setup_pub=task.command_pub=NS(get_subscription_count=lambda:len(endpoints))
        self.assertTrue(task.request_graph_ready())
        settings=dict(task_type=FIXED_TASKS[0],run_id='run',epoch='a'*32,stack='arducopter',token='b'*32)
        record=dict(version=1,run_id='run',epoch='a'*32,stack='arducopter',token='b'*32,
                    control_subscriptions=[2,2],request_graph=task.pv_request_graph)
        validate_initialized(record,settings)
        for field,value in (('node_name','wksim_joint_flight_clock'),('endpoint_gid',[1]*16),('endpoint_gid',[0]*16),
                            ('node_namespace','/other')):
            old=getattr(endpoints[1],field);setattr(endpoints[1],field,value)
            self.assertFalse(task.request_graph_ready())
            setattr(endpoints[1],field,old)
        endpoints.pop()
        self.assertFalse(task.request_graph_ready())
        invalid=copy.deepcopy(record);invalid['request_graph']['command'][1]['endpoint_gid']='01'*16
        with self.assertRaises(ValueError):validate_initialized(invalid,settings)
        legacy=dict(settings,task_type='public_position')
        with self.assertRaises(ValueError):validate_initialized(record,legacy)

    def test_fixed_lifecycle_rejected_before_acceptance(self):
        actions=['start-task','pause','step','resume','recover','start-recovery-task','set-rate','stop','cold-reset']
        for task in FIXED_TASKS:
            allowed=supported_actions(task,actions)
            self.assertEqual(allowed,['start-task','stop','cold-reset'])
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'actions').mkdir()
                mailbox=Mailbox(root,'run','a'*32)
                for number,action in enumerate(set(actions)-set(allowed),1):
                    token=f'{number:032x}'
                    request=dict(version=1,run_id='run',epoch='a'*32,command_id=number,action=action,
                                 offer_token='b'*32,token=token)
                    if action=='set-rate':request['requested_rate']=.5
                    write_json(root/'actions'/f'{number:020d}-{token}.json',request)
                    self.assertIsNone(mailbox.poll('b'*32,allowed))
                    self.assertEqual(json.loads((mailbox.results/(token+'.json')).read_text())['state'],'rejected')
        self.assertEqual(supported_actions('public_position',actions),actions)
        self.assertIsNone(verify_tasks(None,'a'*32,0,{},FIXED_TASKS[0],formal_result={'status':'cold_reset'}))

    def test_trajectory_go_requires_explicit_formal_start_and_both_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run='run';epoch='a'*32
            with self.assertRaises(FileNotFoundError):coordinate_legs(root,run,epoch,100)
            initial={}
            for stack,uid in (('arducopter',1),('px4',2)):
                (root/stack).mkdir()
                initial[stack]=dict(version=1,run_id=run,epoch=epoch,uav_id=uid,control_epoch=str(uid)*32,
                                    request_high_water=0,token=str(uid+2)*32)
                write_json(root/stack/'ready.json',initial[stack])
                write_json(root/stack/'pv-ready-1.json',dict(version=1,profile=FIXED_TASKS[0],leg=1,run_id=run,
                    scene_epoch=epoch,uav_id=uid,control_epoch=str(uid)*32,token=str(uid+4)*32,position=[2.,3.,3.],yaw=0.))
            write_json(root/'go.json',dict(run_id=run,epoch=epoch,tasks=initial))
            coordinate_legs(root,run,epoch,101)
            self.assertFalse((root/'pv-go-1.json').exists())
            path=root/'px4/pv-ready-1.json';offer=json.loads(path.read_text())
            write_json(path,dict(offer,control_epoch='0'*32))
            with self.assertRaises(ValueError):coordinate_legs(root,run,epoch,100)
            self.assertFalse((root/'pv-go-1.json').exists())
            write_json(path,offer)
            coordinate_legs(root,run,epoch,100)
            first=json.loads((root/'pv-go-1.json').read_text())
            self.assertEqual(first['issued_tick'],100)
            self.assertEqual(first['start_ns'],1_100_000_000)
            for stack in initial:
                ready=json.loads((root/stack/'pv-ready-1.json').read_text())
                write_json(root/stack/'pv-ready-2.json',dict(ready,leg=2))
            with self.assertRaises(ValueError):coordinate_legs(root,run,epoch,200)
            self.assertFalse((root/'pv-go-2.json').exists())
            coordinate_legs(root,run,epoch,201)
            self.assertEqual(json.loads((root/'pv-go-1.json').read_text()),first)


if __name__=='__main__':unittest.main()
