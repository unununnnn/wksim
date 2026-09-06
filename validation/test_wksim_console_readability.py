"""Controlled unit fixtures only; these are not native-render acceptance tests."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from tools import visual_readability as readability


def sha(data):
    return hashlib.sha256(data).hexdigest()


class MeasureTests(unittest.TestCase):
    def test_native_gate_requires_three_consecutive_readable_frames(self):
        good = dict(readable_probe=True)
        bad = dict(readable_probe=False)
        for frames in ([], [good], [good, good], [good, bad, good]):
            self.assertFalse(readability.readability_gate(frames))
        self.assertTrue(readability.readability_gate([good, good, good]))
        self.assertTrue(readability.readability_gate([bad, good, good, good]))
        self.assertTrue(readability.readability_gate([good], minimum=1))

    def test_fixed_regions_and_original_file_unchanged(self):
        # 100x100 gives a fixed 70x67 scene ROI; outside pixels deliberately
        # oppose its brightness so accidentally measuring the whole frame fails.
        with tempfile.TemporaryDirectory() as directory:
            for name, inside, outside, expected_luma, dark, clipped, readable in (
                ('dark', (0, 0, 0), (255, 255, 255), 0, 1, 0, False),
                ('readable', (100, 100, 100), (0, 0, 0), 100, 0, 0, True),
                ('clipped', (255, 255, 255), (0, 0, 0), 255, 0, 1, False),
                ('red', (255, 0, 0), (0, 0, 0), 54.213, 0, 0, True),
            ):
                with self.subTest(region=name):
                    path = Path(directory) / (name + '.png')
                    with Image.new('RGB', (100, 100), outside) as image:
                        image.paste(inside, (15, 25, 85, 92))
                        image.save(path)
                    original = path.read_bytes()
                    result = readability.measure(path)
                    self.assertEqual(result['file'], str(path))
                    self.assertEqual((result['width'], result['height']), (100, 100))
                    self.assertEqual(tuple(result['roi_px']), (15, 25, 85, 92))
                    self.assertAlmostEqual(result['mean_luma'], expected_luma)
                    self.assertEqual(result['dark_fraction'], dark)
                    self.assertEqual(result['clipped_fraction'], clipped)
                    self.assertIs(result['readable_probe'], readable)
                    self.assertEqual(result['sha256'], sha(original))
                    self.assertEqual(path.read_bytes(), original)


class CandidateBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / 'repo'
        self.source = self.repo / 'Simulator/ue55'
        self.stage = self.root / 'stage'
        self.source.mkdir(parents=True)
        self.stage.mkdir()
        self.engine = self.root / 'UnrealEditor.exe'
        self.engine.write_bytes(b'inert unit fixture; never executed')
        self.project = self.stage / 'Fixture.uproject'
        self.project.write_bytes(b'{}')
        self.binary = self.stage / 'Binaries/Win64/Fixture.dll'
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b'inert candidate binary')
        inputs = []
        for relative in ('Source/Fixture.cpp', 'Config/DefaultEngine.ini'):
            data = ('fixture ' + relative).encode()
            for root in (self.source, self.stage):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            inputs.append(dict(path=relative, source_sha256=sha(data),
                               staging_sha256=sha(data)))
        self.deployed = self.source / 'state-build-manifest.json'
        self.deployed.write_text(json.dumps(dict(build_inputs=inputs)), encoding='utf-8')
        self.build = dict(build_exit_code=0, project=str(self.project),
                          binary=str(self.binary), binary_sha256=sha(self.binary.read_bytes()),
                          build_inputs=inputs)
        self.manifest = self.root / 'candidate.json'
        patcher = patch.multiple(readability, REPO=self.repo, ENGINE=self.engine)
        patcher.start()
        self.addCleanup(patcher.stop)

    def candidate(self, build=None):
        self.manifest.write_text(json.dumps(self.build if build is None else build),
                                 encoding='utf-8')
        return readability.candidate_build(self.manifest)

    def test_complete_successful_candidate_and_manifests_unchanged(self):
        deployed_before = self.deployed.read_bytes()
        result = self.candidate()
        self.assertEqual(result, dict(self.build, diagnostic_source_drift=[]))
        self.assertEqual(json.loads(self.manifest.read_text(encoding='utf-8')), self.build)
        self.assertEqual(self.deployed.read_bytes(), deployed_before)

    def test_failed_or_missing_build_status_rejected(self):
        for status in (1, -1, None):
            with self.subTest(status=status):
                build = copy.deepcopy(self.build)
                if status is None:
                    del build['build_exit_code']
                else:
                    build['build_exit_code'] = status
                with self.assertRaisesRegex(ValueError, 'complete deployed build-input set'):
                    self.candidate(build)

    def test_requires_exact_complete_input_set(self):
        original = self.build['build_inputs']
        for name, inputs in (
            ('missing', original[:1]),
            ('empty', []),
            ('duplicate', [original[0], original[0]]),
            ('extra', original + [dict(original[0], path='Extra.cpp')]),
            ('substituted', [original[0], dict(original[1], path='Other.ini')]),
        ):
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, 'complete deployed build-input set'):
                    self.candidate(dict(self.build, build_inputs=inputs))

    def test_input_order_is_not_identity(self):
        result = self.candidate(dict(self.build, build_inputs=self.build['build_inputs'][::-1]))
        self.assertEqual(result['diagnostic_source_drift'], [])

    def test_staged_input_tampering_rejected(self):
        (self.stage / self.build['build_inputs'][0]['path']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'staged input identity mismatch'):
            self.candidate()

    def test_missing_staged_input_rejected(self):
        (self.stage / self.build['build_inputs'][0]['path']).unlink()
        with self.assertRaises(FileNotFoundError):
            self.candidate()

    def test_binary_tampering_rejected(self):
        self.binary.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'DLL identity mismatch'):
            self.candidate()

    def test_missing_binary_rejected(self):
        self.binary.unlink()
        with self.assertRaises(FileNotFoundError):
            self.candidate()

    def test_external_binary_with_matching_hash_rejected(self):
        outside = self.root / 'stage-sibling/Fixture.dll'
        outside.parent.mkdir()
        outside.write_bytes(self.binary.read_bytes())
        with self.assertRaisesRegex(ValueError, 'DLL identity mismatch'):
            self.candidate(dict(self.build, binary=str(outside)))

    def test_escaped_staged_inputs_with_matching_hash_rejected(self):
        outside = self.root / 'stage-sibling/escaped.cpp'
        outside.parent.mkdir()
        outside.write_bytes(b'escaped fixture')
        for relative in ('../stage-sibling/escaped.cpp',
                         '..\\stage-sibling\\escaped.cpp', str(outside)):
            with self.subTest(path=relative):
                item = dict(path=relative, source_sha256=sha(outside.read_bytes()),
                            staging_sha256=sha(outside.read_bytes()))
                # A malformed deployed fixture must not bypass containment.
                self.deployed.write_text(json.dumps(dict(build_inputs=[item])), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'staged input identity mismatch'):
                    self.candidate(dict(self.build, build_inputs=[item]))

    def test_missing_project_or_engine_rejected(self):
        for target in (self.project, self.engine):
            with self.subTest(target=target.name):
                original = target.read_bytes()
                target.unlink()
                try:
                    with self.assertRaisesRegex(FileNotFoundError, 'project or pinned UE'):
                        self.candidate()
                finally:
                    target.write_bytes(original)

    def test_historical_source_drift_reported_without_rejection(self):
        changed, missing = self.build['build_inputs']
        current = b'new current source for historical comparison'
        (self.source / changed['path']).write_bytes(current)
        (self.source / missing['path']).unlink()
        result = self.candidate()
        self.assertEqual(result['diagnostic_source_drift'], [
            dict(path=changed['path'], build_sha256=changed['source_sha256'],
                 current_sha256=sha(current)),
            dict(path=missing['path'], build_sha256=missing['source_sha256'],
                 current_sha256=None),
        ])
        self.assertEqual(result['binary_sha256'], self.build['binary_sha256'])


if __name__ == '__main__':
    unittest.main()
