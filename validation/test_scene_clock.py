"""Authority/state-boundary unit tests; real workers and FCs are separate gates."""
import unittest
import os
import sys
from pathlib import Path

from Simulator.wksim_runtime.scene_clock import SceneClock


class SceneClockTests(unittest.TestCase):
    def setUp(self):
        self.clock = SceneClock('a'*32)

    def responses(self, tick):
        state = [0.0]*120
        state[2], state[60] = tick/1000, tick*1000
        return {name: dict(version=1, epoch=self.clock.epoch, tick=tick, state=state[:])
                for name in self.clock.VEHICLES}

    def advance(self, count=4):
        for _ in range(count):
            tick = self.clock.begin_step()
            self.assertEqual(self.clock.commit(self.responses(tick)), tick*1_000_000)
            if tick % 4 == 0:
                self.clock.barrier(tick, tick*1000, True)

    def request(self, action, **fields):
        return self.clock.request(dict(version=1, epoch=self.clock.epoch,
                                       request_id=self.clock.last_request+1, action=action, **fields))

    def test_pause_single_macro_step_and_resume_have_no_implicit_physics(self):
        self.advance()
        self.request('pause')
        self.assertEqual(self.clock.tick, 4)
        with self.assertRaises(ValueError):
            self.clock.begin_step()
        self.request('step')
        self.advance()
        self.assertEqual((self.clock.tick, self.clock.phase), (8, 'paused'))
        with self.assertRaises(ValueError):
            self.clock.begin_step()
        self.request('resume')
        self.assertEqual(self.clock.tick, 8)
        self.advance()
        self.request('stop')
        self.assertEqual(self.clock.tick, 12)
        with self.assertRaises(ValueError):
            self.clock.begin_step()

    def test_partial_wrong_epoch_or_wrong_model_time_never_commits(self):
        for mutation in (lambda r: r.pop('px4'),
                         lambda r: r['px4'].update(epoch='b'*32),
                         lambda r: r['arducopter'].update(tick=True),
                         lambda r: r['px4']['state'].__setitem__(60, 2000),
                         lambda r: r['px4']['state'].__setitem__(1, float('nan'))):
            with self.subTest(mutation=mutation):
                self.setUp()
                self.clock.begin_step()
                responses = self.responses(1)
                mutation(responses)
                with self.assertRaises(ValueError):
                    self.clock.commit(responses)
                self.assertEqual((self.clock.tick, self.clock.phase), (0, 'faulted'))
                with self.assertRaises(ValueError):
                    self.request('resume')

    def test_action_envelope_cannot_cross_cold_epoch_or_replay(self):
        self.advance()
        request = dict(version=1, epoch=self.clock.epoch, request_id=1, action='pause')
        self.clock.request(request)
        before = self.clock.snapshot()
        with self.assertRaises(ValueError):
            self.clock.request(request)
        self.assertEqual(self.clock.snapshot(), before)
        self.request('stop')
        self.clock = SceneClock('b'*32)
        self.assertEqual(self.clock.tick, 0)
        with self.assertRaises(ValueError):
            self.clock.request(request)
        self.assertEqual((self.clock.tick, self.clock.last_request), (0, 0))

    def test_no_pause_inside_incomplete_input_boundary(self):
        self.advance(1)
        with self.assertRaises(ValueError):
            self.request('pause')
        self.assertEqual((self.clock.tick, self.clock.phase), (1, 'running'))
        self.assertEqual(self.clock.last_request, 1)

    def test_barrier_cannot_regress_or_release_an_extra_single_step(self):
        self.advance()
        with self.assertRaises(ValueError):
            self.clock.barrier(4, 3000, True)
        self.assertEqual((self.clock.tick, self.clock.phase), (4, 'faulted'))
        with self.assertRaises(ValueError):
            self.clock.begin_step()

    def test_next_macro_cannot_begin_before_the_previous_input_ack(self):
        for _ in range(4):
            tick = self.clock.begin_step()
            self.clock.commit(self.responses(tick))
        with self.assertRaisesRegex(ValueError, 'barrier'):
            self.clock.begin_step()
        self.clock.barrier(4, 4000, True)
        self.assertEqual(self.clock.begin_step(), 5)

    def test_only_completed_communication_fault_can_explicitly_recover(self):
        self.advance()
        tick=self.clock.begin_step()
        self.clock.commit(self.responses(tick))
        with self.assertRaises(ValueError):
            self.clock.suspend('agent_exit')
        self.clock.acknowledge_ap(5)
        frozen=self.clock.suspend('agent_exit')
        self.assertTrue(frozen['recoverable'])
        self.assertEqual((frozen['tick'],frozen['last_barrier_tick']),(5,4))
        with self.assertRaises(ValueError):
            self.request('resume')
        with self.assertRaises(ValueError):
            self.clock.begin_step()
        self.request('recover')
        self.assertEqual(self.clock.tick,5)
        self.assertEqual(self.clock.begin_step(),6)
        self.clock.fault('partial_model_timeout')
        with self.assertRaises(ValueError):
            self.request('recover')
        self.assertEqual(self.clock.tick,5)

    def test_input_fault_requires_exact_repair_before_explicit_recovery(self):
        self.advance()
        for tick in range(5,9):
            self.clock.begin_step();self.clock.commit(self.responses(tick))
            self.clock.acknowledge_ap(tick)
        frozen=self.clock.suspend_input('px4 input deadline')
        self.assertTrue(frozen['input_pending'])
        with self.assertRaises(ValueError): self.request('recover')
        with self.assertRaises(ValueError): self.clock.repair_input(8,7000)
        self.assertEqual(self.clock.tick,8)
        self.clock.repair_input(8,8000)
        self.assertEqual(self.clock.phase,'faulted')
        with self.assertRaises(ValueError): self.clock.begin_step()
        self.request('recover')
        self.assertEqual(self.clock.begin_step(),9)

    def test_partial_model_cannot_be_repaired_as_an_input_delay(self):
        self.advance()
        self.clock.begin_step()
        with self.assertRaises(ValueError): self.clock.suspend_input('model incomplete')
        self.clock.fault('model RPC timeout')
        with self.assertRaises(ValueError): self.clock.repair_input(5,4000)


