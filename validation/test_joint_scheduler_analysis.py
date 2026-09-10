"""Offline proof cases for trace parsing and scheduler attribution."""
import unittest
from tools.analyze_joint_scheduler import parse,pair,explain,native_wait
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


if __name__=='__main__':unittest.main()
