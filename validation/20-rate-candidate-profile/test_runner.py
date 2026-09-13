"""Offline failure-boundary tests; never start the formal service."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rate61_runner', HERE/'run-one.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerFailures(unittest.TestCase):
    def test_failed_preflight_preserved_without_launch(self):
        with tempfile.TemporaryDirectory(prefix='runner-test-',dir=HERE) as name:
            root = Path(name)
            config = json.loads((HERE/'experiment-1.json').read_text())
            manifest = dict(candidate_id='test',runs={'1':dict(evidence='case-parent',output_root=str(root/'output'))})
            with patch.object(runner,'ROOT',root), patch.object(runner,'check',return_value=(manifest,config)), \
                    patch.object(runner.subprocess,'run',return_value=subprocess.CompletedProcess([],2)) as preflight, \
                    patch.object(runner.subprocess,'Popen') as launch, patch.object(runner.sys,'argv',['run-one.py','1']):
                self.assertEqual(runner.main(),1)
            launch.assert_not_called()
            self.assertEqual(preflight.call_count,1)
            record = json.loads((root/'case-parent/case/wrapper.json').read_text())
            self.assertEqual(record['preflight_returncode'],2)
            self.assertIsNone(record['manager_returncode'])
            self.assertEqual(record['remaining_manager_group'],[])
            self.assertIn('resource preflight rejected',record['error'])

    def test_failed_previous_audit_blocks_next_epoch(self):
        with tempfile.TemporaryDirectory(prefix='runner-test-',dir=HERE) as name:
            root = Path(name)
            (root/'audit.json').write_text('{"status":"failed"}')
            manifest = dict(runs={'1':dict(audit='audit.json')})
            with patch.object(runner,'ROOT',root), patch.object(runner,'check',return_value=(manifest,{})), \
                    patch.object(runner.subprocess,'Popen') as launch, patch.object(runner.sys,'argv',['run-one.py','2']):
                with self.assertRaisesRegex(ValueError,'Previous epoch'):
                    runner.main()
            launch.assert_not_called()
            self.assertEqual(sorted(p.name for p in root.iterdir()),['audit.json'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
