"""Offline proof cases for trace parsing and scheduler attribution."""
import unittest
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from tools.analyze_joint_scheduler import (parse,pair,pair_all,explain,native_wait,
    recorded_native_waits,storage_summary)
from tools.profile_joint_scheduler import (epoch_groups_retired,failure_payload_clean,product_result_clean,complete_child_ownership,
    complete_fc_thread_names,validate_capture_started_early,wait_capture_active,
    retire_collector,retire_manager,kill_collector_group)


class SchedulerAnalysisTests(unittest.TestCase):
    def line(self,stamp,body):return f' wkcanary-1011 [003] ...1. {stamp}: {body}\n'

    def test_retirement_requires_each_epoch_not_just_manager_exit(self):
        for value in (None,{},dict(epochs=[]),dict(epochs=[{}]),
                      dict(epochs=[dict(remaining_group_members=[{'pid':1}])])):
            self.assertFalse(epoch_groups_retired(value))
        self.assertTrue(epoch_groups_retired(dict(epochs=[dict(remaining_group_members=[])])))

    def test_capture_wait_requires_complete_unambiguous_child_ownership(self):
        children={name:dict(identity=dict(pid=pid,start_ticks=pid+100,pgid=7))
                  for name,pid in zip(('arducopter-model','px4-model','arducopter-fc','px4-fc'),(11,22,33,44))}
        partial=dict(children);partial.pop('px4-fc')
        self.assertIsNone(complete_child_ownership(partial))
        owners=complete_child_ownership(dict(children,**{'arducopter-control':dict(identity=dict(pid=55,start_ticks=155))}),dict(pid=99))
        self.assertEqual([owners[name]['pid'] for name in children],[11,22,33,44])
        duplicate=dict(children)
        duplicate['px4-fc']=dict(identity=dict(pid=11,start_ticks=111,pgid=7))
        with self.assertRaisesRegex(ValueError,'Ambiguous child ownership'):
            complete_child_ownership(duplicate)

    def test_capture_wait_rejects_ambiguous_or_incomplete_fc_names(self):
        self.assertFalse(complete_fc_thread_names(['arducopter','log_io'],{'arducopter','log_io','DDS'}))
        with self.assertRaisesRegex(ValueError,'Ambiguous FC thread ownership'):
            complete_fc_thread_names(['logger','logger','wq:lp_default'],{'logger','wq:lp_default'})
        self.assertTrue(complete_fc_thread_names(['logger','logger-worker','wq:lp_default'],{'logger','wq:lp_default'}))

    def test_capture_token_requires_same_epoch_before_tick_40(self):
        epoch='a'*32
        with tempfile.TemporaryDirectory() as temp:
            status=Path(temp)/'status.json'
            state={'run_id':'run','epoch':epoch,'authority':{'epoch':epoch,'tick':39},
                   'issued_monotonic_s':101.0}
            status.write_text(json.dumps(state))
            active={'state':'active','run_id':'run','epoch':epoch,
                    'published_monotonic_ns':100_000_000_000}
            self.assertEqual(validate_capture_started_early(status,'run',epoch,active),state)
            for changed in ({'run_id':'other','epoch':epoch,'authority':{'epoch':epoch,'tick':1}},
                            {'run_id':'run','epoch':'b'*32,'authority':{'epoch':'b'*32,'tick':1}},
                            {'epoch':epoch,'authority':{'epoch':epoch,'tick':40}}):
                changed['issued_monotonic_s']=101.0
                status.write_text(json.dumps(changed))
                with self.assertRaisesRegex(RuntimeError,'run/epoch changed|timed tick 40'):
                    validate_capture_started_early(status,'run',epoch,active)
            state['authority']['tick']=1
            state['issued_monotonic_s']=99.0
            status.write_text(json.dumps(state))
            with self.assertRaisesRegex(TimeoutError,'Fresh capture status'):
                validate_capture_started_early(status,'run',epoch,active,timeout=.02)

            def publish_fresh(_delay):
                state['issued_monotonic_s']=101.0
                status.write_text(json.dumps(state))
            with patch('tools.profile_joint_scheduler.time.sleep',side_effect=publish_fresh):
                self.assertEqual(validate_capture_started_early(
                    status,'run',epoch,active,timeout=.2)['issued_monotonic_s'],101.0)

    def test_capture_freshness_fails_immediately_when_manager_or_collector_exits(self):
        class Exited:
            def poll(self):return 1
        epoch='a'*32
        with tempfile.TemporaryDirectory() as temp:
            status=Path(temp)/'status.json'
            active={'state':'active','run_id':'run','epoch':epoch,
                    'published_monotonic_ns':100_000_000_000}
            with self.assertRaisesRegex(RuntimeError,'Manager exited'):
                validate_capture_started_early(status,'run',epoch,active,manager=Exited(),timeout=.2)
            with self.assertRaisesRegex(RuntimeError,'Collector exited'):
                validate_capture_started_early(status,'run',epoch,active,collector=Exited(),timeout=.2)

    def test_capture_token_binds_instance_to_owned_collector_metadata(self):
        class Collector:
            pid=1234
            def poll(self):return None
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); token=root/'capture-active.json'
            owner=dict(schema='wksim.private-tracefs.instance-owner.v1',collector_pid=1234,
                       instance='/sys/kernel/tracing/instances/wksim-rate-a',
                        instance_inode=[1,2],run_id='run',epoch='a'*32)
            token.write_text(json.dumps(dict(schema='wksim.private-tracefs.capture-active.v1',
                state='active',collector_pid=1234,instance=owner['instance'],
                instance_inode=[3,4],run_id='run',epoch='a'*32)))
            (root/'instance-owner.json').write_text(json.dumps(owner))
            with self.assertRaisesRegex(RuntimeError,'token identity differs'):
                wait_capture_active(token,Collector(),'run','a'*32,timeout=.1)

    def test_collector_timeout_force_kills_and_verifies_owned_group(self):
        class StuckCollector:
            pid=1234
            def __init__(self):self.killed=False
            def poll(self):return -9 if self.killed else None
            def terminate(self):pass
            def kill(self):self.killed=True
            def wait(self,timeout):
                if not self.killed:raise subprocess.TimeoutExpired('collector',timeout)
                return -9
        collector=StuckCollector();result={}
        result['collector']={'pid':1234,'start_ticks':567,'pgid':1234}
        with patch('tools.profile_joint_scheduler.kill_collector_group',side_effect=lambda value,expected:value.kill()):
            retire_collector(collector,result)
        self.assertTrue(result['collector_group_killed'])
        self.assertEqual(collector.poll(),-9)
        self.assertIn('did not retire',result['collector_cleanup_error'])

    def test_manager_stop_failure_force_kills_and_confirms_owned_group_retirement(self):
        class StuckManager:
            pid=1234
            def __init__(self):self.killed=False
            def poll(self):return -9 if self.killed else None
            def wait(self,timeout):
                if not self.killed:raise subprocess.TimeoutExpired('manager',timeout)
                return -9
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp); (directory/'status.json').write_text(json.dumps({'run_id':'run','epoch':'a'*32}))
            manager=StuckManager()
            result={'run_id':'run','manager':{'pid':1234,'pgid':1234,'start_ticks':567}}
            with patch('tools.profile_joint_scheduler.submit',side_effect=RuntimeError('mailbox unavailable')), \
                 patch('tools.profile_joint_scheduler.manager_group_snapshot',return_value=None), \
                 patch('tools.profile_joint_scheduler.kill_manager_group',side_effect=lambda value,expected,*extra:value.__setattr__('killed',True)), \
                 patch('tools.profile_joint_scheduler.group_members',return_value=[]):
                retire_manager(manager,directory,result)
            self.assertTrue(result['manager_group_killed'])
            self.assertEqual(result['manager_returncode'],-9)
            self.assertEqual(result['remaining_manager_group'],[])
            self.assertIn('mailbox unavailable',result['manager_cleanup_error'])

    def test_collector_force_kill_rejects_changed_process_identity(self):
        class LiveCollector:
            pid=1234
            def poll(self):return None
            def kill(self):raise AssertionError('unverified collector was killed')
        expected={'pid':1234,'start_ticks':567,'pgid':1234}
        for field,value in (('pid',9999),('start_ticks',568),('pgid',9999)):
            observed=dict(expected);observed[field]=value
            with self.subTest(field=field), patch('tools.profile_joint_scheduler.json_identity',
                                                  return_value=observed):
                with self.assertRaisesRegex(RuntimeError,'Collector '+field+' identity differs'):
                    kill_collector_group(LiveCollector(),expected)

    @unittest.skipUnless(os.name=='posix','manager process-group retirement is Linux-only')
    def test_manager_leader_exit_retires_only_prevalidated_group_members(self):
        class ExitedManager:
            pid=1234
            returncode=0
            def poll(self):return 0
        leader={'pid':1234,'start_ticks':567,'pgid':1234}
        child={'pid':2222,'start_ticks':888,'pgid':1234}
        result={'run_id':'run','manager':leader,
                'manager_group_snapshot':[leader,child]}
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            snapshots=iter(([child],[child],[],[]))
            with patch('tools.profile_joint_scheduler.json_identity',return_value=None), \
                 patch('tools.profile_joint_scheduler.group_members',side_effect=lambda _pgid:next(snapshots)), \
                 patch('tools.profile_joint_scheduler.kill_manager_group_after_leader') as kill:
                from tools.profile_joint_scheduler import retire_manager
                retire_manager(ExitedManager(),directory,result)
            self.assertTrue(result['manager_group_killed'])
            kill.assert_called_once()
            self.assertEqual(result['remaining_manager_group'],[])

    @unittest.skipUnless(os.name=='posix','manager process-group retirement is Linux-only')
    def test_manager_leader_exit_rejects_new_group_member(self):
        class ExitedManager:
            pid=1234
            returncode=0
            def poll(self):return 0
        leader={'pid':1234,'start_ticks':567,'pgid':1234}
        child={'pid':2222,'start_ticks':888,'pgid':1234}
        foreign={'pid':3333,'start_ticks':999,'pgid':1234}
        result={'run_id':'run','manager':leader,
                'manager_group_snapshot':[leader,child]}
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            snapshots=iter(([foreign],[foreign]))
            with patch('tools.profile_joint_scheduler.json_identity',return_value=None), \
                 patch('tools.profile_joint_scheduler.group_members',side_effect=lambda _pgid:next(snapshots)), \
                 patch('tools.profile_joint_scheduler.kill_manager_group_after_leader') as kill:
                from tools.profile_joint_scheduler import retire_manager
                retire_manager(ExitedManager(),directory,result)
            kill.assert_not_called()
            self.assertIn('Manager group member identity differs',result['manager_cleanup_error'])
            self.assertEqual(result['remaining_manager_group'],[foreign])

    def test_product_result_clean_rejects_missing_or_failed_product_and_epochs(self):
        self.assertFalse(product_result_clean(None))
        self.assertFalse(product_result_clean({'status':'failed','epochs':[]}))
        base={'status':'stopped','epochs':[{'remaining_group_members':[],
            'result':{'status':'stopped'}}]}
        self.assertTrue(product_result_clean(base))
        failed_epoch={'status':'stopped','epochs':[{'remaining_group_members':[],
            'result':{'status':'failed'}}]}
        self.assertFalse(product_result_clean(failed_epoch))
        unknown_status={'status':'error','epochs':[{'remaining_group_members':[],
            'result':{'status':'error'}}]}
        self.assertFalse(product_result_clean(unknown_status))
        leaked={'status':'stopped','epochs':[{'remaining_group_members':[{'pid':1}],
            'result':{'status':'stopped'}}]}
        self.assertFalse(product_result_clean(leaked))

    def test_product_result_clean_rejects_non_empty_failure_payloads_at_each_scope(self):
        base={'status':'stopped','epochs':[{'remaining_group_members':[],
            'result':{'status':'stopped'}}]}
        for field,location in (('error','top'),('cleanup_errors','epoch'),('unresolved','result')):
            value=json.loads(json.dumps(base))
            target=value if location=='top' else value['epochs'][0] if location=='epoch' else value['epochs'][0]['result']
            target[field]=['failure']
            with self.subTest(field=field,location=location):
                self.assertFalse(product_result_clean(value))

    def test_product_result_clean_allows_empty_failure_payload_fields(self):
        value={'status':'stopped','error':None,'errors':[],
               'epochs':[{'remaining_group_members':[],'cleanup_errors':{},
                   'result':{'status':'stopped','error':'','evidence_errors':[],
                             'failures':[],'unresolved':None}}]}
        self.assertTrue(failure_payload_clean(value))
        self.assertTrue(product_result_clean(value))

    def test_hex_write_count_and_native_time(self):
        event=parse(self.line('3.123456','sys_write(fd: 3, buf: abc, count: 51d)'))
        self.assertEqual((event['ns'],event['count'],event['fd']),(3123456000,1309,3))
        event=parse(self.line('3.123457','sys_write -> 0xffffffffffffffff'))
        self.assertEqual(event['ret'],-1)

    def test_fsync_and_fdatasync_are_parsed_and_paired(self):
        events=[parse(self.line('3.123456','sys_fsync(fd: 0x00000009)')),
                parse(self.line('3.123457','sys_fsync -> 0x0')),
                parse(self.line('3.123458','sys_fdatasync(fd: 0x0000000a)')),
                parse(self.line('3.123460','sys_fdatasync -> 0xffffffffffffffff'))]
        paired=pair_all(events,{1011});calls=paired['syncs'];boundaries=paired['boundaries']
        self.assertEqual([(row['syscall'],row['fd'],row['ret']) for row in calls],
                         [('fsync',9,0),('fdatasync',10,-1)])
        self.assertEqual(boundaries['open_syncs_at_end'],0)
        writes,_off,_boundaries=pair(events,{1011})
        self.assertEqual(writes,[])

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

    def test_fc_storage_keeps_fd_rate_group_and_scheduler_evidence(self):
        call=dict(kind='fsync_enter',syscall='fsync',pid=42,ns=100,fd=9,
                  end_ns=200,duration_ns=100,ret=0)
        off={42:[dict(start_ns=120,end_ns=180,state='S',wake_ns=160)]}
        groups=[dict(actual_start_ns=50,actual_end_ns=250,start_tick=1,end_tick=2)]
        result=storage_summary([call],off,{'ap_fc/log_io':42},
            {'ap_fc':{'fds':{'9':{'target':'/tmp/APM.bin'}}}},groups)
        fsync=next(row for row in result[0]['operations'] if row['syscall']=='fsync')
        self.assertEqual((fsync['complete_calls'],fsync['failed_or_short'],fsync['maximum_ns']),(1,0,100))
        self.assertEqual(fsync['top'][0]['fd_before']['target'],'/tmp/APM.bin')
        self.assertEqual(fsync['top'][0]['rate_group']['start_tick'],1)
        self.assertEqual(fsync['top'][0]['scheduler']['blocked_before_wake_ns'],40)

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
        result=native_wait(timing,intervals,{'ap_fc/arducopter':[
            dict(start_ns=30,end_ns=70,state='R',wake_ns=None)]})
        self.assertEqual(result['correlated_threads']['ap_fc/arducopter']['runnable_ns'],40)
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
