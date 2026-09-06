"""Actual private mount test. No flight controller or native command is launched."""
import os
from pathlib import Path
import unittest
import uuid

from Simulator.wksim_runtime.isolation import isolate_temporary_files


@unittest.skipUnless(os.environ.get('WK_PRIVATE_TMP_TESTS')=='1','explicit private mount environment required')
class PrivateTemporaryFilesTests(unittest.TestCase):
    def test_existing_builds_are_readable_but_writes_and_unlinks_do_not_reach_host(self):
        name='wksim-owned-tmp-isolation-'+uuid.uuid4().hex
        host=Path('/proc/1/root/tmp')/name
        host.write_text('owned-host-marker')
        try:
            before=host.stat()
            info=isolate_temporary_files()
            local=Path('/tmp')/name
            self.assertEqual(local.read_text(),'owned-host-marker')
            local.unlink()
            local.write_text('private-version')
            self.assertEqual(host.read_text(),'owned-host-marker')
            self.assertEqual(host.stat().st_ino,before.st_ino)
            self.assertEqual(local.read_text(),'private-version')
            self.assertNotEqual(os.stat('/tmp').st_dev,os.stat('/proc/1/root/tmp').st_dev)
            self.assertTrue(Path(info['artifact_directory']).is_dir())
            self.assertEqual(isolate_temporary_files(),info)
        finally:
            host.unlink()


if __name__=='__main__':unittest.main()
