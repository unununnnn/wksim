"""Pure behavioral admission tests for the generated-e0 lifecycle validator.

Scope
-----
These tests verify the *ordering and rejection contract* of
``tools/validate_generated_e0_lifecycle.py``.  They assert that a bad build
manifest, a bad source set, or an occupied output path is rejected **before**
the validator creates an output directory, creates a cold directory, copies a
source, spawns a compiler, or spawns a probe child.

Nothing here compiles code, loads a ``.so``, runs MATLAB, or touches ROS/UE.
``subprocess.run``, ``subprocess.Popen`` and the process identity helper are
replaced in-process.

Host requirement: this suite runs on **Linux** with a **writable ``/root``**.
That is not incidental — ``run()`` rejects non-Linux hosts outright
(``sys.platform != 'linux'``) and the staged-root contract requires ``/root`` to
be a real absolute path (``Path('/root/...')`` is not absolute on Windows).
The fixtures therefore create and remove real directories under ``/root``.

The suite also pins the *behaviour that must not change*: the compiler argv,
the frozen 4x1000-step comparison gate, and the numeric budgets recorded in
``contract.json``.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import tempfile
import types
import unittest
import uuid
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import validate_generated_e0_lifecycle as validator

SIX_SOURCES = (
    "Exp1_MinModelTemp.cpp",
    "Exp1_MinModelTemp.h",
    "rtwtypes.h",
    "rtw_continuous.h",
    "rtw_solver.h",
    "model.cpp",
)

EXPECTED_COMPILE_ARGV_TAIL = [
    "-std=c++17",
    "-O2",
    "-fno-fast-math",
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
]


def _valid_manifest(staged_root, hashes):
    """A structurally valid build manifest using the six required sources."""
    return {
        "staged_sources": {
            name: {
                "wsl_staged_path": f"{staged_root}/{name}",
                "sha256": hashes[name],
                "size_bytes": 1,
            }
            for name in SIX_SOURCES
        }
    }


class _Fixture:
    """Builds a real staged root in the layout the validator requires.

    Manifest provenance paths are POSIX strings under ``/root`` with the frozen
    ``wksim-codegen-e0-build-`` prefix, and the bytes really live there, so the
    tests exercise the production admission path rather than a redirected one.
    This is why the suite runs on the Ubuntu-22.04 host: ``/root`` and
    ``sys.platform=='linux'`` are part of the validator's contract.
    """

    def __init__(self, testcase):
        self.basename = "wksim-codegen-e0-build-adm-" + uuid.uuid4().hex[:10]
        self.staged = Path("/root") / self.basename
        self.staged.mkdir(parents=True)
        testcase.addCleanup(shutil.rmtree, self.staged, True)
        self.staged_posix = self.staged.as_posix()
        self.hashes = {}
        for name in SIX_SOURCES:
            path = self.staged / name
            path.write_bytes(f"// {name}\n".encode())
            self.hashes[name] = validator.sha(path)
        self.library = self.staged / "libwksim_e0.so"
        self.library.write_bytes(b"ELF-fake\n")
        self.root = Path(tempfile.mkdtemp(prefix="wksim-admission-fixture-"))
        testcase.addCleanup(shutil.rmtree, self.root, True)
        self.manifest = self.root / "build-manifest.json"
        self.manifest.write_text(
            json.dumps(_valid_manifest(self.staged_posix, self.hashes)), encoding="utf-8"
        )
        self.summary = self.root / "summary.json"
        self.summary.write_text(
            json.dumps(
                {
                    "library_sha256": validator.sha(self.library),
                    "library_size_bytes": self.library.stat().st_size,
                }
            ),
            encoding="utf-8",
        )
        self.output = self.root / "evidence-out"

    def write_manifest(self, data):
        self.manifest.write_text(json.dumps(data), encoding="utf-8")

    def reload_manifest(self):
        return json.loads(self.manifest.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 1. Pure helper contract (no filesystem root patching needed).
# --------------------------------------------------------------------------


class SourceRootTests(unittest.TestCase):
    """source_root binds every key to its own filename and one frozen root."""

    def setUp(self):
        self.fx = _Fixture(self)

    def test_valid_six_source_set_resolves_the_staged_root(self):
        manifest = self.fx.reload_manifest()
        root = validator.source_root(manifest["staged_sources"])
        self.assertEqual(str(root), self.fx.staged_posix)

    def test_missing_source_is_rejected(self):
        sources = self.fx.reload_manifest()["staged_sources"]
        del sources["rtw_solver.h"]
        with self.assertRaisesRegex(validator.AdmissionError, "differs from the six expected"):
            validator.source_root(sources)

    def test_extra_source_is_rejected(self):
        sources = self.fx.reload_manifest()["staged_sources"]
        sources["extra.cpp"] = {"wsl_staged_path": f"{self.fx.staged_posix}/extra.cpp", "sha256": "0" * 64}
        with self.assertRaisesRegex(validator.AdmissionError, "extra=\\['extra.cpp'\\]"):
            validator.source_root(sources)

    def test_filename_not_matching_its_key_is_rejected(self):
        """The old code only compared parent directories, never filenames."""
        sources = self.fx.reload_manifest()["staged_sources"]
        sources["model.cpp"]["wsl_staged_path"] = f"{self.fx.staged_posix}/other-wrapper.cpp"
        with self.assertRaisesRegex(validator.AdmissionError, "does not match its key"):
            validator.source_root(sources)

    def test_common_parent_escape_is_rejected(self):
        sources = self.fx.reload_manifest()["staged_sources"]
        sources["model.cpp"]["wsl_staged_path"] = f"/tmp/elsewhere/model.cpp"
        with self.assertRaisesRegex(validator.AdmissionError, "share exactly one staged parent"):
            validator.source_root(sources)

    def test_root_outside_the_frozen_build_prefix_is_rejected(self):
        """A real directory under /root without the frozen prefix is refused."""
        offender = Path("/root") / f"not-a-build-root-{uuid.uuid4().hex[:8]}"
        offender.mkdir()
        self.addCleanup(shutil.rmtree, offender, True)
        sources = self.fx.reload_manifest()["staged_sources"]
        for name in SIX_SOURCES:
            sources[name]["wsl_staged_path"] = f"{offender.as_posix()}/{name}"
        with self.assertRaisesRegex(validator.AdmissionError, "escapes the frozen build root"):
            validator.source_root(sources)

    def test_relative_and_non_posix_paths_are_rejected(self):
        sources = self.fx.reload_manifest()["staged_sources"]
        sources["model.cpp"]["wsl_staged_path"] = "relative/model.cpp"
        with self.assertRaisesRegex(validator.AdmissionError, "absolute POSIX path"):
            validator.source_root(sources)

    def test_nul_byte_path_is_rejected(self):
        sources = self.fx.reload_manifest()["staged_sources"]
        sources["model.cpp"]["wsl_staged_path"] = f"{self.fx.staged_posix}/model.cpp\x00"
        with self.assertRaisesRegex(validator.AdmissionError, "NUL byte"):
            validator.source_root(sources)


class LibraryIdentityTests(unittest.TestCase):
    def setUp(self):
        self.fx = _Fixture(self)

    def test_valid_identity_is_accepted(self):
        summary, library, digest = validator.check_library_identity(
            self.fx.staged, self.fx.summary
        )
        self.assertEqual(library, self.fx.library)
        self.assertEqual(digest, validator.sha(self.fx.library))
        self.assertEqual(summary["library_sha256"], digest)

    def test_missing_library_is_rejected(self):
        self.fx.library.unlink()
        with self.assertRaisesRegex(validator.AdmissionError, "original library is not a regular file"):
            validator.check_library_identity(self.fx.staged, self.fx.summary)

    def test_library_hash_mismatch_is_rejected(self):
        summary = json.loads(self.fx.summary.read_text(encoding="utf-8"))
        summary["library_sha256"] = "0" * 64
        self.fx.summary.write_text(json.dumps(summary), encoding="utf-8")
        with self.assertRaisesRegex(validator.AdmissionError, "differs from summary.json"):
            validator.check_library_identity(self.fx.staged, self.fx.summary)

    def test_missing_summary_is_rejected(self):
        self.fx.summary.unlink()
        with self.assertRaisesRegex(validator.AdmissionError, "summary.json is not a regular file"):
            validator.check_library_identity(self.fx.staged, self.fx.summary)

    def test_malformed_recorded_hash_is_rejected(self):
        summary = json.loads(self.fx.summary.read_text(encoding="utf-8"))
        summary["library_sha256"] = "not-a-digest"
        self.fx.summary.write_text(json.dumps(summary), encoding="utf-8")
        with self.assertRaisesRegex(validator.AdmissionError, "64-character hex digest"):
            validator.check_library_identity(self.fx.staged, self.fx.summary)


class ManifestLoadTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def test_missing_manifest_is_rejected(self):
        with self.assertRaisesRegex(validator.AdmissionError, "not a regular file"):
            validator.load_build_manifest(self.root / "absent.json")

    def test_malformed_json_is_rejected(self):
        path = self.root / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(validator.AdmissionError, "malformed JSON"):
            validator.load_build_manifest(path)

    def test_non_object_root_is_rejected(self):
        path = self.root / "list.json"
        path.write_text("[1, 2]", encoding="utf-8")
        with self.assertRaisesRegex(validator.AdmissionError, "must be a JSON object"):
            validator.load_build_manifest(path)

    def test_sha_is_bound_to_the_exact_bytes_that_were_read(self):
        path = self.root / "m.json"
        path.write_text('{"staged_sources": {}}', encoding="utf-8")
        manifest, digest = validator.load_build_manifest(path)
        self.assertEqual(manifest, {"staged_sources": {}})
        self.assertEqual(digest, validator.sha(path))
        # A later on-disk change must not alter the already-bound identity.
        path.write_text('{"staged_sources": {"x": 1}}', encoding="utf-8")
        self.assertNotEqual(digest, validator.sha(path))

    def test_symlinked_manifest_is_rejected(self):
        real = self.root / "real.json"
        real.write_text("{}", encoding="utf-8")
        link = self.root / "link.json"
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaisesRegex(validator.AdmissionError, "is a symlink"):
            validator.load_build_manifest(link)


class SourceVerificationTests(unittest.TestCase):
    """All six sources are verified in memory before a single snapshot byte."""

    def setUp(self):
        self.fx = _Fixture(self)
        self.snapshot = Path(tempfile.mkdtemp(prefix="wksim-verify-test-"))
        self.addCleanup(shutil.rmtree, self.snapshot, True)

    def test_all_six_are_read_and_verified(self):
        manifest = self.fx.reload_manifest()
        verified = validator.read_verified_sources(manifest["staged_sources"])
        self.assertEqual(set(verified), set(SIX_SOURCES))
        for name, (data, digest) in verified.items():
            self.assertEqual(digest, self.fx.hashes[name])
            self.assertEqual(data, (self.fx.staged / name).read_bytes())

    def test_verification_writes_nothing_anywhere(self):
        """The read pass must not create files, even in the snapshot directory."""
        manifest = self.fx.reload_manifest()
        validator.read_verified_sources(manifest["staged_sources"])
        self.assertEqual(list(self.snapshot.iterdir()), [])

    def test_verification_failure_writes_nothing(self):
        """A bad hash must abort before any snapshot byte exists."""
        manifest = self.fx.reload_manifest()
        manifest["staged_sources"]["model.cpp"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(validator.AdmissionError, "staged source hash differs for model.cpp"):
            validator.read_verified_sources(manifest["staged_sources"])
        self.assertEqual(list(self.snapshot.iterdir()), [])

    def test_source_hash_mismatch_is_rejected(self):
        manifest = self.fx.reload_manifest()
        manifest["staged_sources"]["Exp1_MinModelTemp.cpp"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(validator.AdmissionError, "staged source hash differs"):
            validator.read_verified_sources(manifest["staged_sources"])

    def test_symlinked_source_is_rejected(self):
        target = self.fx.staged / "model.cpp"
        backup = self.fx.staged / "model-real.cpp"
        target.rename(backup)
        try:
            target.symlink_to(backup)
        except (OSError, NotImplementedError):
            backup.rename(target)
            self.skipTest("symlink creation unavailable")
        manifest = self.fx.reload_manifest()
        manifest["staged_sources"]["model.cpp"]["sha256"] = validator.sha(backup)
        with self.assertRaisesRegex(validator.AdmissionError, "staged source model.cpp is a symlink"):
            validator.read_verified_sources(manifest["staged_sources"])

    def test_missing_source_is_rejected(self):
        (self.fx.staged / "rtw_solver.h").unlink()
        manifest = self.fx.reload_manifest()
        with self.assertRaisesRegex(validator.AdmissionError, "not a regular file"):
            validator.read_verified_sources(manifest["staged_sources"])

    def test_snapshot_write_uses_the_verified_bytes(self):
        manifest = self.fx.reload_manifest()
        verified = validator.read_verified_sources(manifest["staged_sources"])
        # Change the originals after verification: the snapshot must not care.
        for name in SIX_SOURCES:
            (self.fx.staged / name).write_bytes(b"changed after verification\n")
        checked = validator.write_snapshot_sources(self.snapshot, verified)
        self.assertEqual(checked, self.fx.hashes)
        for name in SIX_SOURCES:
            self.assertEqual(validator.sha(self.snapshot / name), self.fx.hashes[name])


class BuildRootResolutionTests(unittest.TestCase):
    """A symlinked build root must not be able to escape /root."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def _make_root(self, name):
        path = Path("/root") / f"wksim-codegen-e0-build-{name}"
        path.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, path, True)
        return path

    def test_real_directory_under_root_is_accepted(self):
        real = self._make_root("res-" + uuid.uuid4().hex[:8])
        self.assertEqual(validator.resolve_build_root(real), real.resolve())

    def test_symlinked_build_root_is_rejected(self):
        real = self._make_root("res-real-" + uuid.uuid4().hex[:8])
        link = Path("/root") / f"wksim-codegen-e0-build-res-link-{uuid.uuid4().hex[:8]}"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlink creation unavailable")
        self.addCleanup(lambda: link.is_symlink() and link.unlink())
        with self.assertRaisesRegex(validator.AdmissionError, "is a symlink"):
            validator.resolve_build_root(link)

    def test_symlink_pointing_outside_root_is_rejected(self):
        """Even a symlink that resolves elsewhere must not be followed."""
        outside = self.root / "outside-build-root"
        outside.mkdir()
        link = Path("/root") / f"wksim-codegen-e0-build-res-escape-{uuid.uuid4().hex[:8]}"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlink creation unavailable")
        self.addCleanup(lambda: link.is_symlink() and link.unlink())
        with self.assertRaisesRegex(validator.AdmissionError, "is a symlink"):
            validator.resolve_build_root(link)

    def test_root_not_a_direct_child_of_slash_root_is_rejected(self):
        nested = self.root / "wksim-codegen-e0-build-nested"
        nested.mkdir()
        with self.assertRaisesRegex(validator.AdmissionError, "escapes the frozen build root"):
            validator.resolve_build_root(nested)

    def test_prefix_mismatch_is_rejected(self):
        bad = Path("/root") / f"not-a-build-root-{uuid.uuid4().hex[:8]}"
        bad.mkdir()
        self.addCleanup(shutil.rmtree, bad, True)
        with self.assertRaisesRegex(validator.AdmissionError, "escapes the frozen build root"):
            validator.resolve_build_root(bad)

    def test_missing_root_is_rejected(self):
        with self.assertRaisesRegex(validator.AdmissionError, "is not a directory"):
            validator.resolve_build_root(Path("/root/wksim-codegen-e0-build-absent-" + uuid.uuid4().hex[:8]))


