"""Temporary real Git trees; no FC, ROS, build, or production admission."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ap_clock_candidate as candidate


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'candidate'
        self.source = self.root / 'src'
        self.source.mkdir(parents=True)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        candidate.git(self.source, 'init')
        candidate.git(self.source, 'config', 'user.email', 'test@example.invalid')
        candidate.git(self.source, 'config', 'user.name', 'Test')
        candidate.git(self.source, 'config', 'core.autocrlf', 'false')
        for i in range(8):
            (self.source / f'file{i}').write_bytes(b'original\n')
        candidate.git(self.source, 'add', '.')
        candidate.git(self.source, 'commit', '-m', 'fixture')
        commit = candidate.git(self.source, 'rev-parse', 'HEAD').decode().strip()
        for i, name in enumerate(candidate.PATCHES):
            (self.source / f'file{i}').write_bytes(b'patched\n')
            diff = candidate.git(self.source, 'diff', '--binary', '--', f'file{i}')
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(diff)
        script = self.repo / candidate.BUILD_SCRIPT
        script.parent.mkdir(parents=True)
        script.write_bytes(b'fixture build script\n')
        for name in (candidate.BINARY, 'configure.log', 'build.log'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'fixture artifact\n')
            target.chmod(0o755)
        (self.source / 'untracked').write_bytes(b'extra\n')
        (self.source / 'file7').unlink()
        self.config = dict(stack='arducopter', ap_candidate=candidate.BASELINE_ROOT,
                           dds_workspace='/fixed/dds', nested={'unchanged': [1]})
        self.original = copy.deepcopy(self.config)
        self.baseline = dict(ok=True, reasons=[], candidate_status={'flown': True})
        for name, value in [('REPO', self.repo), ('COMMIT', commit)]:
            patcher = patch.object(candidate, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # Only Linux root policy and environment-dependent product preflight are replaced.
        patcher = patch.object(candidate, 'candidate_root', side_effect=lambda value: self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(candidate, 'preflight', return_value=self.baseline)
        self.preflight = patcher.start()
        self.addCleanup(patcher.stop)

    def sealed(self):
        return candidate.seal(self.root)

    def test_success_and_no_overwrite(self):
        path, checksum = self.sealed()
        updated, admission = candidate.admit(self.config, path, checksum)
        self.assertEqual(self.config, self.original)
        self.preflight.assert_called_once_with(self.original)
        self.assertEqual(updated['ap_candidate'], str(self.root))
        self.assertEqual(updated['dds_workspace'], self.config['dds_workspace'])
        self.assertTrue(admission['experimental'])
        self.assertFalse(admission['production_admitted'])
        self.assertFalse(admission['flown'])
        self.assertTrue(admission['baseline_preflight']['candidate_status']['flown'])
        source = admission['candidate']['source']
        self.assertEqual(len(source['files']), 8)
        self.assertEqual(source['deleted_tracked'], ['file7'])
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.sealed()
        self.assertEqual(path.read_bytes(), before)

    def test_tamper_each_material_input(self):
        path, checksum = self.sealed()
        targets = [self.source / 'file6', self.source / 'untracked',
                   self.root / candidate.BINARY, self.root / 'configure.log',
                   self.root / 'build.log', self.repo / candidate.BUILD_SCRIPT,
                   *(self.repo / p for p in candidate.PATCHES)]
        for target in targets:
            with self.subTest(target=target):
                before = target.read_bytes()
                target.write_bytes(before + b'tampered\n')
                try:
                    with self.assertRaises((ValueError, candidate.subprocess.CalledProcessError)):
                        candidate.admit(self.config, path, checksum)
                finally:
                    target.write_bytes(before)
        self.assertEqual(self.config, self.original)

    def test_added_and_removed_files(self):
        path, checksum = self.sealed()
        for name in ('new-file', 'file7'):
            target = self.source / name
            target.write_bytes(b'new\n')
            with self.assertRaises(ValueError):
                candidate.admit(self.config, path, checksum)
            target.unlink()
        (self.source / 'untracked').unlink()
        with self.assertRaises(ValueError):
            candidate.admit(self.config, path, checksum)

    def test_manifest_hash_schema_and_empty_set(self):
        path, checksum = self.sealed()
        with self.assertRaises(ValueError):
            candidate.admit(self.config, path, '0' * 64)
        original = json.loads(path.read_bytes())
        for transform in (lambda r: r.update(schema_version=True),
                          lambda r: r['source'].update(files={}),
                          lambda r: r['repository_inputs'].clear(),
                          lambda r: r.update(extra='unexpected')):
            record = copy.deepcopy(original)
            transform(record)
            raw = json.dumps(record).encode()
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                candidate.admit(self.config, path, candidate.sha(raw))

    def test_baseline_and_argument_rejection(self):
        config, result = candidate.admit(self.config)
        self.assertIs(config, self.config)
        self.assertEqual(result, self.baseline)
        for args in (('missing', None), (None, '0' * 64)):
            with self.assertRaises(ValueError):
                candidate.admit(self.config, *args)
        self.preflight.return_value = dict(ok=False, reasons=['fixture rejection'])
        with self.assertRaisesRegex(ValueError, 'baseline preflight'):
            candidate.admit(self.config, 'nonexistent', '0' * 64)
        self.assertEqual(self.config, self.original)

    def test_missing_artifacts_commit_and_reverse_check(self):
        (self.root / 'build.log').write_bytes(b'')
        with self.assertRaises(ValueError):
            self.sealed()
        (self.root / 'build.log').write_bytes(b'log')
        with patch.object(candidate, 'COMMIT', '0' * 40):
            with self.assertRaises(ValueError):
                self.sealed()
        (self.source / 'file0').write_bytes(b'original\n')
        with self.assertRaises(candidate.subprocess.CalledProcessError):
            self.sealed()

    @unittest.skipUnless(os.name == 'posix', 'POSIX source symlinks')
    def test_internal_directory_symlink_content_is_checked(self):
        local = self.source / 'local_modules'
        local.mkdir()
        (local / 'module.js').write_bytes(b'module\n')
        link = self.source / 'node_modules'
        link.symlink_to('local_modules', target_is_directory=True)
        path, checksum = self.sealed()
        record = json.loads(path.read_bytes())
        self.assertEqual(record['source']['files']['node_modules']['symlink'], 'local_modules')
        self.assertIn('module.js', record['source']['files']['node_modules']['members'])
        (local / 'module.js').write_bytes(b'changed\n')
        with self.assertRaises(ValueError):
            candidate.admit(self.config, path, checksum)
        link.unlink()
        link.symlink_to(self.base, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            candidate.source_snapshot(self.source)

    def test_submodule_untracked_and_diff(self):
        upstream = self.base / 'upstream'
        upstream.mkdir()
        candidate.git(upstream, 'init')
        candidate.git(upstream, 'config', 'user.email', 'test@example.invalid')
        candidate.git(upstream, 'config', 'user.name', 'Test')
        (upstream / 'nested-source').write_bytes(b'nested\n')
        candidate.git(upstream, 'add', '.')
        candidate.git(upstream, 'commit', '-m', 'nested fixture')
        candidate.git(self.source, '-c', 'protocol.file.allow=always',
                      'submodule', 'add', str(upstream), 'modules/fixture')
        candidate.git(self.source, 'commit', '-m', 'add submodule', '--', '.gitmodules', 'modules/fixture')
        commit = candidate.git(self.source, 'rev-parse', 'HEAD').decode().strip()
        nested = self.source / 'modules/fixture'
        (nested / 'extra').write_bytes(b'untracked nested\n')
        with patch.object(candidate, 'COMMIT', commit):
            path, checksum = self.sealed()
            record = json.loads(path.read_bytes())
            self.assertIn('modules/fixture/extra', record['source']['files'])
            self.assertIn('modules/fixture', record['source']['repositories'])
            (nested / 'extra').write_bytes(b'changed\n')
            with self.assertRaises(ValueError):
                candidate.admit(self.config, path, checksum)
            (nested / 'extra').write_bytes(b'untracked nested\n')
            (nested / 'nested-source').write_bytes(b'dirty\n')
            with self.assertRaises(ValueError):
                candidate.admit(self.config, path, checksum)
            # Removing submodule metadata must not fall back to the parent repository.
            (nested / '.git').unlink()
            with self.assertRaisesRegex(ValueError, 'Uninitialized'):
                candidate.source_snapshot(self.source)


class RootPolicyTests(unittest.TestCase):
    def test_invalid_roots(self):
        for root in ('relative', '/tmp/wksim-ap-clock-stop-test',
                     '/root/wksim-ap-clock-stop-x/../x', candidate.BASELINE_ROOT, None):
            with self.subTest(root=root), self.assertRaises(ValueError):
                candidate.candidate_root(root)


if __name__ == '__main__':
    unittest.main()
