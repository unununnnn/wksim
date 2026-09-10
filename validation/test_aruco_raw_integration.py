"""A passive raw subscriber must have the expected owner, GID and namespace."""
import copy
from types import SimpleNamespace as S
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime.aruco_joint_task import JointArUcoTask
from Simulator.wksim_runtime.joint_aruco_profile import TASK
from Simulator.wksim_runtime.joint_trajectory import validate_initialized


class RawIntegrationTests(unittest.TestCase):
    def make_task(self):
        task=JointArUcoTask.__new__(JointArUcoTask)
        task.flight_stack='px4';task.uav_id=2
        task.setup_pub=task.command_pub=S(get_subscription_count=lambda:2)
        endpoints=[S(node_name='wksim_joint_px4_control',node_namespace='/',endpoint_gid=b'1'*24),
                   S(node_name='wksim_aruco_raw_px4',node_namespace='/',endpoint_gid=b'2'*24)]
        task.node=S(get_subscriptions_info_by_topic=lambda topic:endpoints)
        return task,endpoints

    def test_exact_owner_and_distinct_gid_required(self):
        task,endpoints=self.make_task()
        self.assertTrue(task.request_graph_ready())
        for key,value in [('node_name','another_recorder'),('node_namespace','/foreign'),
                          ('endpoint_gid',b'\0'*24),('endpoint_gid',b'1'*24)]:
            previous=getattr(endpoints[1],key);setattr(endpoints[1],key,value)
            self.assertFalse(task.request_graph_ready(),(key,value))
            setattr(endpoints[1],key,previous)
        endpoints.append(S(node_name='third',node_namespace='/',endpoint_gid=b'3'*24))
        self.assertFalse(task.request_graph_ready())

    def test_supervisor_checks_same_recorded_graph(self):
        task,_=self.make_task();task.request_graph_ready()
        settings=dict(run_id='aruco-test',epoch='a'*32,stack='px4',token='b'*32,task_type=TASK)
        record=dict(version=1,run_id=settings['run_id'],epoch=settings['epoch'],stack='px4',
                    token=settings['token'],control_subscriptions=[2,2],request_graph=task.aruco_request_graph)
        validate_initialized(record,settings)
        bad=copy.deepcopy(record);bad['request_graph']['setup'][1]['node_name']='wksim_joint_supervisor'
        with self.assertRaises(ValueError):validate_initialized(bad,settings)
        bad=copy.deepcopy(record);bad['control_subscriptions']=[1,1]
        with self.assertRaises(ValueError):validate_initialized(bad,settings)

    def test_task_pump_drains_on_both_sides_and_propagates_failure(self):
        task,_=self.make_task();calls=[]
        task.raw_capture=S(drain=lambda:calls.append('raw'))
        with patch('Simulator.wksim_runtime.task.Task.pump',side_effect=lambda:calls.append('pump')):
            task.pump()
        self.assertEqual(calls,['raw','pump','raw'])
        task.raw_capture=S(drain=lambda:(_ for _ in ()).throw(OSError('disk full')))
        with self.assertRaises(OSError):task.pump()


if __name__=='__main__':unittest.main()
