"""Permission identity/replay/lifetime rules; no simulated FC acceptance."""
import json
import unittest
import os
import importlib.util

SCENE_AVAILABLE = importlib.util.find_spec('prometheus_control.scene') is not None
if SCENE_AVAILABLE:
    from prometheus_control.scene import SceneLease


@unittest.skipUnless(SCENE_AVAILABLE, 'Explicit new scene permission source/candidate required')
class SceneLeaseTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.lease = SceneLease('run', 'a'*32, lambda:self.now)
        self.value = dict(version=1, run_id='run', scene_epoch='a'*32, sequence=1,
            request_id=0, phase='running', tick=10000, time_ns=10000000000,
            issued_monotonic_s=self.now, lease_seconds=.5)

    def send(self, **values):
        self.value.update(values)
        return self.lease.accept(json.dumps(self.value))

    def test_missing_foreign_or_replayed_lease_cannot_grant_or_refresh(self):
        with self.assertRaisesRegex(ValueError, 'not_received'):
            self.lease.check()
        self.assertFalse(self.send(scene_epoch='b'*32))
        self.assertIsNone(self.lease.value)
        self.assertTrue(self.send(scene_epoch='a'*32))
        self.now += .51
        self.assertFalse(self.send())
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.lease.check()
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.send(sequence=2, issued_monotonic_s=self.now)

    def test_paused_heartbeat_cannot_manufacture_time_or_skip_request(self):
        self.send()
        with self.assertRaisesRegex(ValueError, 'without_new_request'):
            self.send(sequence=2, phase='paused')
        self.setUp(); self.send()
        self.send(sequence=2, request_id=1, phase='paused')
        with self.assertRaisesRegex(ValueError, 'without_step'):
            self.send(sequence=3, tick=10001, time_ns=10001000000)

    def test_explicit_four_step_resume_and_invalid_frames(self):
        self.send()
        self.send(sequence=2, request_id=1, phase='paused')
        self.send(sequence=3, request_id=2, phase='stepping')
        self.send(sequence=4, phase='paused', tick=10004, time_ns=10004000000)
        self.send(sequence=5, request_id=3, phase='resuming')
        self.send(sequence=6, phase='running', tick=10008, time_ns=10008000000)
        self.assertEqual(self.lease.check()['tick'], 10008)
        for field, value in (('version', True), ('phase', []), ('lease_seconds', 10),
                              ('issued_monotonic_s', float('nan')), ('issued_monotonic_s',10**600), ('time_ns', 0)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                bad = dict(self.value, sequence=7, **{field:value})
                self.lease.accept(json.dumps(bad))
        self.assertEqual(self.lease.check()['sequence'], 6)

    def test_new_recovery_request_is_not_automatic_heartbeat_revival(self):
        self.send()
        self.send(sequence=2,phase='faulted')
        with self.assertRaisesRegex(ValueError,'faulted'):
            self.lease.check()
        with self.assertRaises(ValueError):
            self.send(sequence=3,phase='running')
        with self.assertRaises(ValueError):
            self.send(sequence=3,phase='recovering')
        self.assertTrue(self.send(sequence=3,request_id=1,phase='recovering'))
        self.assertEqual(self.lease.check()['phase'],'recovering')
        self.send(sequence=4,phase='running',tick=10004,time_ns=10004000000)
        self.assertEqual(self.lease.check()['phase'],'running')
        self.send(sequence=5,phase='faulted')
        self.lease.error='scene_time_or_request_regressed'
        with self.assertRaises(ValueError):
            self.send(sequence=6,request_id=2,phase='recovering')

    def test_v2_retirement_scope_is_explicit_bounded_and_fault_bound(self):
        self.send(version=2,faulted_uav_ids=[])
        with self.assertRaisesRegex(ValueError,'scope'):
            self.send(sequence=2,faulted_uav_ids=[1])
        self.send(sequence=2,phase='faulted',faulted_uav_ids=[1])
        with self.assertRaises(ValueError): self.lease.check()
        self.send(sequence=3,request_id=1,phase='recovering')
        self.assertEqual(self.lease.check()['faulted_uav_ids'],[1])
        for invalid in ([True],[3],[1,1],{},None):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                self.lease.accept(json.dumps(dict(self.value,sequence=4,faulted_uav_ids=invalid)))


@unittest.skipUnless(SCENE_AVAILABLE and os.environ.get('WK_SCENE_ROS_TESTS') == '1', 'explicit isolated ROS environment')
class RealSceneNodeTests(unittest.TestCase):
    def test_native_hold_observation_does_not_enable_position_output_during_failsafe(self):
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from prometheus_control.node import ControlNode
        node=NS(scene=object(),scene_supervise=lambda:None,operation_time=lambda:1,
            operation=dict(stage='simple',action='mode',value='AUTO.LOITER'),revoked=True,
            native=NS(generation=0,failed=True,external_mode='OFFBOARD',send=Mock()),native_generation=0,
            state=NS(connected=True,odom_valid=False),advance=Mock(),
            processor=NS(control_state=0,update_state=Mock(),step=lambda:None,local_position=lambda:(0,0,0)),
            shaper=NS(shape=lambda *args:None),warmup_target=None,wall=lambda:1,last_output=0,output_period=.025)
        ControlNode.drive(node)
        node.advance.assert_called_once()
        node.native.send.assert_not_called()
        node.operation['value']='OFFBOARD'
        with self.assertRaisesRegex(ValueError,'failsafe'):
            ControlNode.drive(node)

    def test_retired_discovery_entry_does_not_admit_unknown_active_writers(self):
        from types import SimpleNamespace as NS
        from prometheus_control.node import ControlNode
        old,new,foreign=(bytes([value])*16 for value in (1,2,3))
        writers=[NS(endpoint_gid=old),NS(endpoint_gid=new)]
        node=NS(native=NS(subscriptions=[NS(topic_name='/ap/status')]),retired_native_endpoints=set(),
                get_publishers_info_by_topic=lambda topic:writers)
        with self.assertRaises(ValueError): ControlNode.scene_endpoints(node)
        node.retired_native_endpoints.add(old.hex())
        self.assertEqual(ControlNode.scene_endpoints(node),{'/ap/status':new.hex()})
        writers.append(NS(endpoint_gid=foreign))
        with self.assertRaises(ValueError): ControlNode.scene_endpoints(node)

    def test_fault_recovery_never_reactivates_control_without_fresh_ready_state(self):
        import rclpy
        from std_msgs.msg import String
        from prometheus_control.node import ControlNode
        rclpy.init(args=['--ros-args','-p','flight_stack:=px4','-p','run_id:=scene-recover-test',
                        '-p','use_sim_time:=true','-p','scene_epoch:='+'c'*32])
        node=None
        try:
            node=ControlNode()
            def send(sequence,request_id,phase):
                node.on_scene(String(data=json.dumps(dict(version=1,run_id='scene-recover-test',
                    scene_epoch='c'*32,sequence=sequence,request_id=request_id,phase=phase,
                    tick=10000,time_ns=10000000000,issued_monotonic_s=node.wall(),lease_seconds=.5))))
            send(1,0,'running'); send(2,0,'faulted')
            self.assertTrue(node.revoked)
            send(3,0,'running')
            self.assertEqual(node.scene.value['phase'],'faulted')
            send(4,1,'recovering')
            self.assertIsNotNone(node.scene_recovery)
            self.assertTrue(node.revoked)
            node.tick()
            self.assertFalse(node.scene_recovery['ready'])
            self.assertIsNone(node.native.pending)
            send(5,1,'running')
            self.assertTrue(node.revoked)
            with self.assertRaises(ValueError):
                node.scene.check()
        finally:
            if node is not None: node.destroy_node()
            rclpy.shutdown()

    def test_scene_control_topics_construct_and_invalid_pause_never_grants_freshness(self):
        import rclpy
        from std_msgs.msg import String
        from prometheus_control.node import ControlNode
        from prometheus_control.scene import TOPIC
        rclpy.init(args=['--ros-args', '-p', 'flight_stack:=px4', '-p', 'run_id:=scene-node-test',
                        '-p', 'use_sim_time:=true', '-p', 'scene_epoch:='+'b'*32])
        node = None
        try:
            node = ControlNode()
            self.assertEqual(node.scene_ack.topic_name, TOPIC+'/control/uav1')
            with self.assertRaisesRegex(ValueError, 'native_state_writer'):
                node.scene_endpoints()
            node.on_scene(String(data=json.dumps(dict(version=1, run_id='scene-node-test',
                scene_epoch='b'*32, sequence=1, request_id=1, phase='paused', tick=10000,
                time_ns=10000000000, issued_monotonic_s=node.wall(), lease_seconds=.5))))
            self.assertIsNone(node.scene_hold)
            self.assertTrue(node.revoked)
            self.assertFalse(node.frozen_native_fresh('position', 0.))
        finally:
            if node is not None:
                node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()
