#!/usr/bin/env python3
"""Pure-file tests for tools/probe_release_audit_integrity.py.

No ROS, no rclpy, no native binaries, no flights. Every fixture is a small
synthetic evidence tree built in a temporary directory; a stub codec stands in
for the frozen generated messages so the tamper pipeline can be exercised
offline. The stub auditors decode the capture file themselves, so they are
independent of the probe's codec.

The real run against the 319-file evidence directory and the ROS offline
decode is the main session's job; these tests only exercise the machinery.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = ROOT / "tools" / "probe_release_audit_integrity.py"

AP_CMD = "/uav1/prometheus/v2/command"
AP_SETUP = "/uav1/prometheus/v2/setup"

# Allowlisted inputs the fixture must provide, minus the two derived sources.
FIXTURE_INPUTS = 11
FIXTURE_DERIVED = 2
FIXTURE_TOTAL_INPUTS = FIXTURE_INPUTS + FIXTURE_DERIVED


def load_probe():
    spec = importlib.util.spec_from_file_location("probe_under_test", PROBE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = load_probe()


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cdr(obj) -> str:
    return json.dumps(obj, separators=(",", ":")).encode("utf-8").hex()


def hardlinks_supported() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "a"
        src.write_bytes(b"x")
        try:
            os.link(src, Path(tmp) / "b")
            return True
        except OSError:
            return False


def symlinks_supported() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "target"
        target.write_bytes(b"x")
        try:
            os.symlink(target, Path(tmp) / "link")
            return True
        except (OSError, NotImplementedError):
            return False


def dir_symlinks_supported() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "target"
        target.mkdir()
        try:
            os.symlink(target, Path(tmp) / "link", target_is_directory=True)
            return True
        except (OSError, NotImplementedError):
            return False


HARDLINKS = hardlinks_supported()
SYMLINKS = symlinks_supported()
DIR_SYMLINKS = dir_symlinks_supported()


# --------------------------------------------------------------------------
# stub modules written to disk
# --------------------------------------------------------------------------

STRICT_AUDITOR = '''
import hashlib, json
from pathlib import Path


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def audit(root):
    root = Path(root)
    result = json.loads((root / 'result.json').read_text())
    for name, expected in result['source_sha256'].items():
        path = root / ('source__' + name.replace('/', '__') + '.txt')
        if _sha(path) != expected:
            raise ValueError('retained source changed: ' + name)
    rows = []
    for line in (root / 'pv-dds.jsonl').read_bytes().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    prev = 0
    for row in rows:
        if row['sequence'] != prev + 1:
            raise ValueError('capture sequence gap')
        prev = row['sequence']
    commands, payloads, setups = [], [], []
    for row in rows:
        if row['topic'] == %(cmd)r:
            msg = json.loads(bytes.fromhex(row['cdr_hex']).decode())
            commands.append(msg['request_id'])
            payloads.append(msg['command']['velocity_ref'][0])
        elif row['topic'] == %(setup)r:
            setups.append(json.loads(bytes.fromhex(row['cdr_hex']).decode())['setup']['px4_mode'])
    if commands != result['expected_commands']:
        raise ValueError('publisher command coverage differs: %%r' %% (commands,))
    if payloads != result['expected_velocity_ref0']:
        raise ValueError('command payload differs: %%r' %% (payloads,))
    if setups != result['expected_setup_modes']:
        raise ValueError('setup mode differs: %%r' %% (setups,))
    ledger = [l for l in (root / 'arducopter/prometheus.jsonl').read_bytes().splitlines() if l.strip()]
    if len(ledger) != result['expected_ledger_lines']:
        raise ValueError('ledger length differs')
    pubs = [(json.loads(l)['message'].get('request_id'), json.loads(l).get('published'))
            for l in ledger if json.loads(l).get('request_envelope')]
    if pubs != [tuple(p) for p in result['expected_publications']]:
        raise ValueError('publish ledger publication coverage differs: %%r' %% (pubs,))
    return {'status': 'pass'}
''' % {"cmd": AP_CMD, "setup": AP_SETUP}

# Checks publication coverage only and ignores every non-publication row, so a
# rejection cannot be attributed to unrelated telemetry loss.
PUBLICATION_ONLY_AUDITOR = '''
import json
from pathlib import Path


def audit(root):
    root = Path(root)
    pubs = []
    for line in (root / 'arducopter/prometheus.jsonl').read_bytes().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get('request_envelope'):
            pubs.append((row['message'].get('request_id'), row.get('published')))
    expected = [tuple(p) for p in
                json.loads((root / 'result.json').read_text())['expected_publications']]
    if pubs != expected:
        raise ValueError('publication coverage differs: %r' % (pubs,))
    return {'status': 'pass'}
'''

# Rejects every required corruption but ignores setup modes and ledger length,
# so an explicitly requested optional setup tamper is accepted while the
# required matrix itself still holds.
REQUIRED_ONLY_AUDITOR = '''
import hashlib, json
from pathlib import Path


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def audit(root):
    root = Path(root)
    result = json.loads((root / 'result.json').read_text())
    for name, expected in result['source_sha256'].items():
        if _sha(root / ('source__' + name.replace('/', '__') + '.txt')) != expected:
            raise ValueError('retained source changed: ' + name)
    rows = [json.loads(l) for l in
            (root / 'pv-dds.jsonl').read_bytes().splitlines() if l.strip()]
    commands, payloads = [], []
    for row in rows:
        if row['topic'] == %(cmd)r:
            msg = json.loads(bytes.fromhex(row['cdr_hex']).decode())
            commands.append(msg['request_id'])
            payloads.append(msg['command']['velocity_ref'][0])
    if commands != result['expected_commands']:
        raise ValueError('publisher command coverage differs: %%r' %% (commands,))
    if payloads != result['expected_velocity_ref0']:
        raise ValueError('command payload differs: %%r' %% (payloads,))
    pubs = []
    for line in (root / 'arducopter/prometheus.jsonl').read_bytes().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get('request_envelope'):
            pubs.append((row['message'].get('request_id'), row.get('published')))
    if pubs != [tuple(p) for p in result['expected_publications']]:
        raise ValueError('publication coverage differs: %%r' %% (pubs,))
    return {'status': 'pass'}
''' % {"cmd": AP_CMD}

SEQUENCE_ONLY_AUDITOR = '''
import json
from pathlib import Path


def audit(root):
    prev = 0
    for line in (Path(root) / 'pv-dds.jsonl').read_bytes().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row['sequence'] != prev + 1:
            raise ValueError('capture sequence gap')
        prev = row['sequence']
    return {'status': 'pass'}
'''

PERMISSIVE_AUDITOR = '''
def audit(root):
    return {'status': 'pass'}
'''

ALWAYS_RAISE_AUDITOR = '''
def audit(root):
    raise ValueError('always rejects')
'''

NO_AUDIT_MODULE = '''
def something_else(root):
    return {}
'''

STUB_CODEC = '''
import json


class JsonCodec:
    name = 'stub-json-codec'

    def deserialize(self, topic, raw):
        return json.loads(raw.decode('utf-8'))

    def serialize(self, topic, message):
        return json.dumps(message, separators=(',', ':')).encode('utf-8')


def make_codec():
    return JsonCodec()
'''

BROKEN_CODEC = '''
def make_codec():
    raise ImportError('wksim_msgs generated messages unavailable')
'''


def write_modules(base: Path) -> dict:
    out = {}
    files = {
        "strict_auditor.py": STRICT_AUDITOR,
        "publication_only_auditor.py": PUBLICATION_ONLY_AUDITOR,
        "required_only_auditor.py": REQUIRED_ONLY_AUDITOR,
        "sequence_only_auditor.py": SEQUENCE_ONLY_AUDITOR,
        "permissive_auditor.py": PERMISSIVE_AUDITOR,
        "always_raise_auditor.py": ALWAYS_RAISE_AUDITOR,
        "no_audit.py": NO_AUDIT_MODULE,
        "stub_codec.py": STUB_CODEC,
        "broken_codec.py": BROKEN_CODEC,
    }
    for name, text in files.items():
        path = base / name
        path.write_text(text, encoding="utf-8")
        out[name] = path
    return out


# --------------------------------------------------------------------------
# synthetic evidence root
# --------------------------------------------------------------------------

def build_raw_root(base: Path, big_bytes: int = 1_500_000,
                   trailing_receive: int = 3) -> Path:
    raw = base / "raw-evidence"
    for sub in ("arducopter/planner-release", "px4", "native-source", "vendor"):
        (raw / sub).mkdir(parents=True, exist_ok=True)

    demo = raw / "source__tools__demo.py.txt"
    demo.write_text("print('demo')\n", encoding="utf-8")
    sim = raw / "source__Simulator__wksim_runtime__demo.py.txt"
    sim.write_text("VALUE = 1\n", encoding="utf-8")

    capture_rows = [
        {"sequence": 1, "topic": "/uav1/prometheus/text_info",
         "cdr_hex": cdr({"event": "started", "event_id": 1})},
        {"sequence": 2, "topic": AP_SETUP,
         "cdr_hex": cdr({"request_id": 66, "setup": {"cmd": 1, "px4_mode": "BRAKE"}})},
        {"sequence": 3, "topic": AP_CMD,
         "cdr_hex": cdr({"request_id": 4,
                         "command": {"command_id": 1, "velocity_ref": [1.0, 0.0, 0.0]}})},
        {"sequence": 4, "topic": AP_CMD,
         "cdr_hex": cdr({"request_id": 5,
                         "command": {"command_id": 2, "velocity_ref": [2.0, 0.0, 0.0]}})},
        {"sequence": 5, "topic": "/uav2/prometheus/text_info",
         "cdr_hex": cdr({"event": "started", "event_id": 1})},
        {"sequence": 6, "topic": AP_SETUP,
         "cdr_hex": cdr({"request_id": 67,
                         "setup": {"cmd": 1, "px4_mode": "AUTO.LAND"}})},
    ]
    (raw / "pv-dds.jsonl").write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in capture_rows),
        encoding="utf-8")

    # Publications come first; the tail is dominated by ordinary receive rows,
    # mirroring the real ledger where a naive "drop the last line" cut removes
    # telemetry instead of a publication.
    ledger_rows = [
        {"wall": 1.0, "published": "CommandRequest", "request_envelope": True,
         "message": {"request_id": 62, "command": {}}},
        {"wall": 2.0, "published": "CommandRequest", "request_envelope": True,
         "message": {"request_id": 63, "command": {}}},
        {"wall": 3.0, "published": "SetupRequest", "request_envelope": True,
         "message": {"request_id": 67, "setup": {}}},
    ]
    for index in range(trailing_receive):
        ledger_rows.append({
            "wall": 3.0 + index * 0.01,
            "topic": "/uav1/prometheus/control_state",
            "message": {"uav_id": 1, "control_state": 0},
        })
    (raw / "arducopter" / "prometheus.jsonl").write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in ledger_rows),
        encoding="utf-8")

    result = {
        "status": "observed",
        "source_sha256": {"tools/demo.py": sha(demo)},
        "expected_commands": [4, 5],
        "expected_velocity_ref0": [1.0, 2.0],
        "expected_setup_modes": ["BRAKE", "AUTO.LAND"],
        "expected_ledger_lines": len(ledger_rows),
        "expected_publications": [[62, "CommandRequest"],
                                  [63, "CommandRequest"],
                                  [67, "SetupRequest"]],
    }
    (raw / "result.json").write_text(json.dumps(result, indent=2) + "\n",
                                     encoding="utf-8")
    (raw / "control-build.json").write_text(
        json.dumps({"simulator_python_sha256":
                    {"wksim_runtime/demo.py": sha(sim)}}, indent=2) + "\n",
        encoding="utf-8")

    # Remaining allowlisted inputs (contents irrelevant to the stub auditor).
    (raw / "arducopter" / "planner-release" /
     "planner-release-handoff.json").write_text("{}\n", encoding="utf-8")
    (raw / "arducopter" / "result.json").write_text('{"status": "pass"}\n', encoding="utf-8")
    (raw / "px4" / "result.json").write_text('{"status": "pass"}\n', encoding="utf-8")
    (raw / "px4" / "prometheus.jsonl").write_text('{"wall": 1}\n', encoding="utf-8")
    (raw / "rate.jsonl").write_text('{"kind": "rate_group_end"}\n', encoding="utf-8")
    # Large allowlisted file so the hardlink path is exercised.
    with open(raw / "arducopter-truth.jsonl", "wb") as handle:
        handle.write(b'{"tick": 1}\n' + b"\x00" * big_bytes)
    (raw / "px4-truth.jsonl").write_text('{"tick": 1}\n', encoding="utf-8")

    # Unlisted material that must never be duplicated into a probe copy.
    (raw / "native-source" / "thing.txt").write_text("native\n", encoding="utf-8")
    (raw / "vendor" / "lib.bin").write_bytes(b"\x00" * 4096)
    with open(raw / "unlisted-blob.bin", "wb") as handle:
        handle.write(b"\x00" * big_bytes)
    return raw


class ProbeTestCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="wksim-probe-test-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.raw = build_raw_root(self.base)
        self.mods = write_modules(self.base)
        self.out = self.base / "out"
        self.raw_snapshot = probe.tree_sha256(self.raw)

    def run_probe(self, auditor, codec="stub_codec.py", extra=(), cleanup=True,
                  raw=None, out=None):
        argv = ["--raw-root", str(raw or self.raw),
                "--auditor-file", str(self.mods[auditor]),
                "--output-dir", str(out or self.out)]
        if cleanup:
            argv.append("--cleanup-own-work")
        if codec:
            argv += ["--codec-module", str(self.mods[codec])]
        argv += list(extra)
        args = probe.build_parser().parse_args(argv)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            report = probe.run_probe(args)
        self.last_log = buffer.getvalue()
        return report

    def run_probe_expecting_error(self, out):
        argv = ["--raw-root", str(self.raw),
                "--auditor-file", str(self.mods["strict_auditor.py"]),
                "--output-dir", str(out),
                "--codec-module", str(self.mods["stub_codec.py"])]
        args = probe.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(probe.ProbeError):
                probe.run_probe(args)

    def scenario(self, report, name):
        for entry in report["scenarios"]:
            if entry["name"] == name:
                return entry
        self.fail(f"scenario {name} not present in report")

    def assert_raw_unchanged(self):
        after = probe.tree_sha256(self.raw)
        self.assertEqual(self.raw_snapshot, after,
                         "raw baseline was modified by the probe")

    # -- core acceptance ---------------------------------------------------

    def test_strict_auditor_rejects_every_negative_and_accepts_positive(self):
        report = self.run_probe("strict_auditor.py")
        self.assertEqual(report["verdict"], "pass", report["verdict_reasons"])
        self.assertEqual(self.scenario(report, "positive_unmodified")["outcome"],
                         "accepted")
        for name in probe.REQUIRED_SCENARIOS:
            self.assertEqual(self.scenario(report, name)["outcome"], "rejected",
                             f"{name} was not rejected")
        self.assertTrue(report["baseline"]["unchanged"])
        self.assert_raw_unchanged()

    def test_positive_is_evaluated_before_any_negative(self):
        report = self.run_probe("strict_auditor.py")
        self.assertEqual(report["scenarios"][0]["name"], "positive_unmodified")
        self.assertEqual(report["scenarios"][0]["outcome"], "accepted")

    def test_all_four_required_scenarios_are_present(self):
        report = self.run_probe("strict_auditor.py")
        names = [s["name"] for s in report["scenarios"]]
        for name in probe.REQUIRED_SCENARIOS:
            self.assertIn(name, names)

    def test_every_negative_carries_before_and_after_sha(self):
        report = self.run_probe("strict_auditor.py")
        for name in probe.REQUIRED_SCENARIOS:
            entry = self.scenario(report, name)
            self.assertTrue(entry["source_sha256"], f"{name} lacks original sha")
            self.assertTrue(entry["case_sha256"], f"{name} lacks case sha")
            for rel, before in entry["source_sha256"].items():
                self.assertNotEqual(before, entry["case_sha256"][rel],
                                    f"{name} did not actually change {rel}")

    # -- negative controls on the harness itself ---------------------------

    def test_permissive_auditor_fails_because_corruptions_survive(self):
        report = self.run_probe("permissive_auditor.py")
        self.assertEqual(report["verdict"], "fail")
        self.assertTrue(any("not rejected" in r for r in report["verdict_reasons"]))

    def test_always_raising_auditor_does_not_count_as_pass(self):
        report = self.run_probe("always_raise_auditor.py")
        self.assertEqual(report["verdict"], "fail")
        self.assertTrue(any("positive control was not accepted" in r
                            for r in report["verdict_reasons"]))
        self.assert_raw_unchanged()

    def test_renumbering_hides_gap_from_sequence_only_check(self):
        """Documents why the gap scenario renumbers: a naive check misses it."""
        report = self.run_probe("sequence_only_auditor.py")
        gap = self.scenario(report, "ledger_command_gap")
        self.assertEqual(gap["outcome"], "accepted")
        self.assertEqual(gap["mutations"][0]["remaining_rows"], 5)
        self.assertTrue(gap["mutations"][0]["renumbered"])
        self.assertEqual(report["verdict"], "fail")

    # -- audit input allowlist --------------------------------------------

    def test_only_the_audit_input_set_is_copied(self):
        report = self.run_probe("strict_auditor.py", cleanup=False)
        case = Path(report["work_root"]) / "positive-unmodified"
        for rel in probe.AUDIT_INPUTS:
            self.assertTrue((case / rel).is_file(), f"missing audit input {rel}")
        self.assertEqual(report["audit_inputs"]["count"], FIXTURE_TOTAL_INPUTS)
        self.assertEqual(report["audit_inputs"]["missing"], [])

    def test_unlisted_and_vendor_material_is_excluded(self):
        report = self.run_probe("strict_auditor.py", cleanup=False)
        case = Path(report["work_root"]) / "positive-unmodified"
        self.assertFalse((case / "unlisted-blob.bin").exists())
        self.assertFalse((case / "native-source").exists())
        self.assertFalse((case / "vendor").exists())
        self.assertEqual(report["audit_inputs"]["excluded_prefixes"],
                         ["vendor/", "native-source/"])
        probe.safe_cleanup(Path(report["work_root"]), self.raw)

    def test_resolved_inputs_derive_retained_sources_from_manifests(self):
        report = self.run_probe("strict_auditor.py")
        derived = report["audit_inputs"]["derived_retained_sources"]
        self.assertIn("source__tools__demo.py.txt", derived)
        self.assertIn("source__Simulator__wksim_runtime__demo.py.txt", derived)

    def test_forbidden_and_escaping_paths_are_refused(self):
        for bad in ("vendor/x.bin", "native-source/y.txt", "../escape.txt",
                    "/abs/path.txt"):
            with self.assertRaises(probe.ProbeError, msg=bad):
                probe.refuse_forbidden(bad)
        self.assertEqual(probe.refuse_forbidden("arducopter/result.json"),
                         "arducopter/result.json")

    def test_missing_audit_input_is_reported_not_fatal(self):
        (self.raw / "px4" / "result.json").unlink()
        report = self.run_probe("strict_auditor.py")
        self.assertIn("px4/result.json", report["audit_inputs"]["missing"])
        self.assertEqual(report["audit_inputs"]["count"],
                         FIXTURE_TOTAL_INPUTS - 1)
        self.assertEqual(report["verdict"], "pass")

    # -- isolation ---------------------------------------------------------

    def test_hardlinked_input_is_never_written_through(self):
        capture = self.raw / "pv-dds.jsonl"
        truth = self.raw / "arducopter-truth.jsonl"
        before = (sha(capture), sha(truth))
        report = self.run_probe("strict_auditor.py")
        self.assertEqual((sha(capture), sha(truth)), before)
        self.assertTrue(report["baseline"]["unchanged"])
        self.assert_raw_unchanged()

    def test_large_allowlisted_input_takes_the_hardlink_path(self):
        report = self.run_probe("strict_auditor.py")
        positive = self.scenario(report, "positive_unmodified")
        self.assertEqual(positive["copy"]["files"], FIXTURE_TOTAL_INPUTS)
        if HARDLINKS:
            self.assertGreaterEqual(positive["copy"]["linked"], 1)
        self.assertEqual(sha(self.raw / "arducopter-truth.jsonl"),
                         self.raw_snapshot["arducopter-truth.jsonl"])

    def test_mutated_file_is_independent_of_original(self):
        capture_before = sha(self.raw / "pv-dds.jsonl")
        ledger_before = sha(self.raw / "arducopter" / "prometheus.jsonl")
        self.run_probe("strict_auditor.py")
        self.assertEqual(sha(self.raw / "pv-dds.jsonl"), capture_before)
        self.assertEqual(sha(self.raw / "arducopter" / "prometheus.jsonl"),
                         ledger_before)

    def test_mutating_a_hardlinked_copy_never_writes_through(self):
        """Force every input to be hardlinked, then mutate it.

        With the default 1 MiB threshold the mutated files are small and get
        duplicated, so the atomic-replace-over-a-hardlink path would go
        untested.  Here the mutated ledger starts life as a hardlink, so a
        write-through would corrupt the read-only baseline.
        """
        if not HARDLINKS:
            self.skipTest("platform does not support hardlinks")
        ledger = self.raw / "arducopter" / "prometheus.jsonl"
        capture = self.raw / "pv-dds.jsonl"
        ledger_inode, ledger_links = ledger.stat().st_ino, ledger.stat().st_nlink
        before = (sha(ledger), sha(capture))

        report = self.run_probe("strict_auditor.py", cleanup=False,
                                extra=["--hardlink-min-bytes", "0"])
        positive = self.scenario(report, "positive_unmodified")
        self.assertEqual(positive["copy"]["linked"], FIXTURE_TOTAL_INPUTS)
        self.assertEqual(positive["copy"]["copied"], 0)

        # Hardlinked copies legitimately raise the link count; the bytes and
        # the inode of the baseline must not move.
        self.assertEqual((sha(ledger), sha(capture)), before)
        self.assertEqual(ledger.stat().st_ino, ledger_inode)
        self.assertGreater(ledger.stat().st_nlink, ledger_links)
        self.assertTrue(report["baseline"]["unchanged"])

        # The mutated per-scenario copy is a genuinely separate inode.
        truncation = self.scenario(report, "ledger_tail_truncation")
        self.assertEqual(truncation["outcome"], "rejected")
        case_ledger = (Path(report["work_root"]) / "ledger_tail_truncation" /
                       "arducopter" / "prometheus.jsonl")
        self.assertTrue(case_ledger.is_file())
        self.assertNotEqual(case_ledger.stat().st_ino, ledger_inode)
        self.assertNotEqual(sha(case_ledger), before[0])

        # Removing the probe-owned tree restores the original link count.
        self.assertTrue(probe.safe_cleanup(Path(report["work_root"]),
                                           self.raw)["removed"])
        self.assertEqual(ledger.stat().st_nlink, ledger_links)
        self.assertEqual((sha(ledger), sha(capture)), before)
        self.assert_raw_unchanged()

    def test_outputs_are_written_and_parseable(self):
        report = self.run_probe("strict_auditor.py")
        report_file = self.out / "probe-report.json"
        log_file = self.out / "probe.log"
        self.assertTrue(report_file.is_file())
        self.assertTrue(log_file.is_file())
        on_disk = json.loads(report_file.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["verdict"], report["verdict"])
        self.assertIn("auditor_sha256", on_disk)
        self.assertIn("audit_inputs", on_disk)
        self.assertTrue(on_disk["limitations"])

    def test_cleanup_removes_only_probe_owned_work_directory(self):
        report = self.run_probe("strict_auditor.py")
        self.assertTrue(report["cleanup"]["removed"])
        self.assertFalse(Path(report["work_root"]).exists())
        self.assertTrue(self.raw.is_dir())

    def test_work_directory_is_kept_when_cleanup_not_requested(self):
        report = self.run_probe("strict_auditor.py", cleanup=False)
        self.assertFalse(report["cleanup"]["removed"])
        work = Path(report["work_root"])
        self.assertTrue(work.is_dir())
        self.assertTrue(work.name.startswith(probe.OWN_TEMP_PREFIX))
        self.assertTrue((work / "positive-unmodified" / "result.json").is_file())
        self.assert_raw_unchanged()
        probe.safe_cleanup(work, self.raw)

    # -- root safety -------------------------------------------------------

    def test_input_path_escaping_raw_root_is_refused(self):
        """Covers the containment guard that also catches directory junctions."""
        with self.assertRaises(probe.ProbeError):
            probe._reject_symlinked_input(self.raw.resolve(),
                                          "../outside-evidence.json")

    def test_normal_inputs_resolve_inside_raw_without_links(self):
        inputs = probe.resolve_audit_inputs(self.raw.resolve())
        self.assertEqual(inputs["missing"], [])
        self.assertEqual(len(inputs["files"]), FIXTURE_TOTAL_INPUTS)
        real_raw = Path(os.path.realpath(self.raw))
        for rel, path in inputs["files"].items():
            self.assertFalse(os.path.islink(path), rel)
            self.assertTrue(
                probe.is_within(Path(os.path.realpath(path)), real_raw), rel)
        report = self.run_probe("strict_auditor.py")
        self.assertEqual(report["verdict"], "pass")
        self.assertTrue(report["complete_matrix_pass"])
        self.assert_raw_unchanged()

    def test_external_symlinked_input_file_is_refused(self):
        if not SYMLINKS:
            self.skipTest("platform does not support symlinks")
        outside = self.base / "outside-rate.jsonl"
        outside.write_text('{"kind": "external"}\n', encoding="utf-8")
        target = self.raw / "rate.jsonl"
        target.unlink()
        os.symlink(outside, target)
        self.assertTrue(os.path.islink(target))

        with self.assertRaises(probe.ProbeError):
            probe.resolve_audit_inputs(self.raw.resolve())

        out = self.base / "out-refused-file"
        self.run_probe_expecting_error(out)
        self.assertFalse(out.exists(),
                         "output directory was created before the input check")
        self.assertEqual(outside.read_text(encoding="utf-8"),
                         '{"kind": "external"}\n')

    def test_external_symlinked_input_directory_is_refused(self):
        if not DIR_SYMLINKS:
            self.skipTest("platform does not support directory symlinks")
        external = self.base / "external-px4"
        external.mkdir()
        (external / "result.json").write_text('{"status": "pass"}\n',
                                             encoding="utf-8")
        (external / "prometheus.jsonl").write_text('{"wall": 1}\n',
                                                  encoding="utf-8")
        real_dir = self.raw / "px4"
        shutil.rmtree(real_dir)
        os.symlink(external, real_dir, target_is_directory=True)
        self.assertTrue(os.path.islink(real_dir))

        with self.assertRaises(probe.ProbeError):
            probe.resolve_audit_inputs(self.raw.resolve())

        out = self.base / "out-refused-dir"
        self.run_probe_expecting_error(out)
        self.assertFalse(out.exists(),
                         "output directory was created before the input check")
        self.assertEqual(sorted(p.name for p in external.iterdir()),
                         ["prometheus.jsonl", "result.json"])

    def test_linked_input_branch_is_enforced_without_symlink_privileges(self):
        """Exercises the symlink-component guard where links cannot be made.

        Windows without developer mode cannot create symlinks, so the real-link
        tests skip there.  Forcing ``os.path.islink`` for one real input proves
        the guard itself fires and that no output directory is created.
        """
        raw_resolved = Path(os.path.realpath(self.raw))
        target = os.path.normcase(
            os.path.normpath(str(raw_resolved / "rate.jsonl")))
        real_islink = os.path.islink

        def fake_islink(path):
            try:
                if os.path.normcase(os.path.normpath(os.fspath(path))) == target:
                    return True
            except TypeError:
                pass
            return real_islink(path)

        out = self.base / "out-refused-forced"
        with mock.patch("os.path.islink", side_effect=fake_islink):
            with self.assertRaises(probe.ProbeError):
                probe.resolve_audit_inputs(raw_resolved)
            self.run_probe_expecting_error(out)
        self.assertFalse(out.exists(),
                         "output directory was created before the input check")
        self.assert_raw_unchanged()

    def test_equal_roots_are_refused(self):
        with self.assertRaises(probe.ProbeError):
            probe.assert_disjoint(self.raw, self.raw, "output")

    def test_nested_roots_are_refused(self):
        with self.assertRaises(probe.ProbeError):
            probe.assert_disjoint(self.raw, self.raw / "nested", "output")
        with self.assertRaises(probe.ProbeError):
            probe.assert_disjoint(self.raw / "sub", self.raw, "output")

    def test_output_dir_inside_raw_root_is_refused(self):
        argv = ["--raw-root", str(self.raw),
                "--auditor-file", str(self.mods["strict_auditor.py"]),
                "--output-dir", str(self.raw / "out"),
                "--codec-module", str(self.mods["stub_codec.py"])]
        args = probe.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(probe.ProbeError):
                probe.run_probe(args)
        self.assertFalse((self.raw / "out").exists())

    def test_failed_report_return_is_not_a_positive_acceptance(self):
        from types import SimpleNamespace
        auditor = SimpleNamespace(audit=lambda root: {"status": "failed"})
        result = probe.invoke_audit(auditor, self.raw, (ValueError, AssertionError))
        self.assertEqual(result["outcome"], "error")

    def test_changed_baseline_overrides_otherwise_passing_scenarios(self):
        scenarios = [
            {"name": "positive", "kind": "positive", "outcome": "accepted"},
            {"name": "negative", "kind": "negative", "outcome": "rejected"},
        ]
        self.assertEqual(probe.decide(scenarios)[0], "pass")
        self.assertEqual(probe.decide(scenarios, baseline_unchanged=False)[0], "fail")

    def test_absent_or_non_dict_report_status_is_not_acceptance(self):
        """Only an explicit status of 'pass' may count as acceptance."""
        from types import SimpleNamespace
        for returned in (None, {}, {"status": None}, ["pass"], {"ok": True}):
            with self.subTest(returned=returned):
                auditor = SimpleNamespace(audit=lambda root, r=returned: r)
                result = probe.invoke_audit(auditor, self.raw,
                                            (ValueError, AssertionError))
                self.assertEqual(result["outcome"], "error")

    def test_workspace_like_root_is_refused(self):
        fake = self.base / "checkout"
        (fake / ".git").mkdir(parents=True)
        with self.assertRaises(probe.ProbeError):
            probe.assert_not_workspace_root(fake)

    def test_safe_cleanup_refuses_foreign_and_raw_paths(self):
        foreign = self.base / "not-probe-owned"
        foreign.mkdir()
        result = probe.safe_cleanup(foreign, self.raw)
        self.assertFalse(result["removed"])
        self.assertTrue(foreign.is_dir())
        result = probe.safe_cleanup(self.raw, self.raw)
        self.assertFalse(result["removed"])
        self.assertTrue(self.raw.is_dir())

    # -- environment reporting --------------------------------------------

    def test_missing_audit_function_is_reported(self):
        argv = ["--raw-root", str(self.raw),
                "--auditor-file", str(self.mods["no_audit.py"]),
                "--output-dir", str(self.out)]
        args = probe.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(probe.ProbeError):
                probe.run_probe(args)

    def test_missing_codec_blocks_tamper_without_faking_a_rejection(self):
        report = self.run_probe("strict_auditor.py", codec="broken_codec.py")
        self.assertIsNone(report["codec"])
        self.assertTrue(report["codec_error"])
        tamper = self.scenario(report, "command_payload_tamper")
        self.assertEqual(tamper["outcome"], "env_missing")
        self.assertEqual(report["verdict"], "blocked")
        self.assertEqual(self.scenario(report, "ledger_command_gap")["outcome"],
                         "rejected")
        self.assertEqual(self.scenario(report, "positive_unmodified")["outcome"],
                         "accepted")
        self.assert_raw_unchanged()

    def test_auditor_import_error_is_reported_as_environment(self):
        auditor = self.base / "needs_ros.py"
        auditor.write_text(
            "import definitely_missing_ros_package\n\n"
            "def audit(root):\n    return {'status': 'pass'}\n",
            encoding="utf-8")
        argv = ["--raw-root", str(self.raw),
                "--auditor-file", str(auditor),
                "--output-dir", str(self.out),
                "--codec-module", str(self.mods["stub_codec.py"])]
        args = probe.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(probe.ProbeError):
                probe.run_probe(args)

    def test_auditor_lazy_import_failure_yields_env_missing_not_rejection(self):
        auditor = self.base / "lazy_ros.py"
        auditor.write_text(
            "def audit(root):\n"
            "    import definitely_missing_ros_package  # noqa\n"
            "    return {'status': 'pass'}\n",
            encoding="utf-8")
        argv = ["--raw-root", str(self.raw),
                "--auditor-file", str(auditor),
                "--output-dir", str(self.out),
                "--codec-module", str(self.mods["stub_codec.py"]),
                "--cleanup-own-work"]
        args = probe.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(io.StringIO()):
            report = probe.run_probe(args)
        self.assertEqual(report["verdict"], "blocked")
        for entry in report["scenarios"]:
            self.assertEqual(entry["outcome"], "env_missing")
        self.assert_raw_unchanged()

    # -- scenario mechanics ------------------------------------------------

    def test_gap_scenario_deletes_the_first_ap_command_and_renumbers(self):
        report = self.run_probe("strict_auditor.py")
        detail = self.scenario(report, "ledger_command_gap")["mutations"][0]
        self.assertEqual(detail["topic"], AP_CMD)
        self.assertEqual(detail["deleted_sequence"], 3)
        self.assertEqual(detail["remaining_rows"], 5)

    def test_tamper_scenario_preserves_ids_and_changes_payload_only(self):
        report = self.run_probe("strict_auditor.py")
        detail = self.scenario(report, "command_payload_tamper")["mutations"][0]
        self.assertEqual(detail["topic"], AP_CMD)
        self.assertEqual(detail["field"], "command.velocity_ref.0")
        self.assertEqual(detail["old"], 1.0)
        self.assertNotEqual(detail["cdr_sha256_before"], detail["cdr_sha256_after"])

    def test_tamper_scenario_does_not_guess_cdr_offsets(self):
        """With no codec the probe refuses rather than fabricating bytes."""
        report = self.run_probe("strict_auditor.py", codec="broken_codec.py")
        tamper = self.scenario(report, "command_payload_tamper")
        self.assertEqual(tamper["outcome"], "env_missing")
        self.assertNotIn("case_sha256", tamper)

    def test_truncation_scenario_leaves_completion_report_untouched(self):
        report = self.run_probe("strict_auditor.py")
        entry = self.scenario(report, "ledger_tail_truncation")
        detail = entry["mutations"][0]
        # The mutation must remove a real publication, not a receive row.
        self.assertEqual(detail["removed_request_id"], 67)
        self.assertEqual(detail["removed_published"], "SetupRequest")
        self.assertEqual(detail["truncated_from_line"], 3)
        self.assertEqual(detail["publications_dropped"], 1)
        self.assertEqual(detail["non_publication_dropped"], 3)
        self.assertEqual(detail["remaining_records"], 2)
        self.assertEqual(detail["report_untouched"], "result.json")
        self.assertEqual(list(entry["source_sha256"]),
                         ["arducopter/prometheus.jsonl"])
        self.assertEqual(sha(self.raw / "result.json"),
                         self.raw_snapshot["result.json"])

    def test_truncation_targets_publication_with_long_receive_tail(self):
        """A long non-publication tail must not mask the removed publication."""
        base = Path(tempfile.mkdtemp(prefix="wksim-probe-tail-"))
        self.addCleanup(shutil.rmtree, base, True)
        raw = build_raw_root(base, trailing_receive=500)
        mods = write_modules(base)
        snapshot = probe.tree_sha256(raw)
        out = base / "out"
        argv = ["--raw-root", str(raw),
                "--auditor-file", str(mods["publication_only_auditor.py"]),
                "--output-dir", str(out),
                "--codec-module", str(mods["stub_codec.py"]),
                "--scenario", "ledger_tail_truncation",
                "--cleanup-own-work"]
        args = probe.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(io.StringIO()):
            report = probe.run_probe(args)
        entry = self.scenario(report, "ledger_tail_truncation")
        detail = entry["mutations"][0]
        self.assertEqual(detail["removed_request_id"], 67)
        self.assertEqual(detail["publications_dropped"], 1)
        self.assertEqual(detail["non_publication_dropped"], 500)
        self.assertEqual(detail["remaining_records"], 2)
        # This auditor ignores every non-publication row, so the rejection can
        # only come from the missing publication.
        self.assertEqual(entry["outcome"], "rejected")
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(probe.tree_sha256(raw), snapshot)

    def test_source_scenario_prefers_a_source_listed_in_result(self):
        report = self.run_probe("strict_auditor.py")
        detail = self.scenario(report, "retained_source_change")["mutations"][0]
        self.assertIn("source_sha256", detail["selection_reason"])
        self.assertNotEqual(detail["sha256_before"], detail["sha256_after"])

    def test_optional_setup_tamper_only_runs_when_requested(self):
        report = self.run_probe("strict_auditor.py")
        names = [s["name"] for s in report["scenarios"]]
        self.assertNotIn("setup_mode_tamper", names)
        report = self.run_probe("strict_auditor.py",
                                extra=["--with-setup-tamper"])
        self.assertEqual(self.scenario(report, "setup_mode_tamper")["outcome"],
                         "rejected")

    def test_single_scenario_selection(self):
        report = self.run_probe("strict_auditor.py",
                                extra=["--scenario", "ledger_tail_truncation"])
        names = [s["name"] for s in report["scenarios"]]
        self.assertIn("ledger_tail_truncation", names)
        self.assertNotIn("ledger_command_gap", names)

    # -- coverage semantics (selected pass vs complete matrix pass) --------

    def test_full_matrix_pass_sets_complete_matrix_pass(self):
        report = self.run_probe("strict_auditor.py")
        self.assertEqual(report["verdict"], "pass")
        self.assertTrue(report["selected_matrix_pass"])
        self.assertTrue(report["complete_matrix_pass"])
        coverage = report["coverage"]
        self.assertEqual(coverage["missing"], [])
        self.assertEqual(sorted(coverage["executed"]),
                         sorted(probe.REQUIRED_SCENARIOS))
        self.assertEqual(sorted(coverage["negatives_rejected"]),
                         sorted(probe.REQUIRED_SCENARIOS))
        self.assertTrue(coverage["positive_accepted"])
        self.assertTrue(coverage["baseline_unchanged"])
        # An auditor that lets the corruptions through cannot claim the matrix.
        permissive = self.run_probe("permissive_auditor.py")
        self.assertFalse(permissive["complete_matrix_pass"])
        self.assertFalse(permissive["coverage"]["complete_matrix_pass"])

    def test_partial_selection_pass_is_not_complete_matrix_pass(self):
        report = self.run_probe("strict_auditor.py",
                                extra=["--scenario", "ledger_tail_truncation"])
        self.assertEqual(report["verdict"], "pass")
        self.assertTrue(report["selected_matrix_pass"])
        self.assertFalse(report["complete_matrix_pass"])
        coverage = report["coverage"]
        self.assertEqual(coverage["executed"], ["ledger_tail_truncation"])
        self.assertEqual(sorted(coverage["missing"]),
                         sorted(set(probe.REQUIRED_SCENARIOS)
                                - {"ledger_tail_truncation"}))
        self.assertFalse(coverage["complete_matrix_pass"])
        self.assertTrue(any("partial matrix" in note
                            for note in report["limitations"]))

    def test_missing_environment_blocks_complete_matrix_pass(self):
        report = self.run_probe("strict_auditor.py", codec="broken_codec.py")
        self.assertEqual(report["verdict"], "blocked")
        self.assertFalse(report["selected_matrix_pass"])
        self.assertFalse(report["complete_matrix_pass"])
        coverage = report["coverage"]
        self.assertIn("command_payload_tamper", coverage["blocked_or_error"])
        self.assertEqual(coverage["missing"], [])
        self.assertNotIn("command_payload_tamper",
                         coverage["negatives_rejected"])

    def test_changed_baseline_blocks_complete_matrix_pass(self):
        scenarios = ([{"name": "positive_unmodified", "kind": "positive",
                       "outcome": "accepted"}]
                     + [{"name": name, "kind": "negative", "outcome": "rejected"}
                        for name in probe.REQUIRED_SCENARIOS])
        complete = probe.summarize_coverage(scenarios, True, True)
        self.assertTrue(complete["complete_matrix_pass"])
        self.assertTrue(complete["required_matrix_pass"])
        changed = probe.summarize_coverage(scenarios, False, True)
        self.assertFalse(changed["complete_matrix_pass"])
        self.assertFalse(changed["baseline_unchanged"])
        # Same scenarios without the positive control cannot be complete.
        no_positive = probe.summarize_coverage(scenarios[1:], True, True)
        self.assertFalse(no_positive["complete_matrix_pass"])
        self.assertFalse(no_positive["positive_accepted"])

    # -- tool identity, optional gating, derived-source dedup --------------

    def test_probe_tool_sha256_matches_own_bytes_and_differs_from_auditor(self):
        report = self.run_probe("strict_auditor.py")
        self.assertEqual(report["probe_tool_sha256"], sha(PROBE_PATH))
        self.assertEqual(report["probe_tool_file"], str(PROBE_PATH.resolve()))
        self.assertEqual(report["auditor_sha256"],
                         sha(self.mods["strict_auditor.py"]))
        self.assertNotEqual(report["probe_tool_sha256"],
                            report["auditor_sha256"])
        on_disk = json.loads((self.out / "probe-report.json").read_text(
            encoding="utf-8"))
        self.assertEqual(on_disk["probe_tool_sha256"], sha(PROBE_PATH))

    def test_blocked_optional_cannot_be_masked_by_complete_required_matrix(self):
        """A selected optional that is not rejected must break the final flag.

        The required-only auditor rejects all four required corruptions but
        ignores setup modes, so the explicitly requested optional scenario is
        accepted while the required matrix itself is complete.
        """
        report = self.run_probe("required_only_auditor.py",
                                extra=["--with-setup-tamper"])
        coverage = report["coverage"]
        self.assertEqual(sorted(coverage["executed"]),
                         sorted(probe.REQUIRED_SCENARIOS))
        self.assertEqual(sorted(coverage["negatives_rejected"]),
                         sorted(probe.REQUIRED_SCENARIOS))
        self.assertTrue(coverage["positive_accepted"])
        self.assertTrue(coverage["baseline_unchanged"])
        self.assertEqual(coverage["optional_executed"], ["setup_mode_tamper"])
        # The optional corruption really was accepted by this auditor, while
        # negatives_not_rejected stays scoped to the required matrix.
        self.assertEqual(self.scenario(report, "setup_mode_tamper")["outcome"],
                         "accepted")
        self.assertEqual(coverage["negatives_not_rejected"], [])
        # The required matrix holds, but the run itself is not a pass...
        self.assertTrue(coverage["required_matrix_pass"])
        self.assertFalse(coverage["verdict_pass"])
        self.assertEqual(report["verdict"], "fail")
        # ...so the overall completion flag must stay false.
        self.assertFalse(report["complete_matrix_pass"])
        self.assertFalse(coverage["complete_matrix_pass"])
        self.assertFalse(report["selected_matrix_pass"])
        self.assertTrue(any("verdict is not pass" in note
                            for note in report["limitations"]))

    def test_derived_retained_sources_are_deduplicated(self):
        """One retained file reachable from both manifests is listed once."""
        sim_source = self.raw / "source__Simulator__wksim_runtime__demo.py.txt"
        result_path = self.raw / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        # 'Simulator/<path>' hashes to the same source__ file that
        # control-build's 'simulator_python_sha256' entry derives.
        result["source_sha256"]["Simulator/wksim_runtime/demo.py"] = sha(sim_source)
        result_path.write_text(json.dumps(result, indent=2) + "\n",
                               encoding="utf-8")

        inputs = probe.resolve_audit_inputs(self.raw.resolve())
        derived = inputs["derived"]
        self.assertEqual(len(derived), len(set(derived)))
        self.assertEqual(derived.count("source__Simulator__wksim_runtime__demo.py.txt"), 1)

        report = self.run_probe("strict_auditor.py")
        listed = report["audit_inputs"]["derived_retained_sources"]
        self.assertEqual(len(listed), len(set(listed)))
        self.assertEqual(listed.count("source__Simulator__wksim_runtime__demo.py.txt"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
