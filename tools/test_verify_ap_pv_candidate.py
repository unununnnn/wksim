"""Real temporary Git/source/artifact checks; no firmware runtime or ROS required."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import verify_ap_pv_candidate as candidate


class VerifyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='wksim-ap-pv-', dir='/root')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.base, self.repo = self.root / 'baseline', self.root / 'repo'
        source = self.base / 'src'
        source.mkdir(parents=True)
        candidate.git(source, 'init')
        candidate.git(source, 'config', 'user.name', 'Fixture')
        candidate.git(source, 'config', 'user.email', 'fixture@example.invalid')
        (source / 'control.cpp').write_text('original\n')
        candidate.git(source, 'add', '.')
        candidate.git(source, 'commit', '-m', 'fixture')
        commit = candidate.git(source, 'rev-parse', 'HEAD').decode().strip()
        baseline = dict(source=candidate.source_snapshot(source, commit=commit))
        raw = json.dumps(baseline).encode()
        (self.base / 'wksim-build.json').write_bytes(raw)
        (self.root / 'baseline-manifest.json').write_bytes(raw)
        shutil.copytree(source, self.root / 'src')
        source = self.root / 'src'
        (source / 'control.cpp').write_text('patched\n')
        patch_raw = candidate.git(source, 'diff', '--binary')
        self.repo.mkdir()
        (self.repo / 'candidate.patch').write_bytes(patch_raw)
        (self.root / 'candidate.patch').write_bytes(patch_raw)
        (self.repo / 'tools').mkdir()
        for path in (self.repo / 'tools/prepare_ap_pv_candidate.py', self.root / 'prepare_ap_pv_candidate.py'):
            path.write_bytes(b'fixture preparer\n')
        prepared = dict(schema_version=1, status='source-only-not-built-not-admitted',
                        candidate_root=str(self.root), baseline_root=str(self.base),
                        baseline_manifest_sha256=candidate.sha(raw), commit=commit,
                        patch_sha256=candidate.sha(patch_raw), prepare_sha256=candidate.sha(b'fixture preparer\n'),
                        source=candidate.source_snapshot(source, commit=commit))
        source_raw = json.dumps(prepared).encode()
        (self.root / 'pv-source.json').write_bytes(source_raw)
        binary = self.root / 'build/sitl/bin/arducopter'
        binary.parent.mkdir(parents=True)
        for path in (binary, self.root / 'configure.log', self.root / 'build.log'):
            path.write_bytes(b'fixture artifact\n')
        binary.chmod(0o755)
        record = dict(status='built-not-admitted', candidate_root=str(self.root), binary=str(binary),
                      baseline_manifest_sha256=candidate.sha(raw), source_manifest_sha256=candidate.sha(source_raw),
                      patch_sha256=candidate.sha(patch_raw),
                      **{key: candidate.sha(b'fixture artifact\n') for key in
                         ('binary_sha256', 'configure_log_sha256', 'build_log_sha256')})
        self.manifest = self.root / 'pv-build.json'
        self.manifest.write_text(json.dumps(record))
        self.checksum = candidate.sha(self.manifest.read_bytes())
        for name, value in dict(BASE=self.base, COMMIT=commit, MANIFEST_SHA=candidate.sha(raw),
                                PATCH=self.repo / 'candidate.patch', REPO=self.repo).items():
            patcher = patch.object(candidate, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_verified_is_not_admission(self):
        result = candidate.verify(self.manifest, self.checksum)
        self.assertEqual(result['status'], 'verified-built-not-admitted')
        self.assertFalse(result['production_admitted'])
        self.assertFalse(result['flown'])

    def test_tampered_material_is_rejected(self):
        for name in ('src/control.cpp', 'baseline/src/control.cpp', 'build/sitl/bin/arducopter',
                     'build.log', 'configure.log', 'candidate.patch', 'pv-source.json',
                     'baseline-manifest.json', 'prepare_ap_pv_candidate.py', 'repo/candidate.patch'):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b'tampered\n')
                    with self.assertRaises(ValueError):
                        candidate.verify(self.manifest, self.checksum)
                finally:
                    path.write_bytes(original)

    def test_added_source_is_rejected(self):
        (self.root / 'src/untracked.cpp').write_text('unexpected\n')
        with self.assertRaisesRegex(ValueError, 'source differs'):
            candidate.verify(self.manifest, self.checksum)

    def test_external_hash_and_manifest_link_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA256 differs'):
            candidate.verify(self.manifest, '0' * 64)
        link = self.root / 'linked.json'
        link.symlink_to(self.manifest)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            candidate.verify(link, self.checksum)
        for raw in (b'[]', b'{"status":"built-not-admitted","status":"other"}'):
            self.manifest.write_bytes(raw)
            with self.assertRaises(ValueError):
                candidate.verify(self.manifest, candidate.sha(raw))


if __name__ == '__main__':
    unittest.main()
