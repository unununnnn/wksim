"""Compile actual schedule header and check each rejecting boundary in a process."""
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(platform.system()=='Linux','native C++ fixture runs in WSL')
class ScheduleHeaderTests(unittest.TestCase):
    def test_schedule_generation_and_clock_boundaries(self):
        cases={'bounds':None,'long_tick':None,'fresh_generation':None,
               'late':'late_or_invalid_plan','noncanonical':'noncanonical_plan',
               'changed':'plan_changed','missing':'missing_or_misplaced_plan',
               'late_recreate':'sensor_recreated_outside_recovery_window',
               'old_generation':'stale_or_replayed_sample','overrun':'nonconsecutive_tick'}
        with tempfile.TemporaryDirectory(prefix='wksim-gnss-schedule-') as directory:
            root=Path(directory);binary=root/'fixture'
            subprocess.run(['g++','-std=c++11','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'tools/ap_gnss_flight'),str(ROOT/'validation/ap_gnss_schedule_fixture.cpp'),
                '-o',str(binary)],check=True,capture_output=True)
            for case,reason in cases.items():
                with self.subTest(case=case):
                    trace=root/(case+'.tsv')
                    result=subprocess.run([str(binary),case],env=dict(os.environ,WKSIM_RUN='a'*32,
                        WKSIM_EPOCH='b'*32,WKSIM_GNSS_TRACE=str(trace)),capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,109 if reason else 0,result.stderr)
                    if reason:self.assertIn(reason,trace.read_text())


if __name__=='__main__':unittest.main()