@unittest.skipUnless(os.environ.get('WK_SCENE_ROS_TESTS') == '1', 'explicit private ROS test environment required')
class RosClockTests(unittest.TestCase):
    def test_paused_clock_can_reach_late_consumer_without_an_extra_physics_tick(self):
        import rclpy
        import time
        from rclpy.parameter import Parameter
        from Simulator.wksim_runtime.scene_clock import ClockPublisher
        rclpy.init()
        owner = rclpy.create_node('test_paused_clock_owner')
        publisher = ClockPublisher(owner)
        reader = None
        clock = SceneClock('c'*32)
        try:
            publisher.publish(clock)
            for _ in range(4):
                tick = clock.begin_step()
                state = [0.0]*120
                state[2], state[60] = tick/1000, tick*1000
                clock.commit({name:dict(version=1, epoch=clock.epoch, tick=tick, state=state)
                              for name in clock.VEHICLES})
                if tick == 4:
                    clock.barrier(4, 4000, True)
                publisher.publish(clock)
            clock.request(dict(version=1, epoch=clock.epoch, request_id=1, action='pause'))
            reader = rclpy.create_node('test_paused_clock_late_reader', parameter_overrides=[
                Parameter('use_sim_time', value=True)])
            until = time.monotonic()+.3
            while time.monotonic() < until:
                rclpy.spin_once(reader, timeout_sec=.01)
            self.assertEqual(reader.get_clock().now().nanoseconds, 0)  # Volatile clock has no retained sample.
            before = clock.snapshot()
            until = time.monotonic()+2
            while reader.get_clock().now().nanoseconds != 4_000_000 and time.monotonic() < until:
                publisher.publish(clock)  # Old implementation rejects this exact paused boundary.
                rclpy.spin_once(reader, timeout_sec=.02)
            self.assertEqual(reader.get_clock().now().nanoseconds, 4_000_000)
            self.assertEqual(clock.snapshot(), before)
            self.assertGreater(publisher.paused_republications, 0)
            self.assertEqual(publisher.publications, 5+publisher.paused_republications)
            clock.request(dict(version=1, epoch=clock.epoch, request_id=2, action='resume'))
            with self.assertRaises(ValueError):
                publisher.publish(clock)
            clock.request(dict(version=1, epoch=clock.epoch, request_id=3, action='pause'))
            clock.last_barrier = 0
            with self.assertRaises(ValueError):
                publisher.publish(clock)
            with self.assertRaises(ValueError):
                publisher.publish(SceneClock('d'*32))
        finally:
            if reader is not None:
                reader.destroy_node()
            publisher.close()
            owner.destroy_node()
            rclpy.shutdown()

    def test_private_tcp_listener_rebind_after_owned_connection_retires(self):
        import socket
        from contextlib import ExitStack
        from Simulator.wksim_runtime.isolation import check_isolation
        check_isolation()
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from probe_joint_clock import WireProbe
        for _ in range(2):
            with ExitStack() as stack:
                probe = WireProbe(stack, {}, [])
                self.assertEqual(probe.listener.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR), 1)
                with socket.create_connection(('127.0.0.1', 4581), timeout=1) as client:
                    connection, _ = probe.listener.accept()
                    connection.close()  # Retire the accepted end before rebinding its listener.
                    self.assertEqual(client.recv(1), b'')

    def test_real_ros_consumer_reporting_and_unique_owner(self):
        import rclpy
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from scene_clock_observer import SceneClockObservation
        clock = SceneClock('a'*32)

        class Probe:
            tick = property(lambda self: clock.tick)
            def log(self, stream, **fields):
                pass  # Unit fixture only; real probe retains all observations.

        rclpy.init()
        observer = None
        try:
            observer = SceneClockObservation(Probe(), clock)
            observer.pump()
            for _ in range(4):
                tick = clock.begin_step()
                state = [0.0]*120
                state[2], state[60] = tick/1000, tick*1000
                clock.commit({name: dict(version=1, epoch=clock.epoch, tick=tick, state=state)
                              for name in clock.VEHICLES})
                observer.publish()
            clock.barrier(4, 4000, True)
            self.assertEqual(observer.at_boundary(), 4_000_000)
            report = observer.report()  # Regression for the actual Humble graph API.
            self.assertEqual(report['publisher_count'], 1)
            self.assertEqual(report['publications'], 5)
            self.assertTrue(report['duplicate_owner_rejected'])
            self.assertTrue(report['ros_time_is_active'])
            self.assertTrue(any(name == '/clock' for name, _ in report['consumer_subscriptions']))
            clock.request(dict(version=1, epoch=clock.epoch, request_id=1, action='pause'))
            for _ in range(4):
                observer.pump()
                self.assertEqual(observer.last_ns, 4_000_000)
            with self.assertRaises(ValueError):
                observer.publisher.publish(SceneClock('b'*32))
        finally:
            if observer is not None:
                observer.close()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()
