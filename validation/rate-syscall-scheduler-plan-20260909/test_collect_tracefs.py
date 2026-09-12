"""No kernel tracing: parser, filter, path ownership and preflight guards only."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import threading
import time

from tools.wsl_snapshot_exchange import decode_json_strict, make_snapshot_response, publish_create_only
from validation.test_wsl_root_task_snapshot import VALID_LSNS as SYSTEM_VIEW_LSNS, make_stat, make_status

# Successful mapping fixtures must represent the initial kernel namespace.
VALID_LSNS = SYSTEM_VIEW_LSNS.replace('4026532209', '4026531836')

sys.path.insert(0,str(Path(__file__).resolve().parent))
import collect_tracefs as collector


class Guards(unittest.TestCase):
    def test_owner_fields_are_positive_integers(self):
        self.assertEqual(collector.owner('123:456'),dict(pid=123,start_ticks=456))
        for value in ('0:3','3:0','3:4:5','3;4','abc','-3:4'):
            with self.subTest(value=value),self.assertRaises(ValueError):collector.owner(value)

    def test_filters_use_event_target_fields_not_waker_common_pid(self):
        pids=dict(ap_worker=11,px4_worker=22,supervisor=33,
                  **{'ap_fc/arducopter':41,'ap_fc/log_io':42,'ap_fc/DDS':43,
                     'px4_fc/sim_send':51,'px4_fc/logger':52,'px4_fc/wq:lp_default':53})
        filters=collector.filters(pids)
        self.assertEqual(set(filters),set(collector.EVENTS))
        self.assertEqual(filters['syscalls/sys_enter_write'],
                         'common_pid == 11 || common_pid == 22 || common_pid == 42 || common_pid == 52')
        self.assertEqual(filters['syscalls/sys_enter_fsync'],'common_pid == 42 || common_pid == 52')
        self.assertEqual(filters['syscalls/sys_exit_fdatasync'],'common_pid == 42 || common_pid == 52')
        self.assertIn('prev_pid == 33 || next_pid == 33',filters['sched/sched_switch'])
        self.assertIn('prev_pid == 53 || next_pid == 53',filters['sched/sched_switch'])
        self.assertEqual(filters['sched/sched_wakeup'],
                         ' || '.join('pid == '+str(pid) for pid in pids.values()))

    def test_base_filters_preserve_three_owner_mode(self):
        filters=collector.filters(dict(ap_worker=11,px4_worker=22,supervisor=33))
        self.assertEqual(set(filters),{'syscalls/sys_enter_write','syscalls/sys_exit_write',
                                      'sched/sched_switch','sched/sched_wakeup'})
        self.assertEqual(filters['syscalls/sys_enter_write'],'common_pid == 11 || common_pid == 22')

    def test_instance_guard_rejects_global_foreign_and_replaced_inode(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'instances').mkdir()
            own=root/'instances'/('wksim-rate-'+'a'*32);own.mkdir()
            stat=own.stat();inode=(stat.st_dev,stat.st_ino)
            with patch.object(collector,'TRACE',root):
                collector.guarded_instance(own,inode)
                for path,stamp in [(root,inode),(root/'instances',inode),(own,(0,0))]:
                    with self.subTest(path=path),self.assertRaises(ValueError):collector.guarded_instance(path,stamp)

    def test_identity_mismatch_prevents_any_output_or_instance_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'new'
            with patch.object(collector.os,'geteuid',return_value=0,create=True), \
                 patch.object(collector,'preflight',side_effect=ValueError('identity differs')):
                with self.assertRaisesRegex(ValueError,'identity differs'):
                    collector.collect(SimpleNamespace(output=output,boot_id='bad'),{})
            self.assertFalse(output.exists())

    def test_capture_rejects_three_owner_set_before_preflight_or_trace_instance(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'new'
            owners={'ap_worker':dict(pid=11,start_ticks=1000),
                    'px4_worker':dict(pid=22,start_ticks=2000),
                    'supervisor':dict(pid=33,start_ticks=3000)}
            args=SimpleNamespace(output=output,boot_id='boot',run_id='run',epoch='a'*32)
            with patch.object(collector.os,'geteuid',return_value=0,create=True), \
                 patch.object(collector,'preflight') as preflight:
                with self.assertRaisesRegex(ValueError,'ap_fc and px4_fc'):
                    collector.collect(args,owners)
            preflight.assert_not_called()
            self.assertFalse(output.exists())

    def test_capture_cli_rejects_three_owner_set(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'new'
            argv=['collect_tracefs.py', '--ap-worker', '11:1000',
                  '--px4-worker', '22:2000', '--supervisor', '33:3000',
                  '--boot-id', 'boot', '--run-id', 'run', '--epoch', 'a'*32,
                  '--output', str(output), '--capture-gate-release', str(Path(temp)/'release'),
                  '--map-comm', '--exchange-dir', temp]
            with patch.object(sys,'argv',argv), \
                 patch.object(collector.os,'geteuid',return_value=0,create=True):
                with self.assertRaisesRegex(ValueError,'ap_fc and px4_fc'):
                    collector.main()
            self.assertFalse(output.exists())

    def test_boot_and_starttime_are_both_checked(self):
        owners={'ap_worker':dict(pid=123,start_ticks=456)}
        with patch.object(collector,'boot',return_value='boot'),patch.object(collector,'identity',return_value=dict(pid=123,start_ticks=999)):
            with self.assertRaisesRegex(ValueError,'Boot identity'):collector.verify(owners,'other')
            with self.assertRaisesRegex(ValueError,'Owned lifetime'):collector.verify(owners,'boot')

    def test_statistics_retains_unknown_loss_counters(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cpu=root/'per_cpu/cpu0';cpu.mkdir(parents=True)
            (cpu/'stats').write_text('overrun: 2\ncommit overrun: 0\n')
            result=collector.statistics(root)
            self.assertEqual(result['loss_counts']['cpu0'],{'overrun':2,'commit overrun':0,'dropped events':None})
            self.assertIn('overrun: 2',result['raw']['cpu0'])

    def test_role_binding_rejects_foreign_epoch(self):
        epoch='a'*32;run='owned-run'
        found={role:dict(argv=['python3','-m','Simulator.wksim_core.worker','--epoch',epoch,
            '--trace',f'/root/{run}/epochs/{epoch}/{stack}-truth.jsonl'])
            for role,stack in [('ap_worker','arducopter'),('px4_worker','px4')]}
        found['supervisor']=dict(argv=['python3','-m','Simulator.wksim_runtime.joint_runtime',f'/root/{run}',epoch,'1'])
        found['ap_fc']=dict(argv=['/tmp/arducopter','--defaults',f'/root/{run}/epochs/{epoch}/arducopter/dds.parm'])
        found['px4_fc']=dict(argv=['/tmp/px4','-w',f'/root/{run}/epochs/{epoch}/px4'])
        collector.verify_roles(found,run,epoch)
        with self.assertRaisesRegex(ValueError,'Worker epoch'):
            collector.verify_roles(found,run,'b'*32)

    def test_sched_mapping_accepts_one_pid_per_exact_comm(self):
        names={'ap_worker':'wk-a','px4_worker':'wk-p'}
        event=(b'          task-1 [001] .... 1.0: sched_switch: '
               b'prev_comm=wk-a prev_pid=101 prev_prio=120 prev_state=S ==> '
               b'next_comm=wk-p next_pid=102 next_prio=120\n')
        clock=iter((0.0,0.0,0.1,0.1))
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            calls=[]
            with patch.object(collector.os,'open',return_value=9), \
                 patch.object(collector.os,'read',return_value=event), \
                 patch.object(collector.os,'close') as close, \
                 patch.object(collector.select,'select',return_value=([9],[],[])), \
                 patch.object(collector.time,'monotonic',side_effect=lambda:next(clock)):
                result=collector.map_sched_switch_pids(Path(temp)/'instance',
                    lambda relative,value:calls.append((relative,value)),names,output)
            self.assertEqual(result,{'ap_worker':101,'px4_worker':102})
            self.assertEqual((output/'pid-mapping-trace.txt').read_bytes(),event)
            self.assertEqual(calls[-3:],[('tracing_on','0'),
                                         ('events/sched/sched_switch/enable','0'),('trace','')])
            close.assert_called_once_with(9)

    def test_sched_mapping_retain_keeps_bootstrap_trace_window_enabled(self):
        names={'ap_worker':'wk-a'}
        event=b'prev_comm=wk-a prev_pid=101 prev_prio=120 prev_state=S\n'
        clock=iter((0.0,0.0,0.1,0.1))
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp); calls=[]
            with patch.object(collector.os,'open',return_value=9), \
                 patch.object(collector.os,'read',return_value=event), \
                 patch.object(collector.os,'close') as close, \
                 patch.object(collector.select,'select',return_value=([9],[],[])), \
                 patch.object(collector.time,'monotonic',side_effect=lambda:next(clock)):
                result=collector.map_sched_switch_pids(Path(temp)/'instance',
                    lambda relative,value:calls.append((relative,value)),names,output,retain=True)
            self.assertEqual(result,{'ap_worker':101})
            self.assertNotIn(('tracing_on','0'),calls)
            self.assertNotIn(('events/sched/sched_switch/enable','0'),calls)
            self.assertNotIn(('trace',''),calls)
            close.assert_called_once_with(9)

    def test_sched_mapping_rejects_ambiguous_comm_pid(self):
        names={'ap_worker':'wk-a'}
        event=(b'prev_comm=wk-a prev_pid=101 prev_prio=120 prev_state=S ==> next_comm=idle next_pid=0\n'
               b'prev_comm=wk-a prev_pid=999 prev_prio=120 prev_state=S ==> next_comm=idle next_pid=0\n')
        clock=iter((0.0,0.0,0.1))
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(collector.os,'open',return_value=9), \
                 patch.object(collector.os,'read',return_value=event), \
                 patch.object(collector.os,'close'), \
                 patch.object(collector.select,'select',return_value=([9],[],[])), \
                 patch.object(collector.time,'monotonic',side_effect=lambda:next(clock)):
                with self.assertRaisesRegex(ValueError,'mapping ambiguous: ap_worker'):
                    collector.map_sched_switch_pids(Path(temp)/'instance',lambda *args:None,
                        names,Path(temp))

    def test_sched_mapping_rejects_missing_comm_at_deadline(self):
        names={'ap_worker':'wk-a'}
        clock=iter((0.0,0.0,3.0,3.0))
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(collector.os,'open',return_value=9), \
                 patch.object(collector.os,'close'), \
                 patch.object(collector.select,'select',return_value=([],[],[])), \
                 patch.object(collector.time,'monotonic',side_effect=lambda:next(clock)):
                with self.assertRaisesRegex(ValueError,'mapping timed out: ap_worker'):
                    collector.map_sched_switch_pids(Path(temp)/'instance',lambda *args:None,
                        names,Path(temp))

    def test_sched_mapping_parses_final_line_without_newline(self):
        names={'ap_worker':'wk-a'}
        event=b'prev_comm=wk-a prev_pid=101 prev_prio=120 prev_state=S'
        clock=iter((0.0,0.0,0.1,3.0))
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(collector.os,'open',return_value=9), \
                 patch.object(collector.os,'read',return_value=event), \
                 patch.object(collector.os,'close'), \
                 patch.object(collector.select,'select',return_value=([9],[],[])), \
                 patch.object(collector.time,'monotonic',side_effect=lambda:next(clock)):
                result=collector.map_sched_switch_pids(Path(temp)/'instance',lambda *args:None,
                    names,Path(temp))
            self.assertEqual(result,{'ap_worker':101})

    def test_kernel_mapping_uses_exact_comm_scheduler_window(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);instance=root/'instance';instance.mkdir();output=root/'output';output.mkdir()
            owners={role:dict(pid=pid,start_ticks=1) for role,pid in (
                ('ap_worker',11),('px4_worker',22),('supervisor',33),('ap_fc',44),('px4_fc',55))}
            epoch='a'*32
            # The base roles model the real WSL PID-namespace split the diagnostic
            # exposed: the namespace-local pid (the /proc directory name, e.g. 11)
            # differs from the kernel/global pid the sched_switch tracepoint reports
            # (1001).  NSpid binds both: NSpid[0]=global, NSpid[-1]=local.
            base_global={'ap_worker':1001,'px4_worker':1002,'supervisor':1003}
            def add_status(path,local,name,global_tid,tgid=None):
                path.mkdir(parents=True,exist_ok=True)
                path.joinpath('comm').write_text(name+'\n')
                path.joinpath('status').write_text(f'Name:\t{name}\nTgid:\t{tgid or local}\n')
                task=path/'task'/str(local);task.mkdir(parents=True,exist_ok=True)
                fields=['S']+['0']*18+[str(5000+local)]
                task.joinpath('stat').write_text(f'{local} ({name}) '+' '.join(fields)+'\n')
                task.joinpath('status').write_text(
                    f'Name:\t{name}\nTgid:\t{tgid or local}\nNSpid:\t{global_tid}\t{local}\n')
                task.joinpath('comm').write_text(name+'\n')
            for role,pid,suffix in (('ap_worker',11,'a'),('px4_worker',22,'p'),('supervisor',33,'s')):
                name='wk'+epoch[:11]+suffix
                add_status(root/'proc'/str(pid),pid,name,base_global[role])
            for process_role,names in collector.FC_THREADS.items():
                pid=owners[process_role]['pid']
                for offset,name in enumerate(names,1):
                    tid=pid+offset
                    process=root/'proc'/str(pid)/'task'/str(tid)
                    fields=['S']+['0']*18+[str(5000+tid)]
                    process.mkdir(parents=True)
                    process.joinpath('stat').write_text(f'{tid} ({name}) '+' '.join(fields)+'\n')
                    process.joinpath('status').write_text(f'Name:\t{name}\nTgid:\t{pid}\nNSpid:\t{tid}\n')
                    process.joinpath('comm').write_text(name+'\n')
            mapped=dict(base_global,
                        **{'ap_fc/arducopter':45,'ap_fc/log_io':46,'ap_fc/DDS':47,
                           'px4_fc/sim_send':56,'px4_fc/logger':57,
                           'px4_fc/wq:lp_default':58})
            (output/'pid-mapping-trace.txt').write_bytes(b'fixture')
            with patch.object(collector,'Path',side_effect=lambda value:root/'proc' if value=='/proc' else Path(value)), \
                 patch.object(collector,'map_sched_switch_pids',return_value=mapped) as map_pids:
                result=collector.map_kernel_pids(instance,lambda *args:None,owners,epoch,output)
            self.assertEqual({k:result['kernel_pids'][k] for k in collector.BASE_ROLES},
                             {k:mapped[k] for k in collector.BASE_ROLES})
            self.assertEqual(result['local_threads']['ap_fc/log_io']['comm'],'log_io')
            map_pids.assert_called_once()
            filtered=collector.filters(result['kernel_pids'])
            self.assertIn('common_pid == '+str(result['kernel_pids']['px4_fc/logger']),
                          filtered['syscalls/sys_enter_fsync'])

    def test_global_comm_ownership_rejects_foreign_same_name(self):
        with tempfile.TemporaryDirectory() as temp:
            proc=Path(temp)
            for tgid,tid,name in ((44,45,'logger'),(99,100,'logger')):
                task=proc/str(tgid)/'task'/str(tid);task.mkdir(parents=True)
                task.joinpath('comm').write_text(name+'\n')
            expected={'logger':dict(role='px4_fc/logger',tgid=44,tid=45)}
            with self.assertRaisesRegex(ValueError,'Global comm ownership mismatch'):
                collector.scan_global_comm_owners(expected,proc)

    def test_required_fc_threads_rejects_duplicate_comm(self):
        owners={'ap_fc':dict(pid=44),'px4_fc':dict(pid=55)}
        inventories={44:[dict(local_tid=44,comm='arducopter',start_ticks=1),
                         dict(local_tid=45,comm='log_io',start_ticks=2),
                         dict(local_tid=46,comm='log_io',start_ticks=3),
                         dict(local_tid=47,comm='DDS',start_ticks=4)],
                     55:[dict(local_tid=55,comm='sim_send',start_ticks=1),
                         dict(local_tid=56,comm='logger',start_ticks=2),
                         dict(local_tid=57,comm='wq:lp_default',start_ticks=3)]}
        with patch.object(collector,'task_inventory',side_effect=lambda pid:inventories[pid]), \
             self.assertRaisesRegex(ValueError,'absent/ambiguous: ap_fc/log_io'):
            collector.required_fc_threads(owners)

    def test_wait_required_fc_threads_allows_startup_absence_then_seals_inventory(self):
        owners={'ap_fc':dict(pid=44),'px4_fc':dict(pid=55)}
        complete={44:[dict(local_tid=44,comm='arducopter',start_ticks=1),
                      dict(local_tid=45,comm='log_io',start_ticks=2),
                      dict(local_tid=46,comm='DDS',start_ticks=3)],
                  55:[dict(local_tid=55,comm='sim_send',start_ticks=4),
                      dict(local_tid=56,comm='logger',start_ticks=5),
                      dict(local_tid=57,comm='wq:lp_default',start_ticks=6)]}
        calls=iter((complete[44][0:2],complete[55],complete[44],complete[55],complete[44],complete[55]))
        with patch.object(collector,'task_inventory',side_effect=lambda pid:next(calls)), \
             patch.object(collector.time,'monotonic',side_effect=(0.,0.,1.)), \
             patch.object(collector.time,'sleep'):
            selected,inventories=collector.wait_required_fc_threads(owners,timeout=2.)
        self.assertEqual(selected['ap_fc/arducopter']['local_tid'],44)
        self.assertEqual(inventories['px4_fc'][-1]['comm'],'wq:lp_default')

    def test_wait_required_fc_threads_fails_closed_on_ambiguous_name(self):
        owners={'ap_fc':dict(pid=44),'px4_fc':dict(pid=55)}
        rows={44:[dict(local_tid=44,comm='arducopter',start_ticks=1),
                  dict(local_tid=45,comm='log_io',start_ticks=2),
                  dict(local_tid=46,comm='log_io',start_ticks=3),
                  dict(local_tid=47,comm='DDS',start_ticks=4)],
              55:[]}
        with patch.object(collector,'task_inventory',side_effect=lambda pid:rows[pid]), \
             self.assertRaisesRegex(ValueError,'ownership ambiguous: ap_fc/log_io'):
            collector.wait_required_fc_threads(owners,timeout=.1)

    def test_empty_capture_is_not_complete_even_with_no_reported_loss(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);instance=root/'instance';instance.mkdir();output=root/'output';output.mkdir()
            controls=dict(tracing_on='1',current_tracer='nop',trace_clock='mono')
            for name,value in controls.items():(root/name).write_text(value)
            (output/'trace.txt').write_bytes(b'')
            metadata=dict(errors=[])
            with patch.object(collector,'TRACE',root),patch.object(collector,'guarded_instance'), \
                 patch.object(collector,'statistics',return_value=dict(loss_counts={'cpu0':{k:0 for k in collector.LOSS}})), \
                 patch.object(collector,'verify',return_value={}),patch.object(Path,'rmdir'):
                collector.finalize_capture(instance,(1,1),None,metadata,output,dict(global_controls=controls),
                    {},'boot',{},[],1,1_000_000_001)
            self.assertFalse(metadata['events_observed'])
            self.assertFalse(metadata['complete'])
            self.assertEqual(metadata['status'],'diagnostic_partial')

    def test_capture_active_token_is_exclusive_and_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'capture-active.json'
            (Path(temp)/'instance-owner.json').write_text(json.dumps(
                dict(schema='wksim.private-tracefs.instance-owner.v1',
                     instance='/sys/kernel/tracing/instances/wksim-rate-'+'a'*32,
                     instance_inode=[1,2],collector_pid=456,collector_start_ticks=456,
                     supervisor_pid=789,supervisor_start_ticks=790,
                     run_id='run',epoch='b'*32,boot_id='boot',owners={
                         'supervisor':{'pid':789,'start_ticks':790}}), sort_keys=True)+'\n')
            metadata=dict(instance='/sys/kernel/tracing/instances/wksim-rate-'+'a'*32,
                          instance_inode=[1,2],run_id='run',epoch='b'*32,
                          started_monotonic_ns=123,collector_start_ticks=456,
                          owners={'supervisor':{'pid':789,'start_ticks':790}})
            payload=collector.emit_capture_active(target,metadata)
            self.assertEqual(payload['schema'],'wksim.private-tracefs.capture-active.v1')
            self.assertEqual(payload['collector_start_ticks'],456)
            self.assertEqual(payload['supervisor_start_ticks'],790)
            self.assertEqual(payload['instance_owner_sha256'],
                             hashlib.sha256((Path(temp)/'instance-owner.json').read_bytes()).hexdigest())
            self.assertIsInstance(payload['published_monotonic_ns'],int)
            self.assertEqual(json.loads(target.read_text()),payload)
            self.assertEqual(metadata['capture_active'],payload)
            with self.assertRaises(FileExistsError):
                collector.emit_capture_active(target,metadata)

    def test_capture_active_token_uses_create_only_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'capture-active.json'
            (Path(temp)/'instance-owner.json').write_text(json.dumps(
                dict(schema='wksim.private-tracefs.instance-owner.v1')))
            metadata=dict(instance='/sys/kernel/tracing/instances/wksim-rate-'+'a'*32,
                          instance_inode=[1,2],run_id='run',epoch='b'*32,
                          started_monotonic_ns=123,collector_start_ticks=456,
                          owners={'supervisor':{'pid':789,'start_ticks':790}})
            with patch.object(collector.os,'link',wraps=collector.os.link) as link, \
                 patch.object(collector.os,'replace',side_effect=AssertionError('replace is not create-only')):
                collector.emit_capture_active(target,metadata)
            link.assert_called_once()

    def test_capture_bootstrap_token_uses_explicit_bootstrap_start_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'capture-bootstrap-active.json'
            (Path(temp)/'instance-owner.json').write_text(json.dumps(
                dict(schema='wksim.private-tracefs.instance-owner.v1',
                     instance='/sys/kernel/tracing/instances/wksim-rate-'+'a'*32,
                     instance_inode=[1,2],collector_pid=456,collector_start_ticks=456,
                     supervisor_pid=789,supervisor_start_ticks=790,
                     run_id='run',epoch='b'*32,boot_id='boot',owners={
                         'supervisor':{'pid':789,'start_ticks':790}}), sort_keys=True)+'\n')
            metadata=dict(instance='/sys/kernel/tracing/instances/wksim-rate-'+'a'*32,
                          instance_inode=[1,2],run_id='run',epoch='b'*32,
                          bootstrap_started_monotonic_ns=123,
                          collector_start_ticks=456,
                          owners={'supervisor':{'pid':789,'start_ticks':790}})
            payload=collector.emit_capture_bootstrap(target,metadata)
            self.assertEqual(payload['schema'],'wksim.private-tracefs.capture-bootstrap-active.v1')
            self.assertEqual(payload['state'],'bootstrap_active')
            self.assertEqual(payload['phase'],'bootstrap_sched_switch')
            self.assertEqual(payload['started_monotonic_ns'],123)
            self.assertEqual(json.loads(target.read_text()),payload)

    def test_bootstrap_loss_counter_delta_is_fail_closed(self):
        before={'loss_counts':{'cpu0':{'overrun':0,'commit overrun':0,'dropped events':0}}}
        after={'loss_counts':{'cpu0':{'overrun':1,'commit overrun':0,'dropped events':0}}}
        delta,loss_free=collector.loss_counter_delta(before,after)
        self.assertEqual(delta['cpu0']['overrun'],1)
        self.assertFalse(loss_free)

    def test_enable_capture_publishes_token_after_enable_write(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'capture-active.json'
            (Path(temp)/'instance-owner.json').write_text(json.dumps(
                dict(schema='wksim.private-tracefs.instance-owner.v1')))
            metadata=dict(instance='/sys/kernel/tracing/instances/wksim-rate-'+'a'*32,
                          instance_inode=[1,2],run_id='run',epoch='b'*32,
                          collector_start_ticks=456,
                          owners={'supervisor':{'pid':789,'start_ticks':790}})
            calls=[]
            with patch.object(collector.time,'monotonic_ns',return_value=123), \
                 patch.object(collector.time,'time_ns',return_value=456):
                began,deadline=collector.enable_capture(
                    lambda relative,value:calls.append((relative,value)),1,metadata,target)
            self.assertEqual((began,deadline),(123,1_000_000_123))
            self.assertEqual(calls,[('tracing_on','1')])
            self.assertEqual(json.loads(target.read_text())['state'],'active')


NS_INODE = 4026532221
BOOT = 'boot-under-test'
EPOCH = 'a' * 32


def make_task_record(global_tgid, global_tid, local_tgid, local_tid, comm, ticks):
    stat = make_stat(global_tid, comm, ticks)
    status = make_status(comm, global_tgid, global_tid,
                         [global_tgid, local_tgid], [global_tid, local_tid])
    return dict(global_tgid=global_tgid, global_tid=global_tid,
                local_tgid=local_tgid, local_tid=local_tid, comm=comm,
                start_ticks=ticks, is_leader=local_tid == local_tgid,
                evidence=dict(stat_before=stat, stat_after=stat, status=status,
                              comm=comm, ns_link=f'pid:[{NS_INODE}]'))


def make_snapshot(owner_map, *, ticks_shift=0, drop_leader=None, include_fc_threads=False):
    """owner_map: role -> (local_pid, ticks, comm, global_tid)."""
    records = {}
    tasks = []
    for role, (pid, ticks, comm, gtid) in owner_map.items():
        rec = make_task_record(gtid, gtid, pid, pid, comm, ticks + ticks_shift)
        tasks.append(rec)
        if role != drop_leader:
            records[str(pid)] = rec
    if include_fc_threads:
        for role,names in collector.FC_THREADS.items():
            pid,ticks,_comm,gtid=owner_map[role]
            for offset,name in enumerate(names,1):
                tasks.append(make_task_record(gtid,gtid+offset,pid,pid+offset,
                                              name,ticks+offset))
    return dict(lsns_evidence=dict(raw=VALID_LSNS), leaders=records, tasks=tasks)


def make_post_mapping(owner_map, *, include_ap=False, include_threads=False):
    base={role:dict(local_tid=pid,local_tgid=pid,comm=comm,
                    start_ticks=ticks,global_tid=gtid,global_tgid=gtid)
          for role,(pid,ticks,comm,gtid) in owner_map.items()
          if role in collector.BASE_ROLES}
    kernel={role:record['global_tid'] for role,record in base.items()}
    if include_ap:
        pid,ticks,comm,gtid=owner_map['ap_fc']
        base['ap_fc/arducopter']=dict(local_tid=pid,local_tgid=pid,
                                      comm=comm,start_ticks=ticks,
                                      global_tid=gtid,global_tgid=gtid)
        kernel['ap_fc/arducopter']=gtid
    local_threads={}
    fc_leaders={}
    for fc_role,names in collector.FC_THREADS.items():
        pid,ticks,comm,gtid=owner_map[fc_role]
        fc_leaders[fc_role]=dict(local_tid=pid,local_tgid=pid,comm=comm,
                                 start_ticks=ticks,global_tid=gtid,
                                 global_tgid=gtid)
        if include_threads:
            for offset,name in enumerate(names,1):
                role=fc_role+'/'+name
                if role == 'ap_fc/arducopter' and include_ap:
                    local_threads[role]=dict(local_tid=pid,local_tgid=pid,
                                             comm=comm,start_ticks=ticks)
                    continue
                local_threads[role]=dict(local_tid=pid+offset,local_tgid=pid,
                                         comm=name,start_ticks=ticks+offset)
                kernel[role]=gtid+offset
    return dict(base_leaders=base,fc_leaders=fc_leaders,
                local_threads=local_threads,kernel_pids=kernel)


class ExchangeIntegration(unittest.TestCase):
    """Fixture-level two-phase exchange binding; no tracefs, no service process."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.exchange = Path(self.dir.name)
        self.owners = {'ap_worker': {'pid': 11, 'start_ticks': 1000},
                       'px4_worker': {'pid': 22, 'start_ticks': 2000},
                       'supervisor': {'pid': 33, 'start_ticks': 3000},
                       'ap_fc': {'pid': 44, 'start_ticks': 4000},
                       'px4_fc': {'pid': 55, 'start_ticks': 5000}}
        self.owner_map = {'ap_worker': (11, 1000, 'wk-alpha', 1011),
                          'px4_worker': (22, 2000, 'wk-px4p', 1022),
                          'supervisor': (33, 3000, 'wk-supers', 1033),
                          'ap_fc': (44, 4000, 'arducopter', 1044),
                          'px4_fc': (55, 5000, 'px4', 1055)}
        self.args = SimpleNamespace(run_id='run-x', epoch=EPOCH, boot_id=BOOT,
                                    exchange_dir=self.exchange)
        self.patches = [
            patch.object(collector, 'detect_local_pid_ns_inode', return_value=NS_INODE),
            patch.object(collector, 'identity',
                         return_value={'pid': 99, 'start_ticks': 9000}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def _service(self, phase, snapshot, mutate=None):
        def serve():
            req_path = self.exchange / (phase + '.request.json')
            deadline = time.monotonic() + 5
            while not req_path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            raw = req_path.read_bytes()
            req = decode_json_strict(raw)
            response = make_snapshot_response(request=req, request_bytes=raw,
                                              boot_id=BOOT, snapshot=snapshot)
            if mutate is not None:
                response = mutate(response)
            publish_create_only(self.exchange / (phase + '.response.json'), response)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        return thread

    def _local_inventory(self, pid):
        for role, (lpid, ticks, comm, gtid) in self.owner_map.items():
            if lpid == pid:
                return [dict(local_tid=pid, global_tid=gtid, comm=comm,
                             start_ticks=ticks)]
        raise AssertionError('unexpected pid')

    def _pre(self, snapshot, mutate=None):
        self._service(collector.EXCHANGE_PHASE_PRE, snapshot, mutate)
        with patch.object(collector, 'task_inventory', side_effect=self._local_inventory):
            return collector.pre_bootstrap_leaders(self.args, {}, self.owners)

    def test_normal_two_phase_binding(self):
        proven = self._pre(make_snapshot(self.owner_map))
        self.assertEqual(proven['ap_fc']['global_tid'], 1044)
        self.assertEqual(proven['px4_fc']['global_tgid'], 1055)

        self.assertEqual(proven['supervisor']['proof'], 'root_snapshot_exchange')

        metadata = {}
        self._service(collector.EXCHANGE_PHASE_POST,
                      make_snapshot(self.owner_map, include_fc_threads=True))
        mapping = make_post_mapping(self.owner_map, include_ap=True, include_threads=True)
        verified = collector.post_capture_tasks(self.args, metadata, self.owners, mapping)
        self.assertEqual(verified, mapping['kernel_pids'])
        self.assertEqual(metadata['post_capture_tasks_proof']['count'],
                         len(mapping['kernel_pids']))

    def test_visible_wsl_pns_zero_cannot_prove_kernel_pids(self):
        snapshot = make_snapshot(self.owner_map)
        snapshot['lsns_evidence']['raw'] = SYSTEM_VIEW_LSNS
        # Even a claimed summary flag cannot override the raw namespace proof.
        snapshot['kernel_global_proven'] = True
        with self.assertRaisesRegex(ValueError, 'not the initial kernel PID namespace'):
            self._pre(snapshot)

    def test_pre_rejects_leader_summary_not_bound_to_raw_task(self):
        snapshot = make_snapshot(self.owner_map)
        snapshot['leaders']['44'] = dict(snapshot['leaders']['44'], global_tid=9999)
        with self.assertRaisesRegex(ValueError, 'Leader summary differs from raw task'):
            self._pre(snapshot)

    def test_post_rejects_global_tgid_drift(self):
        snapshot = make_snapshot(self.owner_map)
        task = next(task for task in snapshot['tasks'] if task['comm'] == 'wk-alpha')
        task['global_tgid'] = 9999
        task['evidence']['status'] = make_status(task['comm'], 9999,
                                                 task['global_tid'],
                                                 [9999, task['local_tgid']],
                                                 [task['global_tid'], task['local_tid']])
        self._service(collector.EXCHANGE_PHASE_POST, snapshot)
        mapping = make_post_mapping(self.owner_map)
        with self.assertRaisesRegex(ValueError, 'global tgid differs'):
            collector.post_capture_tasks(self.args, {}, self.owners, mapping)

    def test_wrong_boot_rejected(self):
        with self.assertRaisesRegex(ValueError, 'boot_id'):
            self._pre(make_snapshot(self.owner_map),
                      mutate=lambda r: dict(r, boot_id='other-boot'))

    def test_wrong_epoch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'epoch'):
            self._pre(make_snapshot(self.owner_map),
                      mutate=lambda r: dict(r, epoch='b' * 32))

    def test_wrong_owner_ticks_rejected(self):
        with self.assertRaisesRegex(ValueError, 'start_ticks differ'):
            self._pre(make_snapshot(self.owner_map, ticks_shift=1))

    def test_thread_reuse_post_capture_rejected(self):
        metadata = {}
        reused = make_snapshot(self.owner_map, ticks_shift=7)
        self._service(collector.EXCHANGE_PHASE_POST, reused)
        mapping = make_post_mapping(self.owner_map)
        with self.assertRaisesRegex(ValueError, 'start_ticks differ'):
            collector.post_capture_tasks(self.args, metadata, self.owners, mapping)
        self.assertNotIn('post_capture_tasks_proof', metadata)

    def test_missing_post_target_fails_final_verification(self):
        metadata = {}
        partial = make_snapshot(self.owner_map, drop_leader='supervisor')
        partial['tasks'] = [t for t in partial['tasks'] if t['comm'] != 'wk-supers']
        self._service(collector.EXCHANGE_PHASE_POST, partial)
        mapping = make_post_mapping(self.owner_map)
        mapping['base_leaders'].pop('px4_worker')
        mapping['kernel_pids'].pop('px4_worker')
        with self.assertRaisesRegex(ValueError, 'absent from post-capture snapshot'):
            collector.post_capture_tasks(self.args, metadata, self.owners, mapping)
        self.assertNotIn('post_capture_tasks_proof', metadata)

    def test_ap_same_comm_helper_is_evidence_not_ambiguity(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            lines = iter([
                'x  [0]  sched_switch: prev_comm=arducopter prev_pid=1055 prev_prio=59 prev_state=R ==> next_comm=other next_pid=1',
                'x  [0]  sched_switch: prev_comm=arducopter prev_pid=1044 prev_prio=59 prev_state=R ==> next_comm=other next_pid=1',
            ])
            evidence = []

            def fake_read(descriptor, count):
                try:
                    return next(lines).encode() + b'\n'
                except StopIteration:
                    return b''

            with patch.object(collector.os, 'open', return_value=0), \
                    patch.object(collector.os, 'read', side_effect=fake_read), \
                    patch.object(collector.select, 'select', return_value=([0], [], [])), \
                    patch.object(collector.os, 'close'), \
                    patch.object(collector.time, 'monotonic', side_effect=[float(i) / 10 for i in range(40)]):
                mapped = collector.map_sched_switch_pids(
                    output, lambda *a: None, {'ap_fc/arducopter': 'arducopter'}, output,
                    expected={'ap_fc/arducopter': 1044}, evidence=evidence)
            self.assertEqual(mapped, {'ap_fc/arducopter': 1044})
            self.assertEqual(evidence, [{'role': 'ap_fc/arducopter', 'comm': 'arducopter',
                                         'kernel_pid': 1055}])

    def test_completion_gate_requires_post_capture_proof(self):
        source = (Path(collector.__file__).read_text(encoding='utf-8'))
        line = next(l for l in source.splitlines() if "metadata['complete']=" in l)
        self.assertIn("post_capture_tasks_proof", line)


if __name__=='__main__':unittest.main()
