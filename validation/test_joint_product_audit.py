"""Small corruption checks for product-specific raw lifecycle adaptation."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_joint_product import lifecycle


class ProductAuditCorruption(unittest.TestCase):
    def check(self, mutate=None):
        message = dict(run_id='run', scene_epoch='epoch', tick=4, time_ns=4000000,
                       phase='paused', lease_seconds=.5)
        data = json.dumps(message).encode() + b'\0'
        rows = [dict(kind='permission', epoch='epoch', tick=4, phase='paused', message=message,
                     cdr_hex=(b'\0\1\0\0' + struct.pack('<I', len(data)) + data).hex()),
                dict(kind='paused_clock', epoch='epoch', tick=4, phase='paused',
                     time_ns=4000000, publication=6)]
        if mutate:
            mutate(rows)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'scene-lifecycle.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            return lifecycle(directory, 'epoch', 4, 6, 'run')

    def test_retained_raw_permission(self):
        self.assertEqual(self.check(), dict(permissions=1, clock_republications=1))

    def test_summary_cannot_override_raw_permission(self):
        with self.assertRaisesRegex(ValueError, 'Raw permission differs'):
            self.check(lambda rows: rows[0]['message'].update(lease_seconds=5))

    def test_clock_replay_cannot_count_as_progress(self):
        with self.assertRaisesRegex(ValueError, 'fabricated'):
            self.check(lambda rows: rows[1].update(time_ns=5000000))

    def test_missing_raw_republication_fails(self):
        with self.assertRaisesRegex(ValueError, 'Missing raw'):
            self.check(lambda rows: rows.pop())


if __name__ == '__main__':
    unittest.main()
