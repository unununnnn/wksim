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
        owners={n:dict(pid=p,start_ticks=1) for n,p in [('ap_worker',11),('px4_worker',22),('supervisor',33)]}
        filters=collector.filters(owners)
        self.assertEqual(set(filters),set(collector.EVENTS))
        self.assertEqual(filters['syscalls/sys_enter_write'],'common_pid == 11 || common_pid == 22')
        self.assertIn('prev_pid == 33 || next_pid == 33',filters['sched/sched_switch'])
        self.assertEqual(filters['sched/sched_wakeup'],'pid == 11 || pid == 22 || pid == 33')

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
        collector.verify_roles(found,run,epoch)
        with self.assertRaisesRegex(ValueError,'Worker epoch'):
            collector.verify_roles(found,run,'b'*32)


if __name__=='__main__':unittest.main()
