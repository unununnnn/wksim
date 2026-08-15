"""No kernel tracing: parser, filter, path ownership and preflight guards only."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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

    def test_kernel_mapping_uses_owned_names_and_rejects_shared_thread_name(self):
        for ambiguous in (False, True):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);instance=root/'instance';instance.mkdir();output=root/'output';output.mkdir()
                owners={role:dict(pid=pid,start_ticks=1) for role,pid in (
                    ('ap_worker',11),('px4_worker',22),('supervisor',33),('ap_fc',44),('px4_fc',55))}
                epoch='a'*32;lines=[]
                for role,pid,suffix,kernel in (('ap_worker',11,'a',1011),('px4_worker',22,'p',1022),('supervisor',33,'s',1033)):
                    name='wk'+epoch[:11]+suffix
                    process=root/'proc'/str(pid);process.mkdir(parents=True)
                    (process/'comm').write_text(name+'\n')
                    lines.append(f'prev_comm={name} prev_pid={kernel} prev_prio=120 prev_state=S ==> next_comm=idle next_pid=0\n')
                kernel=1040
                for process_role,names in collector.FC_THREADS.items():
                    pid=owners[process_role]['pid']
                    for offset,name in enumerate(names,1):
                        tid=pid+offset;process=root/'proc'/str(pid)/'task'/str(tid);process.mkdir(parents=True)
                        fields=['S']+['0']*18+[str(5000+tid)]
                        stat=f'{tid} ({name}) '+ ' '.join(fields)+'\n'
                        (process/'stat').write_text(stat)
                        (process/'status').write_text(f'Name:\t{name}\nTgid:\t{pid}\n')
                        (process/'comm').write_text(name+'\n')
                        kernel+=1
                        lines.append(f'prev_comm={name} prev_pid={kernel} prev_prio=120 prev_state=S ==> next_comm=idle next_pid=0\n')
                if ambiguous:lines.append('next_comm=wk'+epoch[:11]+'s next_pid=2033\n')
                (instance/'trace').write_text(''.join(lines))
                with patch.object(collector,'Path',side_effect=lambda value:root/'proc' if value=='/proc' else Path(value)), \
                     patch.object(collector.time,'sleep'):
                    if ambiguous:
                        with self.assertRaisesRegex(ValueError,'absent/ambiguous: supervisor'):
                            collector.map_kernel_pids(instance,lambda *args:None,owners,epoch,output)
                    else:
                        result=collector.map_kernel_pids(instance,lambda *args:None,owners,epoch,output)
                        self.assertEqual({k:result['kernel_pids'][k] for k in collector.BASE_ROLES},
                                         dict(ap_worker=1011,px4_worker=1022,supervisor=1033))
                        self.assertEqual(result['local_threads']['ap_fc/log_io']['comm'],'log_io')
                        filtered=collector.filters(result['kernel_pids'])
                        self.assertIn('common_pid == '+str(result['kernel_pids']['px4_fc/logger']),
                                      filtered['syscalls/sys_enter_fsync'])

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


if __name__=='__main__':unittest.main()
