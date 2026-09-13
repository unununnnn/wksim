"""Large report parsing leaves the paced loop; retirement still checks identity."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from Simulator.wksim_runtime.joint_evidence import task_group_completed,load_retired_task_report


class DeferredReportTests(unittest.TestCase):
    def test_paced_completion_never_reads_reports(self):
        class Unreadable:
            def is_file(self):raise AssertionError('report I/O on the rate deadline')
        for codes,expected in (((0,0),True),((0,None),False),((0,1),False)):
            workers=[NS(poll=lambda code=code:code) for code in codes]
            self.assertEqual(task_group_completed(workers,[Unreadable(),Unreadable()],defer_report_reads=True),expected)

    def test_retirement_rejects_missing_foreign_or_failed_success_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.json'
            good=dict(run_id='run',scene_epoch='a'*32,stack='px4',status='pass')
            path.write_text(json.dumps(good))
            self.assertEqual(load_retired_task_report(path,'run','a'*32,'px4',0),good)
            for patch in ({'run_id':'other'},{'scene_epoch':'b'*32},{'stack':'arducopter'},{'status':'failed'}):
                path.write_text(json.dumps(good|patch))
                with self.assertRaises(ValueError):load_retired_task_report(path,'run','a'*32,'px4',0)
            path.unlink()
            with self.assertRaises(FileNotFoundError):load_retired_task_report(path,'run','a'*32,'px4',0)


if __name__=='__main__':unittest.main()
