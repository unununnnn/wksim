"""Offline proof cases for trace parsing and scheduler attribution."""
import unittest
from tools.analyze_joint_scheduler import parse,pair,explain,native_wait,recorded_native_waits
from tools.profile_joint_scheduler import epoch_groups_retired


class SchedulerAnalysisTests(unittest.TestCase):
    def line(self,stamp,body):return f' wkcanary-1011 [003] ...1. {stamp}: {body}\n'

    def test_retirement_requires_each_epoch_not_just_manager_exit(self):
        for value in (None,{},dict(epochs=[]),dict(epochs=[{}]),
                      dict(epochs=[dict(remaining_group_members=[{'pid':1}])])):
            self.assertFalse(epoch_groups_retired(value))
        self.assertTrue(epoch_groups_retired(dict(epochs=[dict(remaining_group_members=[])])))

    def test_hex_write_count_and_native_time(self):
        event=parse(self.line('3.123456','sys_write(fd: 3, buf: abc, count: 51d)'))
        self.assertEqual((event['ns'],event['count'],event['fd']),(3123456000,1309,3))
        event=parse(self.line('3.123457','sys_write -> 0xffffffffffffffff'))
        self.assertEqual(event['ret'],-1)

    def test_blocked_and_runnable_intervals_are_distinguished(self):
        events=[dict(kind='write_enter',pid=1011,ns=10,fd=3,count=10),
            dict(kind='switch',ns=20,prev=1011,next=0,state='D'),
            dict(kind='wakeup',ns=80,pid=1011),dict(kind='switch',ns=100,prev=0,next=1011,state='R'),
            dict(kind='write_exit',pid=1011,ns=110,ret=10)]
        writes,off,boundaries=pair(events,{1011})
        result=explain(writes[0],off[1011])
        self.assertEqual((result['blocked_before_wake_ns'],result['runnable_ns'],result['off_cpu_ns']),(60,20,80))
        self.assertEqual(boundaries['open_writes_at_end'],0)
        events[1]['state']='R+'
        writes,off,_=pair(events,{1011});result=explain(writes[0],off[1011])
        self.assertEqual((result['blocked_before_wake_ns'],result['runnable_ns']),(0,80))

    def test_missing_wake_and_half_syscall_are_not_fabricated(self):
        events=[dict(kind='write_exit',pid=1011,ns=1,ret=5),
            dict(kind='write_enter',pid=1011,ns=10,fd=3,count=5),
            dict(kind='switch',ns=20,prev=1011,next=0,state='S'),
            dict(kind='switch',ns=80,prev=0,next=1011,state='R'),
            dict(kind='write_exit',pid=1011,ns=100,ret=5)]
        writes,off,boundaries=pair(events,{1011})
        self.assertEqual(len(writes),1)
        self.assertEqual(boundaries['exit_without_entry'],1)
        self.assertEqual(explain(writes[0],off[1011])['unknown_off_cpu_ns'],60)

    def test_native_wait_excludes_model_and_encoding_and_preserves_stack_boundary(self):
        timing=dict(tick=6,wall_start_ns=10,wall_end_ns=117,stages={
            'health_and_models':dict(wall_ns=5,thread_cpu_ns=4),
            'encode_send':dict(wall_ns=2,thread_cpu_ns=2),
            'native_inputs':dict(wall_ns=100,thread_cpu_ns=20)})
        intervals=[dict(start_ns=20,end_ns=100,state='S',wake_ns=80)]
        result=native_wait(timing,intervals)
        self.assertEqual((result['ns'],result['end_ns'],result['duration_ns']),(17,117,100))
        self.assertEqual(result['native_path'],'AP input only')
        self.assertEqual(result['supervisor_scheduler']['blocked_before_wake_ns'],60)
        self.assertEqual(result['supervisor_scheduler']['runnable_ns'],20)
        timing['tick']=8
        self.assertIn('not separated',native_wait(timing,intervals)['native_path'])
        timing['wall_end_ns']+=1
        with self.assertRaisesRegex(ValueError,'Stage timestamps'):native_wait(timing,intervals)

    def test_recorded_waits_keep_sampling_and_capture_boundaries(self):
        def sample(tick,start,model,wait):
            return dict(tick=tick,wall_start_ns=start,wall_end_ns=start+model+wait,
                stages={'health_and_models':dict(wall_ns=model,thread_cpu_ns=model),
                    'encode_send':dict(wall_ns=0,thread_cpu_ns=0),
                    'native_inputs':dict(wall_ns=wait,thread_cpu_ns=10)})
        rows=[sample(1,0,0,100),sample(2,100,3_000_000,100),
              sample(4,3_000_200,0,3_000_000),sample(5,6_000_200,0,100)]
        intervals=[dict(start_ns=3_000_300,end_ns=5_000_300,state='S',wake_ns=5_000_200)]
        result=recorded_native_waits(rows,intervals,100,6_000_200)
        self.assertEqual((result['inside_capture'],result['excluded_capture_boundary']),(2,2))
        paths={row['native_path']:row for row in result['by_native_path']}
        self.assertEqual(paths['AP input only']['recorded_waits_over_2ms'],0)
        self.assertEqual(sum(row['recorded_waits_over_2ms'] for row in paths.values()),1)
        longest=result['longest_recorded_waits'][0]
        self.assertEqual(longest['tick'],4)
        self.assertEqual(longest['supervisor_scheduler']['runnable_ns'],100)
        self.assertEqual(longest['supervisor_scheduler']['blocked_before_wake_ns'],1_999_900)
        self.assertEqual(recorded_native_waits([],[],1,2)['inside_capture'],0)
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            recorded_native_waits(rows,intervals+intervals,100,6_000_200)


if __name__=='__main__':unittest.main()
