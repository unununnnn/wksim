"""Offline checks for tools/px4_land_candidate.py; synthetic fixture repos, no PX4 build.

Builds tiny real git repositories standing in for the PX4 baseline/candidate and a
toy patch, then exercises the seal/check contract: the candidate LandDetector.cpp
must equal baseline-plus-patch bytes exactly (tampering anywhere else in the file
is rejected), extra source changes, baseline identity drift, missing runtime
artifacts, forbidden/missing dynamic dependencies, root policy and manifest
non-overwrite all fail closed. No SITL/UE/ROS, no real PX4 source or binary.
"""
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import px4_land_candidate as land

BASE_SOURCE = (
    "void LandDetector::Run()\n"
    "{\n"
    "\tfloat stick = 0.0f;\n"
    "\n"
    "\tconst bool at_rest = landDetected && _at_rest;\n"
    "\n"
    "\t// publish at 1 Hz, very first time, or when the result has changed\n"
    "\tif ((hrt_elapsed_time(&_land_detected.timestamp) >= 1_s) ||\n"
    "\t    (_land_detected.landed != landDetected) ||\n"
    "\t    (_land_detected.maybe_landed != maybe_landedDetected)) {\n"
    "\t\tpublish();\n"
    "\t}\n"
    "}\n"
)
PATCHED_SOURCE = BASE_SOURCE.replace(
    "\t// publish at 1 Hz, very first time, or when the result has changed\n"
    "\tif ((hrt_elapsed_time(&_land_detected.timestamp) >= 1_s) ||\n",
    "\t// wksim SITL candidate: re-observe/publish at 5 Hz (200 ms)\n"
    "\tif ((hrt_elapsed_time(&_land_detected.timestamp) >= 200_ms) ||\n")
assert PATCHED_SOURCE != BASE_SOURCE

LDD_CLEAN = ("linux-vdso.so.1 (0x00007ffd)\n"
             "\tlibstdc++.so.6 => /lib/x86_64-linux-gnu/libstdc++.so.6 (0x00007f00)\n")


