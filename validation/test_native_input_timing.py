"""AP/PX4 native-input wait segmentation: offline checks with stub waits, not flight proof.

Covers the WKSIM_JOINT_CPU_TIMING-gated per-wait brackets added to
JointPhysics.finish_inputs. Default-off must add no clock reads or records; an
AP-only tick must not fabricate a PX4 wait; a boundary tick must attribute AP and
PX4 waits independently; an input timeout must still propagate with no false
success record. No SITL/UE/ROS is run; the native FC waits are stubbed.
"""
import unittest
from unittest.mock import patch

from Simulator.wksim_core.joint import JointPhysics, InputTimeout
from Simulator.wksim_runtime.scene_clock import SceneClock

JOINT = 'Simulator.wksim_core.joint'


def running_clock(tick):
    """Drive a real SceneClock to `tick`, committed but with its input not yet acked."""
    clock = SceneClock('a' * 32)
    for step in range(1, tick + 1):
        clock.begin_step()
        state = [0.] * 120
        state[2] = step / 1000
        state[60] = step * 1000
        clock.commit({name: dict(version=1, epoch=clock.epoch, tick=step, state=state)
                      for name in clock.VEHICLES})
        if step < tick:
            clock.acknowledge_ap(step)
            if step % 4 == 0:
                clock.barrier(step, step * 1000, True)
    return clock


