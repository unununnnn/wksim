"""Deterministic rate boundary tests, not a substitute for real FC acceptance."""
import tempfile
import time
import unittest
from pathlib import Path

from Simulator.wksim_runtime.joint_rate import JointRate,RateUnmet,LATE_LIMIT_NS
from Simulator.wksim_runtime.joint_config import validate_joint_config
from Simulator.wksim_runtime.joint_actions import validate_request,submit,Mailbox
from Simulator.wksim_runtime.evidence import write_json
from Simulator.wksim_runtime.joint_task import JointTask
from tools.benchmark_joint_rate_release import simulate_creep


class FakeWall:
    def __init__(self): self.ns=1_000_000_000
    def now(self): return self.ns
    def sleep(self,seconds): self.ns+=round(seconds*1e9)


class RateTests(unittest.TestCase):
    def rate(self,value=.5):
        self.wall=FakeWall();self.events=[]
        rate=JointRate('a'*32,value,lambda kind,**row:self.events.append(dict(kind=kind,**row)),
                       self.wall.now,self.wall.sleep)
        rate.reanchor(4,'test')
        return rate

    def test_no_catchup_and_cumulative_lateness(self):
        rate=self.rate()
        for group in range(20):
            rate.begin_group(4+group*4,lambda:None)
            self.wall.ns+=10_000_000
            rate.end_group(8+group*4)
        starts=[row for row in self.events if row['kind']=='rate_group_start']
        self.assertTrue(all(b['actual_start_ns']-a['actual_start_ns']>=8_000_000 for a,b in zip(starts,starts[1:])))
        self.assertEqual(rate.worst_lateness_ns,40_000_000)
        self.assertEqual(len([row for row in self.events if row['kind']=='rate_anchor']),1)

    def test_fast_physics_waits_for_wall_period_without_changing_ticks(self):
        class TickingWall(FakeWall):
            def now(self):
                value=self.ns;self.ns+=1000
                return value
        wall=TickingWall();events=[];checks=[]
        rate=JointRate('a'*32,.5,lambda kind,**row:events.append(dict(kind=kind,**row)),wall.now,wall.sleep)
        rate.reanchor(4,'test')
        for index in range(4):
            rate.begin_group(4+index*4,lambda:checks.append(wall.ns))
            wall.ns+=1_000_000
            rate.end_group(8+index*4)
        starts=[row['actual_start_ns'] for row in events if row['kind']=='rate_group_start']
        self.assertTrue(all(b-a>=8_000_000 for a,b in zip(starts,starts[1:])))
        self.assertEqual(rate.completed,4)
        self.assertGreater(len(checks),4)

    def test_strict_over_100ms_and_completed_barrier(self):
        rate=self.rate(1)
        rate.begin_group(4,lambda:None)
        self.wall.ns+=4_000_000+LATE_LIMIT_NS
        rate.end_group(8)  # Exactly 100ms is permitted.
        self.assertFalse(rate.latched)
        self.wall.ns+=1
        with self.assertRaises(RateUnmet): rate.begin_group(8,lambda:None)
        self.assertEqual(rate.completed,1)
        self.assertIsNone(rate.group)
        with self.assertRaises(ValueError): rate.set_rate(.5,'escape',8)
        with self.assertRaises(ValueError): rate.reanchor(8,'escape')
        rate.reanchor(8,'recover_requested',recovery=True,transition=True)
        self.assertFalse(rate.latched)

    def test_wait_oversleep_fails_before_the_next_group_or_physics(self):
        class AdvancingWall(FakeWall):
            def now(self):
                self.ns+=1000
                return self.ns
            def sleep(self,seconds):
                self.ns+=round(seconds*1e9)+150_000_000
        wall=AdvancingWall();events=[]
        rate=JointRate('a'*32,.5,lambda kind,**fields:events.append(kind),wall.now,wall.sleep)
        rate.reanchor(4,'test')
        rate.begin_group(4,lambda:None);wall.ns+=1_000_000;rate.end_group(8)
        with self.assertRaises(RateUnmet): rate.begin_group(8,lambda:None)
        self.assertTrue(rate.latched)
        self.assertIsNone(rate.group)
        self.assertEqual(rate.completed,1)
        self.assertEqual(events.count('rate_group_start'),1)

    def test_slow_group_faults_only_after_complete_four_ticks(self):
        rate=self.rate()
        rate.begin_group(4,lambda:None)
        self.wall.ns+=109_000_000
        with self.assertRaises(RateUnmet): rate.end_group(8)
        self.assertEqual(rate.completed,1)
        self.assertEqual(self.events[-2]['kind'],'rate_group_end')
        self.assertEqual(self.events[-1]['kind'],'rate_unmet')

    def test_rate_change_cannot_discard_unchecked_boundary_lateness(self):
        rate=self.rate(1)
        rate.begin_group(4,lambda:None)
        self.wall.ns+=4_000_000;rate.end_group(8)
        self.wall.ns+=LATE_LIMIT_NS+1
        with self.assertRaises(RateUnmet): rate.set_rate(.5,'late-change',8)
        self.assertEqual(rate.requested_rate,1)
        self.assertEqual(rate.request_id,'config')
        self.assertEqual(rate.completed,1)
        self.assertTrue(rate.latched)
        sample=self.events[-2]
        self.assertEqual(sample['kind'],'rate_boundary_check')
        self.assertEqual(sample['boundary_tick'],8)
        self.assertEqual(sample['actual_check_ns']-sample['ideal_boundary_ns'],LATE_LIMIT_NS+1)

    def test_transition_confirmation_cannot_discard_boundary_lateness(self):
        for reason in ('resume_confirmed','recover_confirmed','start-recovery-task'):
            with self.subTest(reason=reason):
                rate=self.rate(1)
                rate.begin_group(4,lambda:None)
                self.wall.ns+=4_000_000;rate.end_group(8)
                self.wall.ns+=LATE_LIMIT_NS+1
                with self.assertRaises(RateUnmet): rate.reanchor(8,reason)
                self.assertEqual(rate.segment_id,1)
                self.assertTrue(rate.latched)

    def test_start_recovery_task_anchor_resets_segment_but_not_budgets(self):
        # Approved 2026-09-07 amendment: the storm segment starts at zero, but
        # the unchanged 100ms budget still applies inside it.
        rate=self.rate()
        rate.begin_group(4,lambda:None);self.wall.ns+=8_000_000;rate.end_group(8)
        self.assertEqual(rate.worst_lateness_ns,0)
        rate.reanchor(8,'start-recovery-task',transition=True)
        self.assertEqual(rate.segment_id,2)
        self.assertTrue(rate.anchor['transition'])
        self.assertEqual(rate.worst_lateness_ns,0)
        self.assertIn('rate_segment_end',[event['kind'] for event in self.events])
        anchor=[event for event in self.events if event['kind']=='rate_anchor'][-1]
        self.assertEqual(anchor['reason'],'start-recovery-task')
        self.wall.ns+=LATE_LIMIT_NS+1
        with self.assertRaises(RateUnmet): rate.begin_group(8,lambda:None)
        self.assertTrue(rate.latched)

    def test_pause_boundary_checks_exact_budget_and_excludes_paused_wall_time(self):
        rate=self.rate(1)
        rate.begin_group(4,lambda:None)
        self.wall.ns+=4_000_000;rate.end_group(8)
        self.wall.ns+=LATE_LIMIT_NS
        rate.check_boundary(8)
        self.wall.ns+=1
        with self.assertRaises(RateUnmet): rate.check_boundary(8)
        rate.close_segment('fault',8)
        rate.reanchor(8,'recover_requested',transition=True,recovery=True)
        rate.check_boundary(8)
        rate.close_segment('pause',8)
        self.wall.ns+=60_000_000_000
        rate.check_boundary(8)
        rate.reanchor(8,'resume_requested',transition=True)
        self.assertFalse(rate.latched)

    def test_pause_step_resume_change_discard_old_plan(self):
        rate=self.rate()
        rate.begin_group(4,lambda:None);self.wall.ns+=1_000_000;rate.end_group(8)
        rate.close_segment('pause',8)
        self.wall.ns+=4_000_000_000
        rate.set_rate(1,'new-command',12)  # Unpaced single step completed tick 12.
        rate.reanchor(12,'resume_requested',transition=True)
        rate.begin_group(12,lambda:None)
        self.assertEqual(rate.group['actual_start_ns'],rate.group['ideal_start_ns'])
        self.wall.ns+=1_000_000;rate.end_group(16)
        rate.reanchor(16,'resume_confirmed')
        self.assertEqual(rate.request_id,'new-command')
        self.assertEqual(rate.worst_lateness_ns,0)
        self.assertFalse(rate.anchor['transition'])

    def test_configuration_and_action_envelopes_are_strict(self):
        base=dict(schema_version=1,kind='joint_scene',run_id='rate',runtime_profile='joint_quad_dds_v1')
        self.assertEqual(validate_joint_config(base)['requested_rate'],.5)
        for fields in ({'requested_rate':True},{'requested_rate':2},{'rate':1},
                       {'task_dwell_seconds':{'unknown':30}},{'task_dwell_seconds':{'hold':float('nan')}}):
            with self.assertRaises(ValueError): validate_joint_config(base|fields)
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'actions').mkdir()
            write_json(root/'status.json',dict(run_id='rate',epoch='a'*32,offer_token='b'*32,
                allowed_actions=['set-rate'],issued_monotonic_s=time.monotonic()))
            result=submit(root,'set-rate','a'*32,1)
            mailbox=Mailbox(root,'rate','a'*32)
            request=mailbox.poll('b'*32,['set-rate'])
            self.assertEqual(request['requested_rate'],1)
            mailbox.respond(request,'completed')
            self.assertIsNone(mailbox.poll('b'*32,['set-rate']))
            for bad in (request|{'epoch':'c'*32},request|{'requested_rate':2},request|{'extra':1}):
                with self.assertRaises(ValueError): validate_request(bad,'rate','a'*32)
            with self.assertRaises(ValueError): submit(root,'set-rate','a'*32)

    def test_dwell_uses_labels_sim_time_and_original_predicate(self):
        class FakeTask:
            joint_dwell_seconds={'hold':20,'waypoint':3}
            now=0
            def task_time(self): return self.now
            def pump(self): self.now+=.5
            def phase(self,name): self.completed=name
        task=FakeTask()
        JointTask.dwell(task,'hold_completed',lambda:True,5)
        self.assertEqual(task.now,20)
        self.assertEqual(task.completed,'hold_completed')
        with self.assertRaises(RuntimeError): JointTask.dwell(task,'waypoint_completed',lambda:False,2)

    def test_release_guard_contract_pinned(self):
        """Pin the unchanged release guard: sleep(min(remaining-1ms, 2ms)) only
        when remaining > 1ms, and the group never starts before its edge."""
        class InstrumentedWall(FakeWall):
            def __init__(self):
                super().__init__(); self.sleeps = []
            def now(self):
                self.ns += 1000
                return self.ns
            def sleep(self, seconds):
                self.sleeps.append(seconds)
                self.ns += round(seconds * 1e9)  # Perfect sleep: no overshoot.
        wall = InstrumentedWall(); events = []
        rate = JointRate('a'*32, .5, lambda kind, **row: events.append(dict(kind=kind, **row)), wall.now, wall.sleep)
        rate.reanchor(4, 'test')
        for group in range(6):
            rate.begin_group(4 + group * 4, lambda: None)
            wall.ns += 1_000_000  # 1ms of physics work.
            rate.end_group(8 + group * 4)
            start = [row for row in events if row['kind'] == 'rate_group_start'][-1]
            self.assertGreaterEqual(start['actual_start_ns'], start['earliest_start_ns'])
        # Each group: work 1ms + spin overhead; sleep argument pinned.
        self.assertTrue(wall.sleeps)
        for seconds in wall.sleeps:
            self.assertLessEqual(seconds, .002)
            self.assertGreater(seconds, 0)
        self.assertFalse(rate.latched)

    def test_release_guard_never_sleeps_past_the_edge(self):
        """A sub-guard sleep overshoot still starts on or before the edge."""
        class OvershootingWall(FakeWall):
            def sleep(self, seconds):
                self.ns += round(seconds * 1e9) + 900_000  # 0.9ms overshoot stays inside.
        wall = OvershootingWall()
        rate = JointRate('a'*32, .5, lambda kind, **row: None, wall.now, wall.sleep)
        rate.reanchor(4, 'test')
        rate.begin_group(4, lambda: None)
        wall.ns += 1_000_000
        rate.end_group(8)
        self.assertFalse(rate.latched)
        self.assertEqual(rate.completed, 1)

    def test_release_simulation_replays_repeated_sleep_calls(self):
        work = [1_000_000, 1_000_000]
        one = simulate_creep(work, [2_500_000], 1_000_000)
        two = simulate_creep(work, [2_500_000], 2_000_000)
        self.assertEqual(one['creep_ns'], 1_500_000)
        self.assertEqual(two['creep_ns'], 500_000)
        self.assertEqual(one['sleep_calls'], 2)
        self.assertEqual(two['sleep_calls'], 2)

if __name__=="__main__": unittest.main()
