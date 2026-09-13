"""Negative audits of retained real global flight evidence; never rerun a vehicle."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from tools.audit_global_flight import audit


@unittest.skipUnless(os.environ.get('WKSIM_GLOBAL_AUDIT_ROOT'), 'Explicit retained global flight required')
class GlobalAuditTests(unittest.TestCase):
    def clone(self, directory, changed):
        source = Path(os.environ['WKSIM_GLOBAL_AUDIT_ROOT'])
        root = Path(directory)/'run'
        root.mkdir()
        for path in source.iterdir():
            if path.name == changed:
                shutil.copy2(path, root/path.name)
            else:
                (root/path.name).symlink_to(path, target_is_directory=path.is_dir())
        return root

    def test_changed_budget_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory, 'global-profile.json')
            path = root/'global-profile.json'; value = json.loads(path.read_text())
            value['position_error_m'] = 5.
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'Frozen global profile changed'): audit(root)

    def test_missing_raw_global_request_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory, 'rc-dds.jsonl')
            path = root/'rc-dds.jsonl'; lines = path.read_text().splitlines()
            path.write_text('\n'.join(line for line in lines
                if not json.loads(line)['topic'].endswith('/v2/global_command'))+'\n')
            with self.assertRaisesRegex(ValueError, 'without raw accepted command'): audit(root)

    def test_decoded_native_output_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory, 'rc-dds.jsonl')
            path = root/'rc-dds.jsonl'; lines = path.read_text().splitlines()
            for index, line in enumerate(lines):
                row = json.loads(line)
                if row['topic'] == '/ap/cmd_gps_pose':
                    row['message']['altitude'] += 1.
                    lines[index] = json.dumps(row)
                    break
            else: self.fail('AP retained native output missing')
            path.write_text('\n'.join(lines)+'\n')
            with self.assertRaisesRegex(ValueError, 'Raw DDS differs'): audit(root)

    def test_missing_physical_terminal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory, 'physics-1ms.jsonl')
            path = root/'physics-1ms.jsonl'
            with path.open('rb+') as stream:
                stream.seek(-200, 2); tail = stream.read()
                offset = tail.rfind(b'{"kind": "end"')
                self.assertGreaterEqual(offset, 0)
                stream.truncate(path.stat().st_size-200+offset)
            with self.assertRaisesRegex(ValueError, 'terminal/hold incomplete'): audit(root)


if __name__ == '__main__': unittest.main()