class NativeInputTimingTests(unittest.TestCase):
    def physics(self, tick, cpu_timing):
        clock = running_clock(tick)
        p = object.__new__(JointPhysics)
        p.clock = clock
        p.health = lambda: None
        p.records = []
        p.record = lambda kind, **fields: p.records.append(dict(kind=kind, _tick=clock.tick, **fields))
        if cpu_timing is not None:
            p.cpu_timing = cpu_timing
        last_barrier_us = (tick - 1) // 4 * 4 * 1000
        p.px_time = last_barrier_us
        p.px_commands = [0.] * 16
        p.pending_ap = dict(frame=tick - 1, commands=[0.] * 16)  # force the AP wait
        p.inflight = dict(tick=tick, ap_source_frame=tick - 1,
                          px4_source_time_us=last_barrier_us,
                          model_ticks={name: tick for name in clock.VEHICLES})
        return p

    def stub_waits(self, p, tick, px4_fail=None, ap_fail=None):
        if ap_fail is not None:
            def wait_ap(previous, deadline=None):
                raise ap_fail
        else:
            def wait_ap(previous, deadline=None):
                return dict(frame=tick, commands=[0.] * 16)
        if px4_fail is not None:
            def wait_px4(deadline=None):
                raise px4_fail
        else:
            def wait_px4(deadline=None):
                p.px_time = tick * 1000
                return True
        p.wait_ap = wait_ap
        p.wait_px4 = wait_px4

    def kinds(self, p):
        return [row['kind'] for row in p.records]

    def test_disabled_by_default_reads_no_clock_and_keeps_behavior(self):
        tick = 8
        p = self.physics(tick, False)
        self.stub_waits(p, tick)
        with patch(JOINT + '.time.monotonic_ns') as wall, patch(JOINT + '.time.thread_time_ns') as cpu:
            p.finish_inputs()
            self.assertEqual(wall.call_count, 0)
            self.assertEqual(cpu.call_count, 0)
        self.assertNotIn('diagnostic_native_input_timing', self.kinds(p))
        # Behavior unchanged: AP acked, 4-tick barrier completed, step recorded.
        self.assertEqual(p.clock.last_input_tick, tick)
        self.assertEqual(p.clock.last_barrier, tick)
        self.assertTrue(p.clock.synchronized)
        self.assertIn('barrier', self.kinds(p))
        self.assertIn('step', self.kinds(p))

    def test_unset_cpu_timing_attribute_defaults_off(self):
        # Mirrors test_joint_input_deadline, which never sets cpu_timing.
        tick = 8
        p = self.physics(tick, None)
        self.stub_waits(p, tick)
        p.finish_inputs()
        self.assertNotIn('diagnostic_native_input_timing', self.kinds(p))
        self.assertEqual(p.clock.last_barrier, tick)

    def test_ap_only_tick_does_not_fabricate_px4_wait(self):
        tick = 5  # not a 4-tick boundary; slow enough to pass the >2ms gate
        p = self.physics(tick, True)
        self.stub_waits(p, tick)
        p.wait_px4 = lambda deadline=None: self.fail('PX4 wait must not run on an AP-only tick')
        with patch(JOINT + '.time.monotonic_ns', side_effect=[1_000_000, 4_500_000]), \
             patch(JOINT + '.time.thread_time_ns', side_effect=[100_000, 160_000]):
            p.finish_inputs()
        timing = [row for row in p.records if row['kind'] == 'diagnostic_native_input_timing']
        self.assertEqual(len(timing), 1)
        row = timing[0]
        self.assertEqual(row['_tick'], tick)
        self.assertEqual(len(row['waits']), 1)
        seg = row['waits'][0]
        self.assertEqual(seg['stack'], 'arducopter')
        self.assertEqual(seg['wall_ns'], 3_500_000)
        self.assertEqual(seg['thread_cpu_ns'], 60_000)
        self.assertEqual(seg['ap_frame'], tick)
        self.assertNotIn('px4', [s['stack'] for s in row['waits']])
        self.assertEqual(p.clock.last_barrier, 4)  # no boundary barrier on an AP-only tick

    def test_boundary_tick_separates_ap_and_px4_waits(self):
        tick = 8
        p = self.physics(tick, True)
        self.stub_waits(p, tick)
        wall = [1_000_000, 4_000_000, 6_000_000, 13_000_000]
        cpu = [100_000, 130_000, 200_000, 290_000]
        with patch(JOINT + '.time.monotonic_ns', side_effect=wall), \
             patch(JOINT + '.time.thread_time_ns', side_effect=cpu):
            p.finish_inputs()
        timing = [row for row in p.records if row['kind'] == 'diagnostic_native_input_timing']
        self.assertEqual(len(timing), 1)
        row = timing[0]
        self.assertEqual(row['_tick'], tick)
        self.assertEqual(row['native_wait_wall_ns'], 10_000_000)
        self.assertEqual(row['ap_source_frame'], tick - 1)
        self.assertEqual(row['px4_source_time_us'], 4_000)
        self.assertEqual([s['stack'] for s in row['waits']], ['arducopter', 'px4'])
        ap, px4 = row['waits']
        # Independent, sequential, non-overlapping brackets with their own thread CPU.
        self.assertEqual((ap['wall_start_ns'], ap['wall_end_ns'], ap['wall_ns']),
                         (1_000_000, 4_000_000, 3_000_000))
        self.assertEqual(ap['thread_cpu_ns'], 30_000)
        self.assertEqual(ap['ap_frame'], tick)
        self.assertEqual((px4['wall_start_ns'], px4['wall_end_ns'], px4['wall_ns']),
                         (6_000_000, 13_000_000, 7_000_000))
        self.assertEqual(px4['thread_cpu_ns'], 90_000)
        self.assertEqual(px4['px4_time_us'], tick * 1000)
        self.assertLessEqual(ap['wall_end_ns'], px4['wall_start_ns'])
        # The 4-tick barrier still completed with the held ack order.
        self.assertEqual(p.clock.last_barrier, tick)

    def test_fast_wait_below_gate_records_nothing(self):
        tick = 8  # not periodic (8 % 250 != 0) and total native wait < 2ms
        p = self.physics(tick, True)
        self.stub_waits(p, tick)
        wall = [1_000_000, 1_500_000, 2_000_000, 2_400_000]
        cpu = [100_000, 120_000, 200_000, 230_000]
        with patch(JOINT + '.time.monotonic_ns', side_effect=wall), \
             patch(JOINT + '.time.thread_time_ns', side_effect=cpu):
            p.finish_inputs()
        self.assertNotIn('diagnostic_native_input_timing', self.kinds(p))
        self.assertIn('step', self.kinds(p))  # the step itself still completed

    def test_periodic_tick_records_even_fast_waits(self):
        tick = 250  # 250 % 250 == 0, an AP-only tick (250 % 4 == 2)
        p = self.physics(tick, True)
        self.stub_waits(p, tick)
        with patch(JOINT + '.time.monotonic_ns', side_effect=[1_000_000, 1_100_000]), \
             patch(JOINT + '.time.thread_time_ns', side_effect=[100_000, 110_000]):
            p.finish_inputs()
        timing = [row for row in p.records if row['kind'] == 'diagnostic_native_input_timing']
        self.assertEqual(len(timing), 1)
        self.assertEqual([s['stack'] for s in timing[0]['waits']], ['arducopter'])
        self.assertEqual(timing[0]['waits'][0]['wall_ns'], 100_000)

    def test_ap_timeout_propagates_without_false_success(self):
        tick = 8
        p = self.physics(tick, True)
        self.stub_waits(p, tick, ap_fail=InputTimeout('arducopter', 5.))
        with patch(JOINT + '.time.monotonic_ns', side_effect=[1_000_000]), \
             patch(JOINT + '.time.thread_time_ns', side_effect=[100_000]):
            with self.assertRaises(InputTimeout):
                p.finish_inputs()
        # No segment, no step/barrier record: the failed wait is never reported as success.
        self.assertNotIn('diagnostic_native_input_timing', self.kinds(p))
        self.assertNotIn('step', self.kinds(p))
        self.assertNotIn('barrier', self.kinds(p))
        self.assertEqual(p.clock.last_barrier, 4)

    def test_px4_timeout_propagates_without_false_success(self):
        tick = 8
        p = self.physics(tick, True)
        self.stub_waits(p, tick, px4_fail=InputTimeout('px4', 5.))
        wall = [1_000_000, 4_000_000, 6_000_000]
        cpu = [100_000, 130_000, 200_000]
        with patch(JOINT + '.time.monotonic_ns', side_effect=wall), \
             patch(JOINT + '.time.thread_time_ns', side_effect=cpu):
            with self.assertRaises(InputTimeout):
                p.finish_inputs()
        self.assertNotIn('diagnostic_native_input_timing', self.kinds(p))
        self.assertNotIn('step', self.kinds(p))
        self.assertNotIn('barrier', self.kinds(p))
        # Fail-closed: the AP ack for this tick landed but the PX4 barrier did not.
        self.assertEqual(p.clock.last_input_tick, tick)
        self.assertEqual(p.clock.last_barrier, 4)


if __name__ == '__main__':
    unittest.main()
