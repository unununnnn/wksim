"""Offline context tests: CodeBuddy mixed-work-overrun v2 ingest binding (2026-09-14).

Binds the remediated docs/coordination/mixed-work-overrun-20260913-v2.md
(working-tree bytes, SHA256 b432e2c3bca0ffbcd7b77dd91304d6a5d064e9d6dabd20
a8fba1ec99e8836352 / 5410 bytes) as historical context at authoritative HEAD
31e5b65f5448c5558450d16d0f46da0ef0f0a03c and verifies, entirely offline (no
network, no native/ROS/SITL/build):

- recomputed SHA256/bytes of the remediated source doc, the finalized ingest
  note, and every cited tracked anchor against HEAD-tree bytes;
- the startup-artifact env semantics: launch.sh:4 explicit unset control,
  launch.json/children-start.json zero match, pre-run-identity.json:28 null;
- absent/external limitations: raw joint-wire.jsonl, go.json and
  experimental-admission.json are absent from the oxv29042 field directory in
  this checkout (HEAD tree and worktree) and cannot be reverified locally;
- v1-is-historical / v2-authoritative boundary; v1 script SHA e5a0db2b...
  never committed (exactly one committed analyzer version, 596cb5e6 ->
  1162d9fb...); live-runner drift against the frozen snapshot 65c7a867...;
- numerical observations remain historical diagnostic evidence only: no G6/
  Full/#84 closure, no #83 rerun, no acceptance promotion;
- the diagnostic gate vocabulary (1ms tick / native barrier / 4-tick
  grouping / no catch-up / 100ms / full windows / physics / identity gates)
  is preserved with its tracked anchor phrase;
- no PASS depends on any untracked-only external artifact: every checked
  anchor is either tracked (HEAD-tree bytes) or one of the two candidates;
- mutation negatives (hash, zero-count, unset-semantics, never-committed,
  note-boundary and promotion-language detectors actually fail on mutated
  inputs).

Run modes (the suite never mutates Git in either mode; all git invocations
are read-only):
- normal: python -m unittest
  validation.test_codebuddy_mixed_work_overrun_context (or pytest). Works
  pre-admission (candidates untracked) and after commit (candidates tracked);
  no tracked-status assertion is made either way.
- temporary GIT_INDEX_FILE: with the two candidates staged in a private
  external index (any stage-0 content, plus any future review/manifest paths
  a final batch may add) and WKSIM_MIXED_OVERRUN_TEMP_INDEX=1 in the
  environment, the suite additionally asserts that both candidates are
  staged at stage 0 and blob-identical to their working-tree bytes. The real
  index is never inspected and no requirement is placed on it.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

AUTHORITATIVE_HEAD = "31e5b65f5448c5558450d16d0f46da0ef0f0a03c"
ARCH_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"

# Remediated source document (working-tree binding).
SOURCE_REL = "docs/coordination/mixed-work-overrun-20260913-v2.md"
SOURCE_SHA256 = "b432e2c3bca0ffbcd7b77dd91304d6a5d064e9d6dabd20a8fba1ec99e8836352"
SOURCE_BYTES = 5410
# Pre-remediation version still in the HEAD tree at audit time.
HEAD_SOURCE_SHA256 = "24ad15729ac393026488f9356f265297a8b4b071c92ab6a501b0fe45bca4893a"
HEAD_SOURCE_BYTES = 2863

NOTE_REL = "docs/coordination/codebuddy-mixed-work-overrun-ingest-note-20260914.md"
NOTE_SHA256 = "1648f3d486e3e9bfe42632c39efaf4976237385be3703dc0903a4885bec6c575"
NOTE_BYTES = 9531

TEST_REL = "validation/test_codebuddy_mixed_work_overrun_context.py"

# The two candidates a final batch stages (temp-index mode).
CANDIDATE_PATHS = (NOTE_REL, TEST_REL)

FIELD_DIR = "validation/33-formal-promotion/current-mixed-oxv29042"
ANALYZER_REL = (
    "validation/coordination/mixed-work-overrun-20260913/analyze_mixed_work_overrun.py")
ANALYZER_SHA256 = "1162d9fbcaa581fe795dadd2a33427c6f03b69c81aa67111b8b98eda4e691972"
ANALYZER_BYTES = 28503
V2JSON_REL = (
    "validation/coordination/mixed-work-overrun-20260913/mixed-work-overrun-v2.json")
V2JSON_SHA256 = "e10619cc08f4f49cfc8db25b56ab12d48e74672979ee28646b74b119b568c408"
V2JSON_BYTES = 12062
V1JSON_REL = (
    "validation/coordination/mixed-work-overrun-20260913/mixed-work-overrun.json")
V1JSON_SHA256 = "d0a214e34ffbece76cbb2e1291a7e295beec68da6e3bb948942f145042218272"
CROSSCHECK_REL = (
    "validation/coordination/mixed-work-overrun-20260913/main-rate-crosscheck.json")
CROSSCHECK_SHA256 = "461f6bd328a0f7fe339f360dabb71a41850a5bc7081ce60cc2b20396e009febe"
V1DOC_REL = "docs/coordination/mixed-work-overrun-20260913.md"
V1DOC_SHA256 = "a0bd3df069419257314f91a519291aa9d8425ee0bc81cc4ef2d233b0086cd3ec"
V1DOC_BYTES = 4082

RATE_GZ_REL = FIELD_DIR + "/rate.jsonl.gz"
RATE_GZ_SHA256 = "8058ecff7f4730d5fd81a50e8817a8a4190230cc2de3b8170496e46e279c99da"
RATE_GZ_BYTES = 2138673

JOINT_REL = "Simulator/wksim_core/joint.py"
JOINT_SHA256 = "f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50"

RUNNER_REL = "tools/run_joint_flight.py"
RUNNER_LIVE_SHA256 = "c8577093a62e4993c8048a69f4501984b3ee9045b8a73d26fb83aedc73acbb3b"
RUNNER_LIVE_BYTES = 79221
RUNNER_SNAP_REL = FIELD_DIR + "/source__tools__run_joint_flight.py.txt"
RUNNER_SNAP_SHA256 = (
    "65c7a86765a99d2173a62ffafaf56c43243674dd1e3cbbc1150147b4c56d8161")

DS_AUDIT_REL = "validation/coordination/ds-g0-g5-frontier-20260913-01/audit.json"
DS_AUDIT_SHA256 = "7206d768cddb16192f837603ac252c5cd2525fe29aa63777bdd59b226f79d94f"
DS_AUDIT_BYTES = 64330
GATES_PHRASE = (
    "1 ms tick, 4-tick group, no catch-up, <=100 ms lateness, "
    "complete windows, source_unchanged")

# External-only artifacts: must stay absent from the oxv29042 field directory.
FIELD_ABSENT = ("go.json", "experimental-admission.json", "joint-wire.jsonl")

# 7 +/-neighbourhood window groups x 17 consecutive ticks each, as fixed in
# the tracked v2 JSON's diagnostic_cpu_timing.window_ticks_examined.
WINDOW_GROUP_STARTS = (1992, 5496, 47732, 57448, 87636, 119276, 127936)
WINDOW_GROUP_LEN = 17

ENV_KINDS = ("WKSIM_JOINT_CPU_TIMING", "WKSIM_JOINT_RATE_TIMING_PROBE")

# Protected dirty files: recorded worktree SHA256 at audit time. The suite
# only asserts these did not move relative to the ingest note's record.
PROTECTED_BASELINE = {
    "docs/Prometheus.gitmodules.reference":
        "5aa703020961433befcb2f74cd0432e14fbba139db1fd0616b34c6abf0223855",
    "validation/coordination/short-cycle-dispatches.json":
        "06e65cc1cd7d3aa467740f586e92d5e1de00cc973c07db49694c2c6a73862838",
}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args, allow_fail=False, use_real_index=True):
    env = dict(os.environ)
    if use_real_index:
        # "Tracked" semantics in this suite always mean the committed tree /
        # real index, even when the suite runs under a temporary
        # GIT_INDEX_FILE. The real index itself is never inspected or
        # required to stay untracked.
        env.pop("GIT_INDEX_FILE", None)
    proc = subprocess.run(
        ["git", *args], cwd=str(REPO), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode and not allow_fail:
        raise AssertionError(
            "git %s failed: %s" % (" ".join(args), proc.stderr.decode(errors="replace")))
    return proc


def git_out(*args, use_real_index=True):
    return git(*args, allow_fail=False, use_real_index=use_real_index).stdout.decode(
        "utf-8", errors="replace")


def git_bytes(*args, use_real_index=True):
    return git(*args, allow_fail=False, use_real_index=use_real_index).stdout


def head_blob(rel):
    """(sha256, size) of a path's bytes in the HEAD tree."""
    data = git_bytes("show", "HEAD:" + rel)
    return sha256_bytes(data), len(data)