def git(directory, *args):
    subprocess.run(['git', '-C', str(directory), *args], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def make_world(case):
    """Create baseline repo, repo dir with toy patch, and candidate root."""
    tmp = Path(tempfile.mkdtemp(prefix='wksim-land-test-'))
    case.addCleanup(shutil.rmtree, tmp, True)
    target = Path(land.TARGET)
    baseline = tmp/'baseline'
    (baseline/target.parent).mkdir(parents=True)
    (baseline/target).write_bytes(BASE_SOURCE.encode())
    (baseline/'src/modules/other').mkdir(parents=True)
    (baseline/'src/modules/other/other.cpp').write_bytes(b'int other;\n')
    (baseline/'build/px4_sitl_default/bin').mkdir(parents=True)
    (baseline/'build/px4_sitl_default/bin/px4').write_bytes(b'baseline-elf\n')
    git(baseline, 'init', '-q', '.')
    git(baseline, 'config', 'core.autocrlf', 'false')
    git(baseline, 'add', '-A')
    git(baseline, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'base')
    head = subprocess.run(['git', '-C', str(baseline), 'rev-parse', 'HEAD'], check=True,
                          stdout=subprocess.PIPE).stdout.decode().strip()

    # Toy patch produced by real git diff, never hand-counted hunks.
    (baseline/target).write_bytes(PATCHED_SOURCE.encode())
    patch = subprocess.run(['git', '-C', str(baseline), 'diff'], check=True,
                           stdout=subprocess.PIPE).stdout
    (baseline/target).write_bytes(BASE_SOURCE.encode())

    repo = tmp/'repo'
    (repo/'patches/px4').mkdir(parents=True)
    (repo/'patches/px4/0004-land-observation-cadence.patch').write_bytes(patch)
    (repo/'tools').mkdir()
    (repo/'tools/build-px4-land-cadence.sh').write_bytes(b'#!/bin/sh\n')
    (repo/'tools/px4_land_candidate.py').write_bytes(b'# seal\n')

    root = tmp/'wksim-px4-land-test01'
    shutil.copytree(baseline, root/'src')
    (root/'src/build/px4_sitl_default/etc').mkdir(parents=True)
    (root/'src/build/px4_sitl_default/bin/px4').write_bytes(b'candidate-elf\n')
    (root/'src/build/px4_sitl_default/etc/rcS').write_bytes(b'#!rc\n')
    (root/'build.log').write_bytes(b'build ok\n')
    (root/'dependency-check.log').write_bytes(LDD_CLEAN.encode())
    world = dict(tmp=tmp, baseline=baseline, repo=repo, root=root, head=head,
                 target=target, patch=patch)
    seal_candidate(world)
    return world


def seal_candidate(world):
    git(world['root']/'src', 'apply',
        str(world['repo']/'patches/px4/0004-land-observation-cadence.patch'))


def patched(world, **overrides):
    values = dict(REPO=world['repo'], BASELINE=world['baseline'],
                  COMMIT=world['head'], ROOT_PARENT=world['tmp'],
                  _linked_libraries=lambda binary: LDD_CLEAN)
    values.update(overrides)
    return mock.patch.multiple(land, **values)


@unittest.skipUnless(shutil.which('git'), 'git required for fixture repositories')
class LandCandidateSealTest(unittest.TestCase):
    def test_seal_and_check_roundtrip(self):
        world = make_world(self)
        with patched(world):
            path, checksum = land.seal(world['root'])
            self.assertEqual(path.name, 'land-build.json')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), checksum)
            value = land.check(path, checksum)
        self.assertEqual(value['schema'], 'px4-land-cadence-v1')
        self.assertEqual(value['expected_sources'],
                         {land.TARGET: hashlib.sha256(PATCHED_SOURCE.encode()).hexdigest()})
        self.assertIn('forbidden_pattern', value['dependency_policy'])
        self.assertTrue(value['artifacts'])
        self.assertTrue(any(name.endswith('bin/px4') for name in value['artifacts']))

    def test_tampered_target_elsewhere_rejected(self):
        world = make_world(self)
        with (world['root']/'src'/world['target']).open('ab') as stream:
            stream.write(b'\n// tampered far from the hunk\n')
        with patched(world):
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                land.snapshot(world['root'])

    def test_unpatched_target_rejected(self):
        world = make_world(self)
        (world['root']/'src'/world['target']).write_bytes(BASE_SOURCE.encode())
        with patched(world):
            with self.assertRaisesRegex(ValueError, 'Unexpected native source changes'):
                land.snapshot(world['root'])

    def test_extra_source_change_rejected(self):
        world = make_world(self)
        with (world['root']/'src'/'src/modules/other/other.cpp').open('ab') as stream:
            stream.write(b'int extra;\n')
        with patched(world):
            with self.assertRaisesRegex(ValueError, 'Unexpected native source changes'):
                land.snapshot(world['root'])

    def test_baseline_commit_mismatch_rejected(self):
        world = make_world(self)
        with patched(world, COMMIT='0' * 40):
            with self.assertRaisesRegex(ValueError, 'Unexpected source commit'):
                land.snapshot(world['root'])

    def test_forbidden_dependency_rejected(self):
        world = make_world(self)
        linked = LDD_CLEAN + '\tlibgazebo_msgs.so => /opt/gz/libgazebo_msgs.so (0x00007f00)\n'
        with patched(world, _linked_libraries=lambda binary: linked):
            with self.assertRaisesRegex(ValueError, 'Missing or forbidden'):
                land.snapshot(world['root'])

    def test_missing_dependency_rejected(self):
        world = make_world(self)
        with patched(world, _linked_libraries=lambda binary: '\tlibfoo.so => not found\n'):
            with self.assertRaisesRegex(ValueError, 'Missing or forbidden'):
                land.snapshot(world['root'])

    def test_manifest_not_overwritable(self):
        world = make_world(self)
        with patched(world):
            land.seal(world['root'])
            with self.assertRaises(FileExistsError):
                land.seal(world['root'])

    def test_manifest_checksum_mismatch_rejected(self):
        world = make_world(self)
        with patched(world):
            path, _ = land.seal(world['root'])
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                land.check(path, '0' * 64)

    def test_missing_artifact_detected(self):
        world = make_world(self)
        with patched(world):
            path, checksum = land.seal(world['root'])
            (world['root']/'src/build/px4_sitl_default/etc/rcS').unlink()
            with self.assertRaisesRegex(ValueError, 'candidate changed'):
                land.check(path, checksum)

    def test_root_policy_rejected(self):
        world = make_world(self)
        with patched(world):
            with self.assertRaisesRegex(ValueError, 'private PX4 land candidate root'):
                land.snapshot(world['tmp']/'px4-land-test01')
            with self.assertRaisesRegex(ValueError, 'private PX4 land candidate root'):
                land.snapshot(world['root']/'src')

    def test_manifest_name_versioning_enforced(self):
        world = make_world(self)
        with patched(world):
            with self.assertRaisesRegex(ValueError, 'versioned'):
                land.seal(world['root'], 'build.json')
            path, _ = land.seal(world['root'], 'land-build-v2.json')
            self.assertEqual(path.name, 'land-build-v2.json')


if __name__ == '__main__':
    unittest.main()
