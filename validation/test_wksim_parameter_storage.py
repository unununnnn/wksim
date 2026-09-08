"""Local POSIX lease checks; no flight processes or external parameter files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from Simulator.wksim_runtime import parameter_storage as storage


@unittest.skipUnless(sys.platform == 'linux', 'Requires real POSIX directory flock')
class ParameterStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        mock = patch.object(storage, 'ROOT', self.root)
        mock.start()
        self.addCleanup(mock.stop)
        self.identity = str(uuid4())

    def acquire(self, **kwargs):
        return storage.ParameterStorage(self.identity, kwargs.pop('stack', 'px4'), **kwargs)

    def firmware(self):
        root = self.root / 'firmware'
        (root / 'build/px4_sitl_default/etc').mkdir(parents=True)
        (root / 'test_data').mkdir()
        return root

    def test_native_px4_links_reopen_without_traversing_firmware(self):
        root = self.firmware()
        (root / 'test_data/external-alias').symlink_to(self.root)
        with self.acquire(px4_root=root) as lease:
            self.assertEqual(list(lease.path.iterdir()), [])
            for name, target in lease.targets.items():
                (lease.path / name).symlink_to(target, target_is_directory=True)
            self.assertEqual(lease.check('px4', root), lease.metadata)
        with self.acquire(reopen=True, px4_root=root) as lease:
            self.assertEqual(lease.check('px4', root)['px4_root'], str(root))
            for stack, configured in [('px4', None), ('arducopter', root)]:
                with self.assertRaises(ValueError):
                    lease.check(stack, configured)
        with self.assertRaisesRegex(ValueError, 'closed'):
            lease.check('px4', root)
        with self.assertRaisesRegex(ValueError, 'marker'):
            self.acquire(reopen=True)

    def test_px4_root_and_native_link_boundaries(self):
        root = self.firmware()
        alias = self.root / 'firmware-alias'
        alias.symlink_to(root, target_is_directory=True)
        for stack, configured in [('arducopter', root), ('px4', alias), ('px4', Path('relative'))]:
            with self.assertRaises(ValueError):
                self.acquire(stack=stack, px4_root=configured)
        with self.acquire(px4_root=root) as lease:
            link = lease.path / 'etc'
            link.symlink_to(root / 'test_data', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'linked'):
                lease.check('px4', root)
            link.unlink()
            (lease.path / 'nested').mkdir()
            link = lease.path / 'nested/etc'
            link.symlink_to(root / 'build/px4_sitl_default/etc', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'linked'):
                lease.check('px4', root)
        with self.assertRaisesRegex(ValueError, 'linked'):
            self.acquire(reopen=True, px4_root=root)

    def test_check_rejects_replaced_parent_and_marker(self):
        with self.acquire() as lease:
            marker = lease.path.parent / 'marker.json'
            original = marker.read_bytes()
            marker.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'marker'):
                lease.check('px4')
            marker.write_bytes(original)
            directory = lease.path.parent
            directory.rename(directory.with_name('displaced'))
            directory.mkdir(mode=0o700)
            with self.assertRaisesRegex(ValueError, 'identity'):
                lease.check('px4')

    def test_preserves_bytes_and_rejects_existing_create_and_wrong_stack(self):
        with self.acquire() as lease:
            path = lease.path / 'test-parameter-data'
            path.write_bytes(b'unchanged\x00\xff')
            metadata = lease.metadata
            with self.assertRaisesRegex(RuntimeError, 'conflict'):
                self.acquire(reopen=True)
        with self.assertRaises(FileExistsError):
            self.acquire()
        with self.assertRaisesRegex(ValueError, 'marker'):
            self.acquire(reopen=True, stack='arducopter')
        with self.acquire(reopen=True) as lease:
            self.assertEqual(path.read_bytes(), b'unchanged\x00\xff')
            self.assertEqual(lease.metadata['marker_sha256'], metadata['marker_sha256'])
        lease.close()
        self.assertTrue(path.exists())

    def test_inherited_lock_survives_parent_close(self):
        lease = self.acquire()
        child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'],
                                 stdin=subprocess.PIPE, pass_fds=(lease.fd,))
        lease.close()
        try:
            with self.assertRaisesRegex(RuntimeError, 'conflict'):
                self.acquire(reopen=True)
        finally:
            child.communicate(timeout=5)
        with self.acquire(reopen=True):
            pass

    def test_two_sequential_processes_reuse_the_same_data(self):
        with self.acquire() as lease:
            subprocess.run([sys.executable, '-c',
                            "from pathlib import Path; Path('test-data').write_bytes(b'retained')"],
                           cwd=lease.path, pass_fds=(lease.fd,), check=True, timeout=5)
        with self.acquire(reopen=True) as lease:
            subprocess.run([sys.executable, '-c',
                            "from pathlib import Path; assert Path('test-data').read_bytes()==b'retained'"],
                           cwd=lease.path, pass_fds=(lease.fd,), check=True, timeout=5)

    def test_inherited_lock_survives_parent_abnormal_exit(self):
        # The intermediate parent exits without cleanup; the bounded child
        # inherits the lock and communicates via files only inside this fixture.
        script = '''import os, pathlib, subprocess, sys
from Simulator.wksim_runtime import parameter_storage as s
s.ROOT=pathlib.Path(sys.argv[1])
lease=s.ParameterStorage(sys.argv[2], 'px4')
code="import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); p.with_suffix('.ready').touch(); deadline=time.monotonic()+5; exec('while not p.exists() and time.monotonic()<deadline: time.sleep(.01)')"
subprocess.Popen([sys.executable,'-c',code,sys.argv[3]],pass_fds=(lease.fd,))
os._exit(17)
'''
        release = self.root / 'release'
        parent = subprocess.run([sys.executable, '-c', script, str(self.root), self.identity, str(release)], timeout=5)
        self.assertEqual(parent.returncode, 17)
        import time
        deadline = time.monotonic() + 3
        while not release.with_suffix('.ready').exists() and time.monotonic() < deadline:
            time.sleep(.01)
        try:
            self.assertTrue(release.with_suffix('.ready').exists())
            with self.assertRaisesRegex(RuntimeError, 'conflict'):
                self.acquire(reopen=True)
        finally:
            release.touch()
        deadline = time.monotonic() + 3
        while True:
            try:
                lease = self.acquire(reopen=True)
                lease.close()
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.01)

    def test_rejects_marker_tampering_and_unsafe_modes(self):
        with self.acquire() as lease:
            directory = lease.path.parent
        marker = directory / 'marker.json'
        original = marker.read_bytes()
        data = json.loads(original)
        data['transaction_id'] = str(uuid4())
        marker.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'marker'):
            self.acquire(reopen=True)
        marker.write_bytes(original)
        directory.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'directory'):
            self.acquire(reopen=True)
        directory.chmod(0o700)
        with patch.object(storage.os, 'geteuid', return_value=os.geteuid() + 1):
            with self.assertRaisesRegex(ValueError, 'directory'):
                self.acquire(reopen=True)

    def test_rejects_symlink_and_hardlink_contents(self):
        with self.acquire() as lease:
            path = lease.path
        target = self.root / 'other-experiment'
        target.write_bytes(b'preserve')
        alias = path / 'alias'
        alias.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'linked'):
            self.acquire(reopen=True)
        alias.unlink()
        os.link(target, alias)
        with self.assertRaisesRegex(ValueError, 'linked'):
            self.acquire(reopen=True)
        alias.unlink()
        path.rmdir()
        path.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            self.acquire(reopen=True)
        self.assertEqual(target.read_bytes(), b'preserve')

    def test_create_rejects_preexisting_nonempty_or_symlink_directory(self):
        directory = self.root / ('wksim-parameter-state-' + self.identity.replace('-', ''))
        directory.mkdir(mode=0o700)
        (directory / 'unowned').write_text('keep')
        with self.assertRaises(FileExistsError):
            self.acquire()
        self.assertEqual((directory / 'unowned').read_text(), 'keep')
        (directory / 'unowned').unlink()
        directory.rmdir()
        directory.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            self.acquire(reopen=True)


if __name__ == '__main__':
    unittest.main()
