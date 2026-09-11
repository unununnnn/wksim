"""Offline proof cases for trace parsing and scheduler attribution."""
import unittest
import hashlib
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from tools.analyze_joint_scheduler import (parse,pair,pair_all,explain,native_wait,
    recorded_native_waits,storage_summary)
from tools.profile_joint_scheduler import (epoch_groups_retired,failure_payload_clean,product_result_clean,complete_child_ownership,
    complete_fc_thread_names,validate_capture_started_early,wait_capture_active,wait_gate_ready,wait_gate_release,
    validate_capture_owner_final,install_cleanup_signal_handlers,restore_cleanup_signal_handlers,
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

    def test_first_step_gate_ready_requires_tick_zero_and_owned_supervisor(self):
        epoch='a'*32
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'gate-ready.json'
            ready=dict(schema='wksim.private-tracefs.capture-gate-ready.v1',state='ready',
                       run_id='run',epoch=epoch,pid=123,start_ticks=456,tick=0,published_monotonic_ns=100)
            path.write_text(json.dumps(ready))
            identity=dict(pid=123,start_ticks=456)
            self.assertEqual(wait_gate_ready(path,'run',epoch,identity)['tick'],0)
            ready['tick']=1;path.write_text(json.dumps(ready))
            with self.assertRaisesRegex(RuntimeError,'gate-ready proof identity differs'):
                wait_gate_ready(path,'run',epoch,identity)

    def test_first_step_gate_release_binds_token_and_gate_hash(self):
        epoch='a'*32
        class Collector:
            pid=456
            def poll(self):return None
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ready_path=root/'gate-ready.json';release=root/'gate-release.json'
            token=root/'capture-active.json'
            ready=dict(schema='wksim.private-tracefs.capture-gate-ready.v1',state='ready',
                       run_id='run',epoch=epoch,pid=123,start_ticks=456,tick=0,published_monotonic_ns=100)
            ready_path.write_text(json.dumps(ready,sort_keys=True)+'\n')
            expected={'supervisor':{'pid':123,'start_ticks':456,'pgid':123,
                                    'argv':['supervisor','--run','run']},
                      'ap_worker':{'pid':201,'start_ticks':301,'pgid':201,
                                   'argv':['worker','--stack','arducopter']},
                      'px4_worker':{'pid':202,'start_ticks':302,'pgid':202,
                                    'argv':['worker','--stack','px4']},
                      'ap_fc':{'pid':203,'start_ticks':303,'pgid':203,
                               'argv':['arducopter','--run','run']},
                      'px4_fc':{'pid':204,'start_ticks':304,'pgid':204,
                                'argv':['px4','--run','run']}}
            owner=dict(schema='wksim.private-tracefs.instance-owner.v1',run_id='run',epoch=epoch,
                       collector_pid=456,collector_start_ticks=457,supervisor_pid=123,
                       supervisor_start_ticks=456,instance='/sys/wksim-rate-a',instance_inode=[1,2],
                       owners=expected)
            (root/'instance-owner.json').write_text(json.dumps(owner,sort_keys=True)+'\n')
            token.write_text(json.dumps(dict(schema='wksim.private-tracefs.capture-active.v1',
                state='active',run_id='run',epoch=epoch,collector_pid=456,collector_start_ticks=457,
                supervisor_pid=123,supervisor_start_ticks=456,instance=owner['instance'],
                instance_inode=owner['instance_inode'],instance_owner_sha256=hashlib.sha256(
                    (root/'instance-owner.json').read_bytes()).hexdigest(),started_monotonic_ns=150,
                published_monotonic_ns=200))+'\n')
            collector_identity=dict(pid=456,start_ticks=457)
            value=dict(schema='wksim.private-tracefs.capture-release.v1',state='released',
                run_id='run',epoch=epoch,supervisor_pid=123,supervisor_start_ticks=456,
                collector_pid=456,collector_start_ticks=457,
                capture_active_sha256=hashlib.sha256(token.read_bytes()).hexdigest(),
                gate_ready_sha256=hashlib.sha256(ready_path.read_bytes()).hexdigest(),tick=0,
                instance_owner_sha256=hashlib.sha256((root/'instance-owner.json').read_bytes()).hexdigest(),
                instance=owner['instance'],instance_inode=owner['instance_inode'],
                capture_active_published_monotonic_ns=200,released_monotonic_ns=300)
            release.write_text(json.dumps(value))
            with patch('tools.profile_joint_scheduler.json_identity',return_value=collector_identity):
                self.assertEqual(wait_capture_active(
                    token,Collector(),'run',epoch,collector_identity=collector_identity,
                    supervisor_identity={'pid':123,'start_ticks':456},expected_owners=expected,
                    timeout=.1)['state'],'active')
                result=wait_gate_release(release,ready,token,'run',epoch,Collector(),
                                         collector_identity=collector_identity,
                                         expected_owners=expected)
            self.assertEqual(result['capture_active_sha256'],value['capture_active_sha256'])
            final=validate_capture_owner_final(token,ready,collector_identity,expected,release)
            self.assertEqual(set(final['owner']['owners']),set(expected))
            token.write_text(token.read_text()+'tamper')
            with patch('tools.profile_joint_scheduler.json_identity',return_value=collector_identity), \
                    self.assertRaisesRegex(RuntimeError,'Capture owner chain is unreadable|JSON|identity'):
                wait_gate_release(release,ready,token,'run',epoch,Collector(),
                                  collector_identity=collector_identity,expected_owners=expected)

    def test_final_owner_rejects_hash_tamper_and_collector_pid_reuse(self):
        epoch='a'*32
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);token=root/'capture-active.json';owner_path=root/'instance-owner.json'
            ready_path=root/'gate-ready.json';release_path=root/'gate-release.json'
            ready=dict(schema='wksim.private-tracefs.capture-gate-ready.v1',state='ready',
                       run_id='run',epoch=epoch,pid=123,start_ticks=456,tick=0,
                       published_monotonic_ns=100)
            ready_path.write_text(json.dumps(ready,sort_keys=True)+'\n')
            owner=dict(schema='wksim.private-tracefs.instance-owner.v1',run_id='run',epoch=epoch,
                       collector_pid=456,collector_start_ticks=457,supervisor_pid=123,
                       supervisor_start_ticks=456,instance='/sys/wksim-rate-a',instance_inode=[1,2])
            owner_path.write_text(json.dumps(owner,sort_keys=True)+'\n')
            active=dict(schema='wksim.private-tracefs.capture-active.v1',state='active',
                        run_id='run',epoch=epoch,collector_pid=456,collector_start_ticks=457,
                        supervisor_pid=123,supervisor_start_ticks=456,instance=owner['instance'],
                        instance_inode=owner['instance_inode'],
                        instance_owner_sha256=hashlib.sha256(owner_path.read_bytes()).hexdigest(),
                        started_monotonic_ns=150,published_monotonic_ns=200)
            token.write_text(json.dumps(active,sort_keys=True)+'\n')
            release=dict(schema='wksim.private-tracefs.capture-release.v1',state='released',
                         run_id='run',epoch=epoch,supervisor_pid=123,supervisor_start_ticks=456,
                         collector_pid=456,collector_start_ticks=457,
                         capture_active_sha256=hashlib.sha256(token.read_bytes()).hexdigest(),
                         instance_owner_sha256=active['instance_owner_sha256'],
                         gate_ready_sha256=hashlib.sha256(ready_path.read_bytes()).hexdigest(),
                         instance=owner['instance'],instance_inode=owner['instance_inode'],tick=0,
                         capture_active_published_monotonic_ns=200,released_monotonic_ns=300)
            release_path.write_text(json.dumps(release,sort_keys=True)+'\n')
            collector=dict(pid=456,start_ticks=457)
            self.assertEqual(validate_capture_owner_final(token,ready,collector,
                             release_path=release_path)['sha256'],
                             active['instance_owner_sha256'])
            owner_path.write_text(owner_path.read_text()+'\n')
            with self.assertRaisesRegex(RuntimeError,'digest changed|identity differs'):
                validate_capture_owner_final(token,ready,collector,release_path=release_path)
            owner['collector_start_ticks']=999
            owner_path.write_text(json.dumps(owner,sort_keys=True)+'\n')
            with self.assertRaisesRegex(RuntimeError,'identity differs'):
                validate_capture_owner_final(token,ready,collector,release_path=release_path)

    def test_final_owner_requires_expected_identity_fields_for_complete_five_role_chain(self):
        epoch='a'*32
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);token=root/'capture-active.json';owner_path=root/'instance-owner.json'
            ready_path=root/'gate-ready.json';release_path=root/'gate-release.json'
            ready=dict(schema='wksim.private-tracefs.capture-gate-ready.v1',state='ready',
                       run_id='run',epoch=epoch,pid=123,start_ticks=456,tick=0,
                       published_monotonic_ns=100)
            ready_path.write_text(json.dumps(ready,sort_keys=True)+'\n')
            expected={'supervisor':{'pid':123,'start_ticks':456,'pgid':123,
                                    'argv':['supervisor','--run','run']},
                      'ap_worker':{'pid':201,'start_ticks':301,'pgid':201,
                                   'argv':['worker','--stack','arducopter']},
                      'px4_worker':{'pid':202,'start_ticks':302,'pgid':202,
                                    'argv':['worker','--stack','px4']},
                      'ap_fc':{'pid':203,'start_ticks':303,'pgid':203,
                               'argv':['arducopter','--run','run']},
                      'px4_fc':{'pid':204,'start_ticks':304,'pgid':204,
                                'argv':['px4','--run','run']}}

            def write_chain(owner_owners):
                owner=dict(schema='wksim.private-tracefs.instance-owner.v1',run_id='run',epoch=epoch,
                           collector_pid=456,collector_start_ticks=457,supervisor_pid=123,
                           supervisor_start_ticks=456,instance='/sys/wksim-rate-a',instance_inode=[1,2],
                           owners=owner_owners)
                owner_path.write_text(json.dumps(owner,sort_keys=True)+'\n')
                active=dict(schema='wksim.private-tracefs.capture-active.v1',state='active',
                            run_id='run',epoch=epoch,collector_pid=456,collector_start_ticks=457,
                            supervisor_pid=123,supervisor_start_ticks=456,instance=owner['instance'],
                            instance_inode=owner['instance_inode'],
                            instance_owner_sha256=hashlib.sha256(owner_path.read_bytes()).hexdigest(),
                            started_monotonic_ns=150,published_monotonic_ns=200)
                token.write_text(json.dumps(active,sort_keys=True)+'\n')
                release=dict(schema='wksim.private-tracefs.capture-release.v1',state='released',
                             run_id='run',epoch=epoch,supervisor_pid=123,supervisor_start_ticks=456,
                             collector_pid=456,collector_start_ticks=457,
                             capture_active_sha256=hashlib.sha256(token.read_bytes()).hexdigest(),
                             instance_owner_sha256=active['instance_owner_sha256'],
                             gate_ready_sha256=hashlib.sha256(ready_path.read_bytes()).hexdigest(),
                             instance=owner['instance'],instance_inode=owner['instance_inode'],tick=0,
                             capture_active_published_monotonic_ns=200,released_monotonic_ns=300)
                release_path.write_text(json.dumps(release,sort_keys=True)+'\n')

            write_chain(json.loads(json.dumps(expected)))
            result=validate_capture_owner_final(token,ready,{'pid':456,'start_ticks':457},
                                                expected,release_path)
            self.assertEqual(set(result['owner']['owners']),set(expected))
            for field,pattern in (('pgid','pgid identity is missing'),
                                  ('argv','argv identity is missing')):
                owners=json.loads(json.dumps(expected))
                owners['supervisor'].pop(field)
                write_chain(owners)
                with self.subTest(missing=field), self.assertRaisesRegex(RuntimeError,pattern):
                    validate_capture_owner_final(token,ready,{'pid':456,'start_ticks':457},
                                                 expected,release_path)
            owners=json.loads(json.dumps(expected))
            owners['px4_fc']['argv']=['foreign']
            write_chain(owners)
            with self.assertRaisesRegex(RuntimeError,'argv identity differs'):
                validate_capture_owner_final(token,ready,{'pid':456,'start_ticks':457},
                                             expected,release_path)

    def test_final_owner_rejects_active_state_time_and_release_time_tamper(self):
        epoch='a'*32
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);token=root/'capture-active.json';owner_path=root/'instance-owner.json'
            ready_path=root/'gate-ready.json';release_path=root/'gate-release.json'
            ready=dict(schema='wksim.private-tracefs.capture-gate-ready.v1',state='ready',
                       run_id='run',epoch=epoch,pid=123,start_ticks=456,tick=0,
                       published_monotonic_ns=100)
            ready_path.write_text(json.dumps(ready,sort_keys=True)+'\n')
            owner=dict(schema='wksim.private-tracefs.instance-owner.v1',run_id='run',epoch=epoch,
                       collector_pid=456,collector_start_ticks=457,supervisor_pid=123,
                       supervisor_start_ticks=456,instance='/sys/wksim-rate-a',instance_inode=[1,2])
            owner_path.write_text(json.dumps(owner,sort_keys=True)+'\n')
            def write_chain(state='active',published=200,release_published=200):
                active=dict(schema='wksim.private-tracefs.capture-active.v1',state=state,
                            run_id='run',epoch=epoch,collector_pid=456,collector_start_ticks=457,
                            supervisor_pid=123,supervisor_start_ticks=456,instance=owner['instance'],
                            instance_inode=owner['instance_inode'],
                            instance_owner_sha256=hashlib.sha256(owner_path.read_bytes()).hexdigest(),
                            started_monotonic_ns=150,published_monotonic_ns=published)
                token.write_text(json.dumps(active,sort_keys=True)+'\n')
                release=dict(schema='wksim.private-tracefs.capture-release.v1',state='released',
                             run_id='run',epoch=epoch,supervisor_pid=123,supervisor_start_ticks=456,
                             collector_pid=456,collector_start_ticks=457,
                             capture_active_sha256=hashlib.sha256(token.read_bytes()).hexdigest(),
                             instance_owner_sha256=active['instance_owner_sha256'],
                             gate_ready_sha256=hashlib.sha256(ready_path.read_bytes()).hexdigest(),
                             instance=owner['instance'],instance_inode=owner['instance_inode'],tick=0,
                             capture_active_published_monotonic_ns=release_published,
                             released_monotonic_ns=300)
                release_path.write_text(json.dumps(release,sort_keys=True)+'\n')
            write_chain()
            for state,published,release_published in (('tampered',200,200),('active',50,50)):
                write_chain(state,published,release_published)
                with self.subTest(state=state,published=published), self.assertRaisesRegex(
                        RuntimeError,'Capture-active token identity differs'):
                    validate_capture_owner_final(token,ready,{'pid':456,'start_ticks':457},
                                                 release_path=release_path)
            write_chain('active',200,199)
            with self.assertRaisesRegex(RuntimeError,'gate-release proof identity differs'):
                validate_capture_owner_final(token,ready,{'pid':456,'start_ticks':457},
                                             release_path=release_path)

    def test_gate_waits_fail_closed_when_manager_or_collector_exits(self):
        class Exited:
            pid=456
            def poll(self):return 1
        epoch='a'*32
        identity=dict(pid=123,start_ticks=456)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError,'Manager exited'):
                wait_gate_ready(Path(temp)/'missing-ready','run',epoch,identity,manager=Exited(),timeout=.2)
            ready=dict(schema='wksim.private-tracefs.capture-gate-ready.v1',state='ready',
                       run_id='run',epoch=epoch,pid=123,start_ticks=456,tick=0,
                       published_monotonic_ns=100)
            with self.assertRaisesRegex(RuntimeError,'Collector exited'):
                wait_gate_release(Path(temp)/'missing-release',ready,Path(temp)/'missing-token',
                                  'run',epoch,Exited(),collector_identity=dict(pid=456,start_ticks=457),
                                  timeout=.2)

    def test_sigterm_handler_is_restored_after_cleanup(self):
        calls=[]
        def fake(signum,handler):
            calls.append((signum,handler))
            return 'previous-'+str(signum)
        with patch('tools.profile_joint_scheduler.signal.signal',side_effect=fake):
            previous=install_cleanup_signal_handlers()
            restore_cleanup_signal_handlers(previous)
        self.assertEqual(len(calls),4)
        self.assertEqual([handler for _,handler in calls[2:]],
                         ['previous-'+str(signum) for signum,_ in calls[:2]])

    def test_sigterm_handler_converts_signal_to_handled_interrupt(self):
        previous=install_cleanup_signal_handlers()
        try:
            handler=signal.getsignal(signal.SIGTERM)
            with self.assertRaises(KeyboardInterrupt):
                handler(signal.SIGTERM,None)
        finally:
            restore_cleanup_signal_handlers(previous)

    def test_capture_token_binds_instance_to_owned_collector_metadata(self):
        class Collector:
            pid=1234
            def poll(self):return None
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); token=root/'capture-active.json'
            owner=dict(schema='wksim.private-tracefs.instance-owner.v1',collector_pid=1234,
                       collector_start_ticks=567,supervisor_pid=99,supervisor_start_ticks=100,
                       instance='/sys/kernel/tracing/instances/wksim-rate-a',
                        instance_inode=[1,2],run_id='run',epoch='a'*32)
            owner_raw=json.dumps(owner).encode();(root/'instance-owner.json').write_bytes(owner_raw)
            token.write_text(json.dumps(dict(schema='wksim.private-tracefs.capture-active.v1',
                state='active',collector_pid=1234,collector_start_ticks=567,supervisor_pid=99,
                supervisor_start_ticks=100,instance=owner['instance'],instance_inode=[3,4],
                instance_owner_sha256=hashlib.sha256(owner_raw).hexdigest(),run_id='run',epoch='a'*32,
                started_monotonic_ns=1,published_monotonic_ns=2)))
            collector_identity=dict(pid=1234,start_ticks=567)
            supervisor_identity=dict(pid=99,start_ticks=100)
            with patch('tools.profile_joint_scheduler.json_identity',return_value=collector_identity), \
                    self.assertRaisesRegex(RuntimeError,'token identity differs'):
                wait_capture_active(token,Collector(),'run','a'*32,collector_identity=collector_identity,
                                    supervisor_identity=supervisor_identity,timeout=.1)

    def test_capture_wait_accepts_complete_five_role_owner_proof(self):
        class Collector:
            pid=1234
            def poll(self):return None
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);token=root/'capture-active.json'
            expected={'supervisor':{'pid':99,'start_ticks':100,'pgid':99,
                                    'argv':['supervisor','--run','run']},
                      'ap_worker':{'pid':11,'start_ticks':111,'pgid':11,
                                    'argv':['worker','--stack','arducopter']},
                      'px4_worker':{'pid':22,'start_ticks':122,'pgid':22,
                                     'argv':['worker','--stack','px4']},
                      'ap_fc':{'pid':33,'start_ticks':133,'pgid':33,
                               'argv':['arducopter','--run','run']},
                      'px4_fc':{'pid':44,'start_ticks':144,'pgid':44,
                                'argv':['px4','--run','run']}}
            owner=dict(schema='wksim.private-tracefs.instance-owner.v1',collector_pid=1234,
                       collector_start_ticks=567,supervisor_pid=99,supervisor_start_ticks=100,
                       instance='/sys/kernel/tracing/instances/wksim-rate-a',instance_inode=[1,2],
                       run_id='run',epoch='a'*32,
                       owners=expected)
            owner_raw=json.dumps(owner,sort_keys=True).encode();(root/'instance-owner.json').write_bytes(owner_raw)
            token.write_text(json.dumps(dict(schema='wksim.private-tracefs.capture-active.v1',
                state='active',collector_pid=1234,collector_start_ticks=567,supervisor_pid=99,
                supervisor_start_ticks=100,instance=owner['instance'],instance_inode=owner['instance_inode'],
                instance_owner_sha256=hashlib.sha256(owner_raw).hexdigest(),run_id='run',epoch='a'*32,
                started_monotonic_ns=1,published_monotonic_ns=2)))
            collector_identity={'pid':1234,'start_ticks':567,'pgid':1234,'argv':['collector']}
            with patch('tools.profile_joint_scheduler.json_identity',return_value=collector_identity):
                result=wait_capture_active(token,Collector(),'run','a'*32,
                    collector_identity=collector_identity,supervisor_identity={'pid':99,'start_ticks':100},
                    expected_owners=expected,timeout=.1)
            self.assertEqual(result['state'],'active')

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