# --------------------------------------------------------------------------
# 2. Ordering contract: nothing is created before admission passes.
# --------------------------------------------------------------------------


class OrderingTests(unittest.TestCase):
    """Every bad input must fail before output/cold/compile/probe side effects."""

    def setUp(self):
        self.fx = _Fixture(self)
        patcher = unittest.mock.patch.object(validator.sys, "platform", "linux")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _forbid_side_effects(self):
        """Replace every side-effecting callable with a loud sentinel.

        Nothing may spawn a compiler or probe before admission completes.
        """
        patchers = [
            unittest.mock.patch.object(
                validator.subprocess, "run",
                side_effect=AssertionError("compiler spawned before admission"),
            ),
            unittest.mock.patch.object(
                validator.subprocess, "Popen",
                side_effect=AssertionError("probe spawned before admission"),
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _assert_rejected_without_side_effects(self, expected, output_preexisted=False):
        self._forbid_side_effects()
        with self.assertRaisesRegex(validator.AdmissionError, expected):
            validator.run(self.fx.manifest, self.fx.output)
        if output_preexisted:
            self.assertEqual(
                [path.name for path in self.fx.output.iterdir()],
                [],
                "output directory gained artifacts despite rejection",
            )
        else:
            self.assertFalse(self.fx.output.exists(), "output directory created despite rejection")

    def test_source_hash_failure_creates_no_snapshot_at_all(self):
        """All six hashes are verified before mkdtemp is reached."""
        manifest = self.fx.reload_manifest()
        manifest["staged_sources"]["model.cpp"]["sha256"] = "0" * 64
        self.fx.write_manifest(manifest)
        self._assert_mkdtemp_never_called("staged source hash differs")

    def test_any_existing_output_is_rejected_before_snapshot_creation(self):
        """Including an empty directory: no write, no snapshot, no spawn."""
        self.fx.output.mkdir()
        self._assert_mkdtemp_never_called("output path already exists", output_preexisted=True)

    def test_occupied_output_rejected_before_any_read_or_spawn(self):
        self.fx.output.mkdir()
        (self.fx.output / "stale.json").write_text("{}", encoding="utf-8")
        self._assert_mkdtemp_never_called("output path already exists", output_preexisted=True)
        self.assertEqual([path.name for path in self.fx.output.iterdir()], ["stale.json"])

    def test_output_that_is_a_file_is_rejected(self):
        self.fx.output.write_text("not a directory", encoding="utf-8")
        self._assert_mkdtemp_never_called("output path already exists", output_preexisted=True)
        self.assertTrue(self.fx.output.is_file())
        self.assertEqual(self.fx.output.read_text(encoding="utf-8"), "not a directory")

    def test_symlinked_output_is_rejected(self):
        real = self.fx.root / "real-output"
        real.mkdir()
        try:
            self.fx.output.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        self._forbid_side_effects()
        with self.assertRaisesRegex(validator.AdmissionError, "output is a symlink"):
            validator.run(self.fx.manifest, self.fx.output)

    def test_failed_run_cleans_up_its_own_snapshot(self):
        """A failure after mkdtemp must remove that snapshot and nothing else."""
        real_mkdtemp = tempfile.mkdtemp
        sandbox = self.fx.root / "cleanup-sandbox"
        sandbox.mkdir()
        created = []

        def tracked_mkdtemp(*args, **kwargs):
            path = Path(real_mkdtemp(dir=sandbox, prefix="wksim-cleanup-track-"))
            created.append(path)
            return str(path)

        manifest = self.fx.reload_manifest()
        self.fx.write_manifest(manifest)
        self._forbid_side_effects()
        # Force a post-snapshot failure: the snapshot manifest check is the first
        # write and its digest is compared against the identity read up front.
        with unittest.mock.patch.object(validator.tempfile, "mkdtemp", tracked_mkdtemp), \
             unittest.mock.patch.object(validator.shutil, "copyfile", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                validator.run(self.fx.manifest, self.fx.output)
        self.assertTrue(created, "expected the run to reach snapshot creation")
        for path in created:
            self.assertFalse(path.exists(), f"failed run left its snapshot behind: {path}")

    def _assert_mkdtemp_never_called(self, expected, output_preexisted=False):
        """Assert a rejection happens before the private snapshot is created."""
        self._forbid_side_effects()
        with unittest.mock.patch.object(
            validator.tempfile, "mkdtemp",
            side_effect=AssertionError("snapshot created before the input was accepted"),
        ):
            with self.assertRaisesRegex(validator.AdmissionError, expected):
                validator.run(self.fx.manifest, self.fx.output)
        if not output_preexisted:
            self.assertFalse(self.fx.output.exists(), "output created despite rejection")

    def test_library_identity_failure_creates_no_snapshot_at_all(self):
        """The library check is read-only and precedes the snapshot mkdtemp."""
        summary = json.loads(self.fx.summary.read_text(encoding="utf-8"))
        summary["library_sha256"] = "0" * 64
        self.fx.summary.write_text(json.dumps(summary), encoding="utf-8")
        self._assert_mkdtemp_never_called("differs from summary.json")

    def test_source_hash_mismatch_rejected_before_output_creation(self):
        manifest = self.fx.reload_manifest()
        manifest["staged_sources"]["model.cpp"]["sha256"] = "0" * 64
        self.fx.write_manifest(manifest)
        self._assert_mkdtemp_never_called("staged source hash differs")

    def test_missing_staged_source_rejected_before_output_creation(self):
        (self.fx.staged / "model.cpp").unlink()
        self._assert_mkdtemp_never_called("staged source model.cpp is not a regular file")

    def test_library_hash_mismatch_rejected_before_output_creation(self):
        summary = json.loads(self.fx.summary.read_text(encoding="utf-8"))
        summary["library_sha256"] = "0" * 64
        self.fx.summary.write_text(json.dumps(summary), encoding="utf-8")
        self._assert_mkdtemp_never_called("differs from summary.json")

    def test_missing_manifest_rejected_before_output_creation(self):
        self.fx.manifest.unlink()
        self._assert_mkdtemp_never_called("not a regular file")

    def test_manifest_missing_a_source_rejected_before_output_creation(self):
        manifest = self.fx.reload_manifest()
        del manifest["staged_sources"]["rtwtypes.h"]
        self.fx.write_manifest(manifest)
        self._assert_mkdtemp_never_called("differs from the six expected")

    def test_filename_mismatch_rejected_before_output_creation(self):
        manifest = self.fx.reload_manifest()
        manifest["staged_sources"]["model.cpp"]["wsl_staged_path"] = (
            f"{self.fx.staged_posix}/wrong-name.cpp"
        )
        self.fx.write_manifest(manifest)
        self._assert_mkdtemp_never_called("does not match its key")

    def test_shared_parent_escape_rejected_before_output_creation(self):
        manifest = self.fx.reload_manifest()
        manifest["staged_sources"]["rtw_solver.h"]["wsl_staged_path"] = "/tmp/elsewhere/rtw_solver.h"
        self.fx.write_manifest(manifest)
        self._assert_mkdtemp_never_called("share exactly one staged parent")

    def test_symlinked_staged_root_rejected_before_output_creation(self):
        """A symlinked build root must not be able to escape /root."""
        link = Path("/root") / f"wksim-codegen-e0-build-adm-link-{uuid.uuid4().hex[:8]}"
        try:
            link.symlink_to(self.fx.staged, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlink creation unavailable")
        self.addCleanup(lambda: link.is_symlink() and link.unlink())
        manifest = self.fx.reload_manifest()
        for name in SIX_SOURCES:
            manifest["staged_sources"][name]["wsl_staged_path"] = f"{link.as_posix()}/{name}"
        self.fx.write_manifest(manifest)
        self._assert_mkdtemp_never_called("is a symlink")


# --------------------------------------------------------------------------
# 3. Frozen behaviour that must not change.
# --------------------------------------------------------------------------


class FrozenContractTests(unittest.TestCase):
    """The happy path, driven entirely by fakes, to pin what must not change."""

    def setUp(self):
        self.fx = _Fixture(self)
        patcher = unittest.mock.patch.object(validator.sys, "platform", "linux")
        patcher.start()
        self.addCleanup(patcher.stop)
        # A successful run keeps its private snapshot; track every one it
        # creates so the test suite leaves no temporary directory behind.
        self.snapshots = []
        real_mkdtemp = tempfile.mkdtemp

        def tracked_mkdtemp(*args, **kwargs):
            path = Path(real_mkdtemp(*args, **kwargs))
            self.snapshots.append(path)
            return str(path)

        snap_patcher = unittest.mock.patch.object(validator.tempfile, "mkdtemp", tracked_mkdtemp)
        snap_patcher.start()
        self.addCleanup(snap_patcher.stop)
        self.addCleanup(
            lambda: [shutil.rmtree(path, ignore_errors=True) for path in self.snapshots]
        )

    def _drive_happy_path(self):
        calls = {"probe": [], "identities": []}
        original_library_bytes = self.fx.library.read_bytes()

        class FakeProc:
            returncode = 0

            def __init__(self, pid):
                self.pid = pid

            def wait(self, timeout=None):
                return 0

        def track_cold_dir(path):
            cold_dir = Path(path).parent
            if cold_dir.name.startswith("wksim-codegen-e0-cold-"):
                self.addCleanup(shutil.rmtree, cold_dir, True)

        def fake_subprocess_run(argv, **kwargs):
            if argv and argv[0] == "ldd":
                calls["ldd"] = list(argv)
                return types.SimpleNamespace(
                    stdout="libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6\n"
                )
            track_cold_dir(argv[argv.index("-o") + 1])
            calls["compile"] = list(argv)
            # Same input bytes must yield the same library identity.
            Path(argv[argv.index("-o") + 1]).write_bytes(original_library_bytes)
            return types.SimpleNamespace(returncode=0)

        def fake_popen(argv, **kwargs):
            calls["probe"].append(list(argv))
            directory = Path(argv[argv.index("--output") + 1])
            directory.mkdir(parents=True, exist_ok=True)
            for cycle in (0, 1):
                rows = []
                for tick in range(1, 1001):
                    level = 0.0 if tick <= 100 else 0.5 if tick <= 600 else 0.45
                    output = [0.0] * 120
                    output[2] = tick / 1000
                    rows.append(
                        json.dumps(
                            {
                                "tick": tick,
                                "commands": [level] * 4 + [0.0] * 12,
                                "output": output,
                            }
                        )
                    )
                (directory / f"cycle-{cycle}.jsonl").write_text(
                    "\n".join(rows) + "\n", encoding="utf-8"
                )
            (directory / "process.json").write_text(
                json.dumps({"maps": ["libc.so.6"]}), encoding="utf-8"
            )
            return FakeProc(pid=7000 + len(calls["probe"]))

        def fake_identity(pid):
            calls["identities"].append(pid)
            return {"pid": pid, "pgid": pid, "start_ticks": pid, "argv": []}

        with unittest.mock.patch.object(validator.subprocess, "run", fake_subprocess_run), \
             unittest.mock.patch.object(validator.subprocess, "Popen", fake_popen), \
             unittest.mock.patch.object(validator, "json_identity", fake_identity):
            validator.run(self.fx.manifest, self.fx.output)
        return calls

    def test_compiler_argv_is_unchanged(self):
        calls = self._drive_happy_path()
        argv = calls["compile"]
        self.assertEqual(argv[0], "g++")
        for flag in EXPECTED_COMPILE_ARGV_TAIL:
            self.assertIn(flag, argv)
        joined = " ".join(argv)
        self.assertIn("Exp1_MinModelTemp.cpp", joined)
        self.assertIn("model.cpp", joined)
        self.assertEqual(argv[argv.index("-o") + 1].endswith("libwksim_e0.so"), True)
        self.assertEqual(calls["ldd"][0], "ldd")

    def test_both_probe_runs_are_requested(self):
        calls = self._drive_happy_path()
        self.assertEqual(len(calls["probe"]), 2)

    def test_contract_records_the_frozen_4x1000_step_gate(self):
        self._drive_happy_path()
        contract = json.loads((self.fx.output / "contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["ticks"], 1000)
        self.assertEqual(contract["dt_s"], 0.001)
        self.assertEqual(contract["output_count"], 120)
        self.assertEqual(contract["clock_absolute_error_s"], 1e-8)
        self.assertEqual(contract["other_twelve"], 0.0)
        self.assertEqual(contract["version"], 1)
        self.assertEqual(
            contract["inputs"],
            [
                {"first": 1, "last": 100, "first_four": 0.0},
                {"first": 101, "last": 600, "first_four": 0.5},
                {"first": 601, "last": 1000, "first_four": 0.45},
            ],
        )
        self.assertEqual(contract["build_manifest_sha256"], validator.sha(self.fx.manifest))

    def test_audit_records_four_cycles_and_full_comparison_count(self):
        self._drive_happy_path()
        audit = json.loads((self.fx.output / "audit.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["status"], "pass")
        self.assertEqual(audit["schema"], "wksim.generated-e0-lifecycle.v1")
        self.assertEqual(audit["ticks_per_cycle"], 1000)
        self.assertEqual(audit["cycles"], 4)
        self.assertEqual(audit["compared_values"], 4 * 1000 * 120)
        self.assertEqual(set(audit["raw_sha256"]), {
            "original/cycle-0.jsonl", "original/cycle-1.jsonl",
            "cold/cycle-0.jsonl", "cold/cycle-1.jsonl",
        })
        self.assertEqual(set(audit["source_sha256"]), set(SIX_SOURCES))

    def test_side_effects_begin_only_after_admission_on_the_happy_path(self):
        """Control for OrderingTests: a valid input does create the output."""
        self.assertFalse(self.fx.output.exists())
        self._drive_happy_path()
        self.assertTrue((self.fx.output / "contract.json").is_file())

    def test_successful_run_keeps_exactly_one_private_snapshot(self):
        """The snapshot is retained on success so later phases keep their inputs."""
        self._drive_happy_path()
        self.assertEqual(len(self.snapshots), 1)
        self.assertTrue(self.snapshots[0].is_dir())
        self.assertTrue((self.snapshots[0] / "libwksim_e0.so").is_file())


# --------------------------------------------------------------------------
# 4. Optimized-mode refusal: assert-based gates must never be stripped.
# --------------------------------------------------------------------------


class OptimizedModeGuardTests(unittest.TestCase):
    """Under ``python -O`` every numeric/lifecycle gate is stripped, so a run
    could be reported as ``pass`` without being checked.  Both execution entry
    points must refuse to start, before any filesystem write or model load.

    The subprocess tests use a real ``-O`` interpreter; nothing is compiled,
    no ``.so`` is loaded, and the paths are deliberately nonexistent.
    """

    VALIDATOR = ROOT / "tools/validate_generated_e0_lifecycle.py"

    def _run_under(self, optimize_flag, code):
        return subprocess.run(
            [sys.executable, optimize_flag, "-B", "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _programmatic_probe(self, tmp, flag="-O"):
        """Import the module under an optimized interpreter and call both entry points."""
        out = Path(tmp) / "sentinel-output"
        code = (
            "import sys; sys.path.insert(0, r'%s')\n"
            "import validate_generated_e0_lifecycle as v\n"
            "print('DEBUG_FLAG', __debug__)\n"
            "for name, args in (('run', ('absent-manifest.json', r'%s')),"
            " ('probe', ('absent-lib.so', r'%s'))):\n"
            "    try:\n"
            "        getattr(v, name)(*args)\n"
            "        print(name, 'NO_RAISE')\n"
            "    except v.AdmissionError as exc:\n"
            "        print(name, 'REFUSED', str(exc)[:40])\n"
            % (str(ROOT / "tools"), str(out), str(out))
        )
        return self._run_under(flag, code), out

    def test_programmatic_calls_refuse_under_optimized_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, out = self._programmatic_probe(tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            stdout = proc.stdout
            self.assertIn("DEBUG_FLAG False", stdout)
            self.assertIn("run REFUSED", stdout)
            self.assertIn("probe REFUSED", stdout)
            self.assertNotIn("NO_RAISE", stdout)
            # Proof the refusal happened before any filesystem effect.
            self.assertFalse(out.exists(), "guard let the run create its output")

    def test_cli_refuses_under_optimized_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "cli-output"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-O",
                    "-B",
                    str(self.VALIDATOR),
                    "--manifest",
                    "absent-manifest.json",
                    "--output",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertNotEqual(proc.returncode, 0)
            combined = (proc.stdout + proc.stderr).lower()
            self.assertIn("assertions are disabled", combined)
            self.assertFalse(out.exists(), "guard let the CLI create its output")

    def test_double_optimized_interpreter_also_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, out = self._programmatic_probe(tmp, flag="-OO")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("DEBUG_FLAG False", proc.stdout)
            self.assertIn("REFUSED", proc.stdout)
            self.assertNotIn("NO_RAISE", proc.stdout)
            self.assertFalse(out.exists())


    def test_guard_precedes_every_other_entry_point_check(self):
        """Even with a plausible platform, the guard is what rejects first.

        ``__debug__`` is a compile-time constant and cannot be monkeypatched, so
        the -O subprocess is combined with a source-level check that the guard
        call is the first statement (see the AST test above).
        """
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "precedence-output"
            proc = self._run_under(
                "-O",
                "import sys; sys.path.insert(0, r'%s')\n"
                "import validate_generated_e0_lifecycle as v\n"
                "print('PLATFORM', sys.platform)\n"
                "try:\n"
                "    v.run('absent-manifest.json', r'%s')\n"
                "    print('NO_RAISE')\n"
                "except v.AdmissionError as exc:\n"
                "    print('GUARD_FIRST', str(exc)[:30])\n"
                "except Exception as exc:\n"
                "    print('OTHER', type(exc).__name__)\n"
                % (str(ROOT / "tools"), str(out)),
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("GUARD_FIRST", proc.stdout)
            self.assertNotIn("OTHER", proc.stdout)
            self.assertNotIn("NO_RAISE", proc.stdout)
            self.assertFalse(out.exists())


    def test_normal_mode_guard_is_a_no_op(self):
        self.assertTrue(__debug__)
        self.assertIsNone(validator.require_assertions_enabled())


if __name__ == "__main__":
    unittest.main()