def lines_of(rel, from_head=False):
    if from_head:
        data = git_bytes("show", "HEAD:" + rel)
        return data.decode("utf-8", errors="replace").splitlines()
    return (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()


def line_has(lines, n, token):
    assert 0 < n <= len(lines), "line %d out of range (%d lines)" % (n, len(lines))
    assert token in lines[n - 1], "line %d lacks %r (got %r)" % (n, token, lines[n - 1])


def analyzer_committed_versions():
    """[(commit, content_sha256)] for every commit touching the analyzer."""
    commits = git_out("log", "--all", "--format=%h", "--", ANALYZER_REL).split()
    return [(c, sha256_bytes(git_bytes("show", c + ":" + ANALYZER_REL)))
            for c in commits]


# ---- pure detectors (reused by mutation negatives) ----

def check_bytes(path, want_sha, want_size):
    got_sha = sha256_file(path)
    got_size = path.stat().st_size
    if got_sha != want_sha or got_size != want_size:
        raise AssertionError(
            "%s is %s/%d bytes, expected %s/%d"
            % (path, got_sha[:12], got_size, want_sha[:12], want_size))


def check_zero_diagnostic_counts(v2json):
    """Historical-only boundary: zero diagnostic rows, fixed evidence."""
    dct = v2json.get("diagnostic_cpu_timing") or {}
    counts = dct.get("observed_counts") or {}
    if set(counts) != {"diagnostic_gc_timing", "diagnostic_step_cpu_timing",
                       "diagnostic_native_input_timing"}:
        raise AssertionError("diagnostic kind set drifted: %r" % sorted(counts))
    for kind, n in counts.items():
        if n != 0:
            raise AssertionError("%s is no longer 0 (%r)" % (kind, n))
    if dct.get("observed_total") != 0:
        raise AssertionError("observed_total drifted")
    if dct.get("rows_in_overrun_windows") != []:
        raise AssertionError("overrun-window rows are no longer empty")
    if dct.get("expected_min_step_cpu_records_if_enabled") != 527:
        raise AssertionError("527 counterfactual bound drifted")
    if dct.get("extractable_stages") is not None:
        raise AssertionError("extractable_stages must stay null")


def check_window_groups(ticks):
    if len(ticks) != len(WINDOW_GROUP_STARTS) * WINDOW_GROUP_LEN:
        raise AssertionError("window tick count drifted: %d" % len(ticks))
    for i, start in enumerate(WINDOW_GROUP_STARTS):
        group = ticks[i * WINDOW_GROUP_LEN:(i + 1) * WINDOW_GROUP_LEN]
        if group != list(range(start, start + WINDOW_GROUP_LEN)):
            raise AssertionError("window group %d drifted" % i)


def check_launch_unset_semantics(line4):
    """Line 4 must be an unset control, never an assignment."""
    stripped = line4.strip()
    if not stripped.startswith("unset "):
        raise AssertionError("launch.sh:4 is not an unset control: %r" % stripped[:60])
    for kind in ENV_KINDS:
        if kind not in stripped:
            raise AssertionError("launch.sh:4 lost %r" % kind)
        if kind + "=" in stripped:
            raise AssertionError("launch.sh:4 assigns %r (set, not unset)" % kind)


def check_never_committed(versions):
    """Every committed analyzer version must be the tracked one; the v1-cited
    e5a0db2b... script must never appear in Git history."""
    if not versions:
        raise AssertionError("no committed analyzer version found")
    for commit, sha in versions:
        if sha != ANALYZER_SHA256:
            raise AssertionError(
                "commit %s introduced a second analyzer version %s" % (commit, sha[:12]))
        if sha.startswith("e5a0db2b"):
            raise AssertionError("e5a0db2b... script is in Git after all")


def check_note_boundaries(text):
    lowered = text.lower()
    for required in (
        "b432e2c3bca0ffbcd7b77dd91304d6a5d064e9d6dabd20a8fba1ec99e8836352",
        "5410 bytes", "24ad15729ac393026488f9356f265297a8b4b071c92ab6a501b0fe45bca4893a",
        AUTHORITATIVE_HEAD, ARCH_ANCESTOR,
        # startup-artifact semantics
        "显式 unset 控制", "WKSIM_JOINT_RATE_TIMING_PROBE", "pre-run-identity",
        # external limits
        "仅存于 Linux 接受根", "未随场入库", "20d0634e", "495,410",
        "go.json", "experimental-admission.json", "无法本地复验",
        "无 PASS 依赖任何仅外部（untracked-only）原件",
        # v1/v2 authority + script SHA evolution + runner drift
        "v1（`mixed-work-overrun-20260913.md`）保留为历史证据",
        "权威表述", "e5a0db2b", "d81595fe", "不在 Git 中",
        "1162d9fbcaa581fe795dadd2a33427c6f03b69c81aa67111b8b98eda4e691972",
        "596cb5e6", "65c7a867", "c8577093", "377", "perf-capture",
        # historical-diagnostic-evidence-only boundary
        "历史诊断证据", "不关闭 G6", "不收口 #84", "不触发 #83 重跑",
        "不做验收晋升", "不算全场通过", "不构成任何验收、批准、收口",
        "full_run_acceptance=false", "performance_pass=false", "native_executed=false",
        # gate vocabulary
        "1ms tick", "native barrier", "4-tick", "no catch-up", "100ms",
        "complete windows", "physics", "identity", GATES_PHRASE,
    ):
        if required not in text and required.lower() not in lowered:
            raise AssertionError("ingest note lost boundary phrase: %r" % required)
    for forbidden in (
        "验收通过", "批准通过", "已批准", "已收口", "closure approved",
        "approved by", "performance_pass=true", "full_run_acceptance=true",
        "#83 重跑已执行", "g6 已通过", "full 已通过", "#84 已收口",
        "g6 通过", "full 通过",
    ):
        if forbidden in lowered:
            raise AssertionError("ingest note contains elevation phrase: %r" % forbidden)


class TestByteBinding(unittest.TestCase):
    """Hash/size recomputation: remediated source, note binding, pre-remediation."""

    def test_source_doc_bytes(self):
        path = REPO / SOURCE_REL
        self.assertTrue(path.is_file(), SOURCE_REL + " missing")
        self.assertEqual(sha256_file(path), SOURCE_SHA256)
        self.assertEqual(path.stat().st_size, SOURCE_BYTES)

    def test_note_bytes_and_binding(self):
        path = REPO / NOTE_REL
        self.assertTrue(path.is_file(), NOTE_REL + " missing")
        self.assertEqual(sha256_file(path), NOTE_SHA256)
        self.assertEqual(path.stat().st_size, NOTE_BYTES)
        text = path.read_text(encoding="utf-8")
        self.assertIn(SOURCE_SHA256, text)
        self.assertIn(str(SOURCE_BYTES) + " bytes", text)
        self.assertIn(AUTHORITATIVE_HEAD, text)
        self.assertIn(ARCH_ANCESTOR, text)

    def test_head_tree_still_pre_remediation(self):
        sha, size = head_blob(SOURCE_REL)
        self.assertEqual(sha, HEAD_SOURCE_SHA256)
        self.assertEqual(size, HEAD_SOURCE_BYTES)
        self.assertNotEqual(sha, SOURCE_SHA256,
                            "remediation committed; update the drift record")


class TestTrackedAnchors(unittest.TestCase):
    """Every cited tracked anchor, verified against HEAD-tree bytes."""

    def test_analyzer_head_tree(self):
        sha, size = head_blob(ANALYZER_REL)
        self.assertEqual(sha, ANALYZER_SHA256)
        self.assertEqual(size, ANALYZER_BYTES)

    def test_v2_json_head_tree(self):
        sha, size = head_blob(V2JSON_REL)
        self.assertEqual(sha, V2JSON_SHA256)
        self.assertEqual(size, V2JSON_BYTES)

    def test_v2_json_zero_diagnostic_evidence(self):
        doc = json.loads(git_bytes("show", "HEAD:" + V2JSON_REL).decode("utf-8"))
        self.assertEqual(doc.get("script_sha256"), ANALYZER_SHA256)
        self.assertEqual(doc.get("run_id"), "joint-public-flight-oxv29042")
        self.assertEqual(doc.get("epoch"), "18c96a7e0af9477092aa87e18239c23c")
        check_zero_diagnostic_counts(doc)
        check_window_groups(
            (doc.get("diagnostic_cpu_timing") or {}).get("window_ticks_examined") or [])
        census = doc.get("wire_kind_census") or {}
        self.assertEqual(set(census),
                         {"actuator", "sensor", "step", "barrier", "gps", "connected"})
        align = doc.get("tick_alignment_control") or {}
        self.assertIs(align.get("true_P+1..P+4"), True)
        self.assertIs(align.get("wrong_alignments_rejected"), True)
        # Historical-diagnostic-evidence-only boundary, as recorded in the JSON.
        self.assertIs(doc.get("full_run_acceptance"), False)
        self.assertIs(doc.get("performance_pass"), False)
        self.assertIs(doc.get("native_executed"), False)

    def test_v1_artifacts_preserved(self):
        self.assertEqual(head_blob(V1DOC_REL), (V1DOC_SHA256, V1DOC_BYTES))
        v1 = git_bytes("show", "HEAD:" + V1DOC_REL).decode("utf-8")
        self.assertIn("e5a0db2b", v1)
        self.assertIn("d81595fe", v1)
        for rel, want in ((V1JSON_REL, V1JSON_SHA256),
                          (CROSSCHECK_REL, CROSSCHECK_SHA256)):
            sha, _ = head_blob(rel)
            self.assertEqual(sha, want, rel)

    def test_joint_gate_head_tree(self):
        sha, _ = head_blob(JOINT_REL)
        self.assertEqual(sha, JOINT_SHA256)
        lines = lines_of(JOINT_REL, from_head=True)
        line_has(lines, 54, "self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'")

    def test_rate_bundle_head_tree(self):
        sha, size = head_blob(RATE_GZ_REL)
        self.assertEqual(sha, RATE_GZ_SHA256)
        self.assertEqual(size, RATE_GZ_BYTES)

    def test_runner_drift_boundary(self):
        # Live runner (this checkout's working tree) has drifted from the
        # frozen snapshot; snapshot record() stays at lines 829-831.
        live = REPO / RUNNER_REL
        self.assertEqual(sha256_file(live), RUNNER_LIVE_SHA256)
        self.assertEqual(live.stat().st_size, RUNNER_LIVE_BYTES)
        sha, _ = head_blob(RUNNER_SNAP_REL)
        self.assertEqual(sha, RUNNER_SNAP_SHA256)
        self.assertNotEqual(RUNNER_LIVE_SHA256, RUNNER_SNAP_SHA256)
        snap_lines = lines_of(RUNNER_SNAP_REL)
        line_has(snap_lines, 829, "def record(kind, **data):")
        line_has(snap_lines, 830, "wire.write(json.dumps(dict(kind=kind")

    def test_gates_anchor_head_tree(self):
        sha, size = head_blob(DS_AUDIT_REL)
        self.assertEqual(sha, DS_AUDIT_SHA256)
        self.assertEqual(size, DS_AUDIT_BYTES)
        text = git_bytes("show", "HEAD:" + DS_AUDIT_REL).decode("utf-8")
        self.assertIn(GATES_PHRASE, text)


class TestStartupArtifacts(unittest.TestCase):
    """Env semantics and absent/external limitations for the oxv29042 field."""

    def test_launch_sh_explicit_unset(self):
        lines = lines_of(FIELD_DIR + "/launch.sh", from_head=True)
        check_launch_unset_semantics(lines[3])

    def test_launch_json_children_start_no_match(self):
        for rel in (FIELD_DIR + "/launch.json", FIELD_DIR + "/children-start.json"):
            text = git_bytes("show", "HEAD:" + rel).decode("utf-8", errors="replace")
            self.assertNotIn("WKSIM_JOINT_CPU_TIMING", text, rel)

    def test_pre_run_identity_records_null(self):
        lines = lines_of(FIELD_DIR + "/pre-run-identity.json", from_head=True)
        line_has(lines, 28, '"WKSIM_JOINT_CPU_TIMING": null')

    def test_external_artifacts_absent(self):
        tracked = set(git_out("ls-tree", "-r", "--name-only", "HEAD",
                              "--", FIELD_DIR + "/").splitlines())
        for name in FIELD_ABSENT:
            rel = FIELD_DIR + "/" + name
            self.assertNotIn(rel, tracked, rel + " became tracked; update the boundary")
            self.assertFalse((REPO / rel).is_file(),
                             rel + " appeared on disk; update the boundary")


class TestNeverCommitted(unittest.TestCase):
    """v1-cited e5a0db2b... script SHA was never committed."""

    def test_single_committed_version(self):
        check_never_committed(analyzer_committed_versions())


class TestNoteBoundaries(unittest.TestCase):
    """Note preserves reviewed conclusions; no promotion language."""

    def test_note_boundaries(self):
        check_note_boundaries((REPO / NOTE_REL).read_text(encoding="utf-8"))

    def test_source_preserves_its_own_limits(self):
        text = (REPO / SOURCE_REL).read_text(encoding="utf-8")
        self.assertIn("可复核性与当前限度", text)
        self.assertIn("不算全场通过", text)
        self.assertIn("**不能**", text)


class TestNoElevation(unittest.TestCase):
    """Protected files untouched since the audit baseline."""

    def test_protected_files_untouched(self):
        for rel, want in PROTECTED_BASELINE.items():
            path = REPO / rel
            self.assertTrue(path.is_file(), rel + " missing")
            self.assertEqual(sha256_file(path), want,
                             rel + " moved since the audit baseline")


class TestAncestry(unittest.TestCase):
    """f333316e... and 31e5b65f... are ancestors of HEAD -- never strict
    equality, so the suite keeps working as HEAD advances."""

    def test_arch_ancestor(self):
        self.assertEqual(git("merge-base", "--is-ancestor", ARCH_ANCESTOR,
                             "HEAD", allow_fail=True).returncode, 0)

    def test_authoritative_head_is_ancestor_not_equality(self):
        # Ancestry only: strict equality is deliberately not asserted so the
        # suite keeps passing as HEAD advances beyond 31e5b65f.
        proc = git("merge-base", "--is-ancestor", AUTHORITATIVE_HEAD, "HEAD",
                   allow_fail=True)
        self.assertEqual(proc.returncode, 0)


class TestMutationNegatives(unittest.TestCase):
    """Detectors must fail on mutated inputs (offline, temp copies)."""

    def test_hash_detector_fails_on_mutated_source(self):
        data = (REPO / SOURCE_REL).read_bytes()
        mutated = data.replace(b"flag", b"flax", 1)
        self.assertNotEqual(sha256_bytes(mutated), SOURCE_SHA256)
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "mutated.md"
            fake.write_bytes(mutated)
            with self.assertRaises(AssertionError):
                check_bytes(fake, SOURCE_SHA256, SOURCE_BYTES)

    def test_hash_detector_fails_on_mutated_size(self):
        with self.assertRaises(AssertionError):
            check_bytes(REPO / SOURCE_REL, SOURCE_SHA256, SOURCE_BYTES + 1)

    def test_zero_count_detector_fails_on_nonzero(self):
        doc = json.loads(git_bytes("show", "HEAD:" + V2JSON_REL).decode("utf-8"))
        doc["diagnostic_cpu_timing"]["observed_counts"]["diagnostic_gc_timing"] = 1
        with self.assertRaises(AssertionError):
            check_zero_diagnostic_counts(doc)

    def test_unset_detector_fails_on_assignment_mutation(self):
        # If line 4 ever became an assignment, the unset-control semantics
        # must fail closed.
        with self.assertRaises(AssertionError):
            check_launch_unset_semantics(
                "export WKSIM_JOINT_CPU_TIMING=1 WKSIM_JOINT_RATE_TIMING_PROBE=1")
        with self.assertRaises(AssertionError):
            check_launch_unset_semantics("set WKSIM_JOINT_CPU_TIMING")

    def test_never_committed_detector_fails_on_fake_version(self):
        fake = [("deadbee", "e5a0db2b" + "0" * 56)]
        with self.assertRaises(AssertionError):
            check_never_committed(fake)
        with self.assertRaises(AssertionError):
            check_never_committed([("abc123", "1" * 64)])

    def test_note_detector_fails_on_missing_boundary(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("不做验收晋升"), 1)
        mutated = text.replace("不做验收晋升", "（removed）")
        self.assertNotEqual(mutated, text)
        self.assertNotIn("不做验收晋升", mutated)
        with self.assertRaises(AssertionError):
            check_note_boundaries(mutated)

    def test_note_detector_fails_on_elevation_insert(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        with self.assertRaises(AssertionError):
            check_note_boundaries(text + "\n已收口：G6 通过。\n")


@unittest.skipUnless(
    os.environ.get("WKSIM_MIXED_OVERRUN_TEMP_INDEX") == "1",
    "only meaningful in the temporary GIT_INDEX_FILE run")
class TestTemporaryIndex(unittest.TestCase):
    """Under a private external index, the two new candidates must be staged
    at stage 0 and blob-identical to their working-tree bytes. Extra staged
    paths (future review/manifest files of a final batch) are allowed; the
    real index is not inspected and no requirement is placed on it."""

    def test_candidates_staged_stage0_blob_identical(self):
        listing = git_out("ls-files", "-s", use_real_index=False)
        staged = {}
        for line in listing.splitlines():
            meta, path = line.split("\t", 1)
            mode, objhash, stage = meta.split()
            staged[path] = (mode, objhash, int(stage))
        for rel in CANDIDATE_PATHS:
            self.assertIn(rel, staged, "candidate not staged in temp index: " + rel)
            mode, objhash, stage = staged[rel]
            self.assertEqual(stage, 0, rel + " must be stage-0")
            self.assertEqual(mode, "100644", rel + " must be a regular file")
            want = git_out("hash-object", str(REPO / rel), use_real_index=False).strip()
            self.assertEqual(objhash, want,
                             rel + " staged bytes differ from working tree")
        # All staged entries must still be stage-0 (no conflict stages).
        for path, (_, _, stage) in staged.items():
            self.assertEqual(stage, 0, "non-stage-0 entry: " + path)


if __name__ == "__main__":
    unittest.main()
