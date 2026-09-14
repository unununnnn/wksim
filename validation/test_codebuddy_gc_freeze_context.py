"""Offline context tests: CodeBuddy gc-freeze review ingest binding (2026-09-14).

Binds docs/coordination/codebuddy-gc-freeze-review-20260912.md as historical
context. The writing-time historical baseline is HEAD
31e5b65f5448c5558450d16d0f46da0ef0f0a03c, at which the binding was authored;
the suite does NOT assert exact HEAD equality. Instead it requires,
fail-closed, that 31e5b65f and the architecture ancestor
f333316e6efa6b299b4288a9d91fb2bccedfb9d6 remain ancestors of the current
HEAD (git merge-base --is-ancestor, exit 0 required; any nonzero exit --
non-ancestor or invalid object name -- is rejected), so unrelated later
commits do not invalidate the binding. Exact source/blob pins (the review
doc, the ingest note bytes, the pinned historical snapshots, the runner
drift boundary) continue to carry byte authority. All verification is
entirely offline (no network, no native/ROS/SITL/build):

- recomputed SHA256/bytes of the pinned historical source snapshot (preserved
  tracked under validation/coordination/c1-delivery-20260912/) and of the
  writing-time HEAD runner snapshot (byte-authoritative drift boundary);
- existence of every tracked anchor cited by the review and its line anchors
  against the pinned snapshot (not against drifted HEAD);
- the 23/23 boundary: independent rerun record for the pinned historical SHA
  snapshot only -- not current execution, not approval, not #83, not closure;
- D3 supersession by tracked docs/plan/33-rate-measured-candidate-20260912.md
  and later tracked C1 decisions;
- no approval/closure elevation anywhere in the ingest note;
- historical failures preserved;
- ancestors of the current HEAD: writing-time baseline
  31e5b65f5448c5558450d16d0f46da0ef0f0a03c and architecture ancestor
  f333316e6efa6b299b4288a9d91fb2bccedfb9d6 (fail-closed merge-base, with a
  non-ancestor negative);
- mutation negatives (hash, note-byte-binding, and 23/23 boundary detectors
  actually fail on mutated inputs);
- the candidate lifecycle accept/reject detectors (states A/B/C below).

The three CANDIDATE_PATHS follow a lifecycle; the suite accepts exactly
three valid states against the real index/HEAD and rejects everything
else (partial/mixed presence, staged blob mismatch, nonzero stages,
index/HEAD disagreement):

- A) pre-admission: none of the candidates staged or in HEAD;
- B) precommit: all three staged at stage 0, each index blob byte-identical
  to its working-tree file, and none yet in HEAD;
- C) postcommit: all three in HEAD byte-identical to the working-tree
  files and the index matching HEAD for them.

Run modes:
- normal: python -m unittest validation.test_codebuddy_gc_freeze_context (or
  pytest). Any of the three lifecycle states is accepted; ordinary runs use
  read-only git plumbing only and must not mutate Git.
- temporary GIT_INDEX_FILE: with the three candidates force-added to a temp
  index and WKSIM_GC_FREEZE_TEMP_INDEX=1 in the environment, the suite
  additionally asserts the external index stages exactly the three
  candidates byte-identical; the real index must still be in a valid
  lifecycle state (no longer required to be pre-admission only).
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

REVIEW_REL = "docs/coordination/codebuddy-gc-freeze-review-20260912.md"
REVIEW_SHA256 = "64d0e8766274df1ac8cd8d136ec9300b080bc755e0a1694a1272aae3ad406546"
REVIEW_BYTES = 10594

NOTE_REL = "docs/coordination/codebuddy-gc-freeze-ingest-note-20260914.md"
NOTE_SHA256 = "f68c165fc44e07b22f40b82f3df956dca03f13bea1d4bdcb2d35e3c8808fa853"
NOTE_SIZE = 14664

CANDIDATE_PATHS = (
    REVIEW_REL,
    NOTE_REL,
    "validation/test_codebuddy_gc_freeze_context.py",
)

# The exactly-three valid lifecycle states of the candidate set (A/B/C in
# the module docstring); anything else must be rejected.
VALID_LIFECYCLE_STATES = ("pre-admission", "precommit", "postcommit")

# Synthetic blob shas for the offline lifecycle-detector tests; they never
# name real objects (the injected reader maps them to fixture bytes).
FAKE_SHAS = {rel: ("%02x" % idx) * 20 for idx, rel in enumerate(CANDIDATE_PATHS)}
OTHER_FAKE_SHA = "f" * 40

DELIVERY_REL = "validation/coordination/c1-delivery-20260912/delivery.json"

# Pinned historical snapshot: path in review section 0 -> (snapshot rel path, sha256, bytes)
PINNED_SOURCES = {
    "tools/manager_gc_candidate.py": (
        "validation/coordination/c1-delivery-20260912/source__tools__manager_gc_candidate.py.txt",
        "cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66",
        11254,
    ),
    "validation/test_manager_gc_candidate.py": (
        "validation/coordination/c1-delivery-20260912/source__validation__test_manager_gc_candidate.py.txt",
        "637c403c3fe5ea44d097fb89479b10d353d51b2684c4fb52cdcf5d017a6aa6ad",
        15726,
    ),
    "tools/run_joint_flight.py": (
        "validation/coordination/c1-delivery-20260912/source__tools__run_joint_flight.py.txt",
        "fd0b7ee6dfb99be7a2d6f580555c6f9bfcddf721e25f68e97761d7f5670df246",
        78247,
    ),
}

# Current HEAD state of the runner source (drift boundary).
HEAD_RUNNER_SHA256 = "c8577093a62e4993c8048a69f4501984b3ee9045b8a73d26fb83aedc73acbb3b"
HEAD_RUNNER_BYTES = 79221

PLAN_REL = "docs/plan/33-rate-measured-candidate-20260912.md"
COMPARATOR_REL = "tools/compare_joint_gc_diagnostics.py"
COMPARATOR_TEST_REL = "validation/test_compare_joint_gc_diagnostics.py"
JOINT_PROFILE_REL = "Simulator/wksim_runtime/joint_profile.py"
RUNNER_SH_REL = "tools/run-joint-flight.sh"
CONTROL_RESULT_REL = "validation/33-rate-profile/diagnostic-7bdfxkb/result.json"
SELF_CHECK_REL = "validation/coordination/gc-diagnostic-comparator-20260912/self-check-7bdfxkb.json"
SELF_CHECK_SHA256 = "fb698d67faf5f10d8ad416e571531b5ca99a5990648890bb4faf0799f9c4f0a7"
C1_ANALYSIS_REL = "docs/coordination/ds-c1-actual-analysis-20260912.md"
C1_ANALYSIS_JSON_REL = "docs/coordination/ds-c1-actual-analysis-20260912.json"
OMP_CHECK_REL = "docs/coordination/omp-c1-measurement-check-20260912.md"
C1_FIELD_RESULT_REL = "validation/33-rate-profile/diagnostic-c1-ztdsk269/manager-gc-candidate.json"

# Protected dirty files: recorded worktree SHA256 at audit time. The suite
# only asserts these did not move relative to the ingest note's record.
PROTECTED_BASELINE = {
    "docs/Prometheus.gitmodules.reference":
        "5aa703020961433befcb2f74cd0432e14fbba139db1fd0616b34c6abf0223855",
    "validation/coordination/short-cycle-dispatches.json":
        "06e65cc1cd7d3aa467740f586e92d5e1de00cc973c07db49694c2c6a73862838",
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args, allow_fail=False, use_real_index=True):
    env = dict(os.environ)
    if use_real_index:
        # "Tracked" semantics in this suite always mean the real index, even
        # when the suite runs under a temporary GIT_INDEX_FILE.
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


def tracked_files():
    return set(git_out("ls-files").splitlines())


def check_ancestor(ancestor, descendant="HEAD"):
    """Fail-closed ancestry: exit 0 required; a non-ancestor or invalid
    object name (any nonzero exit) must reject."""
    proc = git("merge-base", "--is-ancestor", ancestor, descendant,
               allow_fail=True)
    if proc.returncode != 0:
        raise AssertionError(
            "git merge-base --is-ancestor %s %s rejected (exit %d): %s"
            % (ancestor, descendant, proc.returncode,
               proc.stderr.decode(errors="replace")))


def check_binding(rel, want_sha, want_size):
    """Byte authority: the file must hash to want_sha at exactly want_size."""
    path = REPO / rel
    if not path.is_file():
        raise AssertionError(rel + " missing")
    got_sha = sha256_file(path)
    got_size = path.stat().st_size
    if got_sha != want_sha or got_size != want_size:
        raise AssertionError(
            "%s is %s/%d bytes, expected %s/%d"
            % (rel, got_sha[:12], got_size, want_sha[:12], want_size))


def snapshot_lines(rel):
    return (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()


def line_has(lines, n, token):
    assert 0 < n <= len(lines), "line %d out of range (%d lines)" % (n, len(lines))
    assert token in lines[n - 1], "line %d lacks %r (got %r)" % (n, token, lines[n - 1])


# ---- pure detectors (reused by mutation negatives) ----

def check_pinned_hashes(mapping):
    """mapping: logical path -> (sha256, bytes). Raises on any mismatch."""
    for logical, (want_sha, want_size) in mapping.items():
        snap_rel = PINNED_SOURCES[logical][0]
        path = REPO / snap_rel
        got_sha = sha256_file(path)
        got_size = path.stat().st_size
        if got_sha != want_sha or got_size != want_size:
            raise AssertionError(
                "%s: snapshot %s is %s/%d bytes, expected %s/%d"
                % (logical, snap_rel, got_sha[:12], got_size, want_sha[:12], want_size))


def check_delivery_boundary(delivery):
    """23/23 is only a historical rerun record: fail-closed detector."""
    if delivery.get("classification") != "candidate_source_delivery_not_flight":
        raise AssertionError("classification must keep the delivery-not-flight boundary")
    if delivery.get("native_started") is not False:
        raise AssertionError("native_started must stay false for a source delivery receipt")
    delegated = delivery.get("delegated_validation") or {}
    if delegated.get("manager_gc_candidate") != "23 passed":
        raise AssertionError(
            "23/23 record drifted: %r" % (delegated.get("manager_gc_candidate"),))
    for logical, sha in (delivery.get("source_sha256") or {}).items():
        if logical in PINNED_SOURCES and sha != PINNED_SOURCES[logical][1]:
            raise AssertionError("delivery.json SHA for %s drifted from pin" % logical)


def check_note_boundaries(text):
    lowered = text.lower()
    for negation in (
        "不是当前执行", "不是批准", "不是 #83 证据", "不是收口",
        "不构成任何验收、批准、收口", "只做", "historical context only",
    ):
        if negation not in text and negation.lower() not in lowered:
            raise AssertionError("ingest note lost boundary phrase: %r" % negation)
    for forbidden in (
        "验收通过", "批准通过", "已批准", "已收口", "closure approved",
        "approved by", "performance_pass=true", "performance_pass: true",
        "c1 通过", "c1已通过", "#83 通过",
    ):
        if forbidden in lowered:
            raise AssertionError("ingest note contains elevation phrase: %r" % forbidden)


# ---- candidate lifecycle detector (read-only; readers injectable) ----

def git_lifecycle_readers(use_real_index=True):
    """Read-only readers over real git plumbing: HEAD blob sha per path,
    index stage->blob-sha map per path, blob bytes, working bytes."""

    def head_blob_sha(rel):
        proc = git("ls-tree", "HEAD", "--", rel, allow_fail=True,
                   use_real_index=use_real_index)
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode or not out:
            return None
        meta = out.split("\t", 1)[0].split()
        return meta[2] if len(meta) >= 3 else None

    def index_stages(rel):
        stages = {}
        for line in git_out("ls-files", "-s", "--", rel,
                            use_real_index=use_real_index).splitlines():
            meta = line.partition("\t")[0].split()
            if len(meta) >= 3:
                stages[int(meta[2])] = meta[1]
        return stages

    def blob_bytes(sha):
        return git("cat-file", "blob", sha, use_real_index=use_real_index).stdout

    def working_bytes(rel):
        path = REPO / rel
        if not path.is_file():
            return None
        return path.read_bytes()

    return head_blob_sha, index_stages, blob_bytes, working_bytes


def classify_candidate_lifecycle(paths=CANDIDATE_PATHS, readers=None):
    """Read-only lifecycle detector for the candidate set (states A/B/C).

    Accepts exactly:
    A pre-admission  -- none of the candidates in HEAD or the index;
    B precommit      -- all absent from HEAD, all stage-0 in the index,
                        each index blob byte-identical to working bytes;
    C postcommit     -- all in HEAD and index, HEAD=index=working bytes.
    Returns the accepted state name; raises AssertionError for anything
    else (partial/mixed presence, nonzero index stages, blob mismatch,
    HEAD-vs-index disagreement). Git inspection is injected via the four
    readers so offline tests can drive synthetic states (FAKE_SHAS)
    without mutating Git.
    """
    if readers is None:
        readers = git_lifecycle_readers()
    head_blob_sha, index_stages, blob_bytes, working_bytes = readers

    observed = {}
    for rel in paths:
        head_sha = head_blob_sha(rel)
        stages = index_stages(rel)
        if head_sha is None and not stages:
            observed[rel] = "absent"  # not in HEAD, not in the index
            continue
        if set(stages) != {0}:
            raise AssertionError(
                "%s: index stages %r, expected exactly stage 0"
                % (rel, sorted(stages)))
        work = working_bytes(rel)
        if work is None:
            raise AssertionError(rel + ": candidate missing from working tree")
        if blob_bytes(stages[0]) != work:
            raise AssertionError(
                "%s: index blob %s != working bytes" % (rel, stages[0]))
        if head_sha is None:
            observed[rel] = "staged"
        else:
            if blob_bytes(head_sha) != work:
                raise AssertionError(
                    "%s: HEAD blob %s != working bytes" % (rel, head_sha))
            observed[rel] = "committed"

    kinds = set(observed.values())
    if kinds <= {"absent"}:
        return VALID_LIFECYCLE_STATES[0]   # A: pre-admission
    if kinds == {"staged"}:
        return VALID_LIFECYCLE_STATES[1]   # B: precommit
    if kinds == {"committed"}:
        return VALID_LIFECYCLE_STATES[2]   # C: postcommit
    raise AssertionError(
        "candidate set is in a partial/mixed lifecycle state: %r" % observed)


class TestByteBinding(unittest.TestCase):
    """Hash/size recomputation: review doc, note binding, pinned snapshot."""

    def test_review_doc_bytes(self):
        path = REPO / REVIEW_REL
        self.assertTrue(path.is_file(), REVIEW_REL + " missing")
        self.assertEqual(sha256_file(path), REVIEW_SHA256)
        self.assertEqual(path.stat().st_size, REVIEW_BYTES)

    def test_note_binds_review_and_writing_baseline(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn(REVIEW_SHA256, text)
        self.assertIn(str(REVIEW_BYTES) + " bytes", text)
        self.assertIn(AUTHORITATIVE_HEAD, text)
        self.assertIn(ARCH_ANCESTOR, text)

    def test_note_bytes(self):
        check_binding(NOTE_REL, NOTE_SHA256, NOTE_SIZE)

    def test_pinned_snapshot_hashes_and_sizes(self):
        check_pinned_hashes(
            {logical: (sha, size) for logical, (_, sha, size) in PINNED_SOURCES.items()})

    def test_head_drift_boundary(self):
        runner = REPO / "tools/run_joint_flight.py"
        self.assertEqual(sha256_file(runner), HEAD_RUNNER_SHA256)
        self.assertEqual(runner.stat().st_size, HEAD_RUNNER_BYTES)
        self.assertNotEqual(HEAD_RUNNER_SHA256, PINNED_SOURCES["tools/run_joint_flight.py"][1])
        for logical in ("tools/manager_gc_candidate.py",
                        "validation/test_manager_gc_candidate.py"):
            self.assertFalse((REPO / logical).is_file(),
                             logical + " unexpectedly exists at HEAD")
            head_has = git("cat-file", "-e", "HEAD:" + logical, allow_fail=True)
            self.assertNotEqual(head_has.returncode, 0,
                                logical + " unexpectedly tracked at HEAD")


class TestAnchors(unittest.TestCase):
    """Tracked anchor existence + line anchors against the pinned snapshot."""

    def test_tracked_anchors_exist(self):
        tracked = tracked_files()
        for rel in (PLAN_REL, COMPARATOR_REL, COMPARATOR_TEST_REL,
                    JOINT_PROFILE_REL, RUNNER_SH_REL, CONTROL_RESULT_REL,
                    DELIVERY_REL, C1_ANALYSIS_REL, C1_ANALYSIS_JSON_REL,
                    OMP_CHECK_REL, C1_FIELD_RESULT_REL,
                    "validation/33-rate-profile/diagnostic-triple-20260912/7bdfxkb.json",
                    "validation/33-rate-profile/diagnostic-triple-20260912/ztdsk269.json",
                    "validation/33-rate-profile/diagnostic-triple-20260912/vwen35gc.json",
                    "validation/coordination/c1-delivery-20260912/"
                    "source__tools__manager_gc_candidate.py.txt"):
            self.assertIn(rel, tracked, "anchor not tracked: " + rel)

    def test_selfcheck_untracked_on_disk(self):
        path = REPO / SELF_CHECK_REL
        self.assertTrue(path.is_file(), SELF_CHECK_REL + " missing on disk")
        self.assertNotIn(SELF_CHECK_REL, tracked_files(),
                         SELF_CHECK_REL + " became tracked; reclassify the boundary")
        self.assertEqual(sha256_file(path), SELF_CHECK_SHA256)
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc.get("status"), "unavailable")
        self.assertEqual(doc.get("reasons"), ["candidate:gc_freeze_contract:unavailable"])

    def test_candidate_files_exist_and_lifecycle_valid(self):
        # Every candidate exists on disk and the real index/HEAD hold the
        # candidate set in exactly one of the accepted lifecycle states
        # (A pre-admission / B precommit / C postcommit); anything partial,
        # mixed, stage-nonzero, or byte-mismatched is rejected by the
        # detector itself.
        for rel in CANDIDATE_PATHS:
            self.assertTrue((REPO / rel).is_file(), rel + " missing")
        self.assertIn(classify_candidate_lifecycle(), VALID_LIFECYCLE_STATES)

    def test_plan_doc_contract_amended(self):
        text = git_out("show", "HEAD:" + PLAN_REL)
        self.assertIn("cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66", text)
        self.assertIn("fd0b7ee6", text)  # abbreviated pin in plan text
        self.assertIn("**不**要求主会话手造 `gc-freeze.json`", text)
        self.assertIn("manager-gc-candidate.json", text)
        # Tracked current-conclusion block binds the later C1 decisions.
        self.assertIn("当前结论（2026-09-14）", text)
        self.assertIn("#83 不重跑", text)
        self.assertIn("C1 仍是假说", text)

    def test_head_comparator_has_no_gc_freeze_contract(self):
        lines = snapshot_lines(COMPARATOR_REL)
        text = "\n".join(lines)
        self.assertNotIn("gc-freeze", text)
        self.assertNotIn("freeze_calls", text)
        self.assertNotIn("wksim.joint-gc-freeze.v1", text)
        line_has(lines, 333, "def resolve_inputs")
        # The review's pre-commit cites must NOT be treated as HEAD anchors.
        self.assertFalse("def resolve_inputs" in lines[72], "resolve_inputs moved off :333?")

    def test_runner_sh_passthrough_line22(self):
        lines = snapshot_lines(RUNNER_SH_REL)
        line_has(lines, 22, "run_joint_flight.py")

    def test_joint_profile_head_probe_rejection(self):
        lines = snapshot_lines(JOINT_PROFILE_REL)
        line_has(lines, 274, "for marker in")
        line_has(lines, 276, "Formal mixed/PV evidence cannot include")
        # The review's 219-220 cite is stale at HEAD: must not silently match.
        self.assertFalse(
            any("Formal mixed/PV evidence" in l for l in lines[218:220]),
            "rejection moved back onto 219-220; update the drift record")

    def test_control_field_identity(self):
        doc = json.loads((REPO / CONTROL_RESULT_REL).read_text(encoding="utf-8"))
        self.assertEqual(doc.get("run_id"), "joint-public-flight-7bdfxkb_")
        self.assertEqual(doc.get("scene_epoch"),
                         "85df8c49b8f64de8ba794cff149696d1")
        self.assertIs(doc.get("source_unchanged"), True)
        self.assertEqual(doc.get("cleanup_errors"), [])
        self.assertEqual(len(doc.get("source_sha256") or {}), 38)

    def test_snapshot_line_anchors_runner(self):
        lines = snapshot_lines(PINNED_SOURCES["tools/run_joint_flight.py"][0])
        line_has(lines, 466, "try:")
        line_has(lines, 791, "ExitStack")
        line_has(lines, 888, "initialized.json")
        line_has(lines, 905, "Candidate startup advanced the model clock")
        line_has(lines, 910, "manager_gc.prepare")
        line_has(lines, 911, "physics.connect()")
        line_has(lines, 1041, "except PauseProbeComplete")
        line_has(lines, 1043, "except BaseException")
        line_has(lines, 1048, "finally:")
        line_has(lines, 1050, "cleanup_children")
        line_has(lines, 1061, "finally:")
        line_has(lines, 1066, "manager_gc.restore()")
        line_has(lines, 1071, "manager-gc-candidate.json")
        line_has(lines, 1187, "--manager-gc-freeze is only allowed for PV/MIXED")
        line_has(lines, 1195, "no alternate probes")
        # review's stale cites must not have become true again unnoticed
        self.assertNotIn("manager_gc.prepare", lines[905])
        self.assertNotIn("no alternate probes", lines[1096])

    def test_snapshot_line_anchors_manager_candidate(self):
        lines = snapshot_lines(PINNED_SOURCES["tools/manager_gc_candidate.py"][0])
        line_has(lines, 151, "def _revalidate")
        line_has(lines, 183, "return observed")
        line_has(lines, 196, "self._revalidate()")
        self.assertIn("self._we_froze = True", "\n".join(lines[199:205]))
        self.assertIn("restore_noop_not_owner", "\n".join(lines[222:228]))
        self.assertIn("def report", "\n".join(lines[247:273]))

    def test_c1_candidate_field_matches_pin(self):
        doc = json.loads((REPO / C1_FIELD_RESULT_REL).read_text(encoding="utf-8"))
        self.assertEqual(doc.get("source_sha256"),
                         PINNED_SOURCES["tools/manager_gc_candidate.py"][1])
        self.assertIs(doc.get("performance_pass"), False)
        self.assertIs(doc.get("restored"), True)


class TestBoundary23(unittest.TestCase):
    """23/23: independent rerun record for the pinned snapshot only."""

    def test_delivery_json_boundary(self):
        delivery = json.loads((REPO / DELIVERY_REL).read_text(encoding="utf-8"))
        check_delivery_boundary(delivery)

    def test_review_records_23_passed(self):
        text = (REPO / REVIEW_REL).read_text(encoding="utf-8")
        self.assertIn("23 passed", text)

    def test_note_states_23_23_boundary(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        for phrase in ("只是对 §2 钉住的历史 SHA 快照", "独立复跑记录",
                       "不是当前执行", "不是批准", "不是 #83 证据", "不是收口"):
            self.assertIn(phrase, text, "note lost 23/23 boundary phrase: " + phrase)
        self.assertIn("candidate_source_delivery_not_flight", text)
        self.assertIn("native_started", text)


class TestD3Supersession(unittest.TestCase):
    """D3's premise (gc-freeze.json contract) was superseded by tracked anchors."""

    def test_review_states_d3_as_written(self):
        text = (REPO / REVIEW_REL).read_text(encoding="utf-8")
        self.assertIn("新缺陷 D3", text)
        self.assertIn("gc-freeze.json", text)
        self.assertIn("wksim.joint-gc-freeze.v1", text)

    def test_note_states_supersession(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("D3 折叠", text)
        self.assertIn("已被 tracked 权威取代", text)
        self.assertIn("33-rate-measured-candidate-20260912.md", text)

    def test_tracked_c1_decision_docs(self):
        text = (REPO / C1_ANALYSIS_REL).read_text(encoding="utf-8")
        self.assertIn("RateUnmet", text)
        self.assertIn("不可复现", text)
        self.assertIn("不建议放宽任何门限", text)
        omp = (REPO / OMP_CHECK_REL).read_text(encoding="utf-8")
        self.assertTrue(omp.strip())
        analysis = json.loads((REPO / C1_ANALYSIS_JSON_REL).read_text(encoding="utf-8"))
        self.assertTrue(isinstance(analysis, dict))

    def test_head_comparator_consumes_manager_gc_candidate(self):
        text = git_out("show", "HEAD:" + COMPARATOR_REL)
        self.assertIn("manager_gc_candidate", text)
        self.assertNotIn("gc-freeze.json", text)


class TestNoElevation(unittest.TestCase):
    """No approval/closure elevation; historical failures preserved."""

    def test_note_boundaries(self):
        check_note_boundaries((REPO / NOTE_REL).read_text(encoding="utf-8"))

    def test_review_preserves_failures(self):
        text = (REPO / REVIEW_REL).read_text(encoding="utf-8")
        self.assertIn("未通过 / 未证", text)
        self.assertIn("candidate:gc_freeze_contract:unavailable", text)
        self.assertIn("`unavailable`/`rejected`", text)

    def test_note_preserves_historical_failures(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("历史失败记录保全", text)
        self.assertIn("未修", text)
        self.assertIn("candidate:gc_freeze_contract:unavailable", text)
        self.assertIn("RateUnmet", text)
        self.assertIn("native_started=false", text)

    def test_protected_files_untouched(self):
        for rel, want in PROTECTED_BASELINE.items():
            path = REPO / rel
            self.assertTrue(path.is_file(), rel + " missing")
            self.assertEqual(sha256_file(path), want,
                             rel + " moved since the audit baseline")


class TestArchitectureAncestor(unittest.TestCase):
    """31e5b65f is the writing-time historical baseline, not an exact-HEAD
    equality pin: it and the architecture ancestor must remain ancestors of
    the current HEAD, checked fail-closed."""

    def test_baseline_and_arch_ancestor_are_ancestors(self):
        check_ancestor(AUTHORITATIVE_HEAD)
        check_ancestor(ARCH_ANCESTOR)

    def test_non_ancestor_rejected(self):
        # a fabricated 40-hex name names no object: fail-closed rejection
        with self.assertRaises(AssertionError):
            check_ancestor(OTHER_FAKE_SHA)

    def test_genuine_non_ancestor_rejected(self):
        # A genuine non-ancestor (valid commit objects, merge-base
        # --is-ancestor exit 1) must also be rejected, distinct from the
        # invalid-object exit-128 path above; a fail-open regression that
        # only rejects exit 128 would be caught here. Built offline in a
        # repo-external temporary git repo holding two unrelated root
        # commits (no dependency on any local object; the real repo is
        # never mutated; check_ancestor's fixed cwd is bypassed by
        # temporarily rebinding the module-level git helper).
        env = dict(os.environ)
        env.pop("GIT_INDEX_FILE", None)
        env.update({
            "GIT_AUTHOR_NAME": "g", "GIT_AUTHOR_EMAIL": "g@example.invalid",
            "GIT_COMMITTER_NAME": "g", "GIT_COMMITTER_EMAIL": "g@example.invalid",
            "GIT_AUTHOR_DATE": "2026-09-14T00:00:00 +0000",
            "GIT_COMMITTER_DATE": "2026-09-14T00:00:00 +0000",
        })
        with tempfile.TemporaryDirectory() as td:
            def tgit(*args, allow_fail=False, **kw):
                proc = subprocess.run(
                    ["git", *args], cwd=td, env=env, **kw,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if proc.returncode and not allow_fail:
                    raise AssertionError(
                        "git %s failed: %s"
                        % (" ".join(args), proc.stderr.decode(errors="replace")))
                return proc

            tgit("init", "-q")
            tree = tgit("mktree", input=b"").stdout.decode().strip()
            root_a, root_b = (
                tgit("commit-tree", tree, input=msg).stdout.decode().strip()
                for msg in (b"root a", b"root b"))
            # prove the negative is genuine: valid objects, mutual exit 1
            raw = tgit("merge-base", "--is-ancestor", root_b, root_a,
                       allow_fail=True)
            self.assertEqual(
                raw.returncode, 1,
                "genuine non-ancestor must exit 1, got %d: %s"
                % (raw.returncode, raw.stderr.decode(errors="replace")))
            # the fabricated name stays a distinct failure mode: exit 128
            bad = tgit("merge-base", "--is-ancestor", OTHER_FAKE_SHA, root_a,
                       allow_fail=True)
            self.assertEqual(
                bad.returncode, 128,
                "invalid object name must exit 128, got %d" % bad.returncode)
            # drive check_ancestor over the temporary repo: the self-ancestor
            # control must pass (exit 0), then the genuine non-ancestor
            # (exit 1) must reject.
            original_git = globals()["git"]
            globals()["git"] = lambda *args, allow_fail=False, use_real_index=True: \
                tgit(*args, allow_fail=allow_fail)
            try:
                check_ancestor(root_a, descendant=root_a)
                with self.assertRaises(AssertionError):
                    check_ancestor(root_b, descendant=root_a)
            finally:
                globals()["git"] = original_git


class TestMutationNegatives(unittest.TestCase):
    """Detectors must fail on mutated inputs (offline, temp copies)."""

    def test_hash_detector_fails_on_mutated_snapshot(self):
        src = REPO / PINNED_SOURCES["tools/manager_gc_candidate.py"][0]
        data = src.read_bytes()
        mutated = data.replace(b"_revalidate", b"_revalidatX", 1)
        self.assertNotEqual(hashlib.sha256(mutated).hexdigest(),
                            PINNED_SOURCES["tools/manager_gc_candidate.py"][1])
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "mutated.txt"
            fake.write_bytes(mutated)
            logical = "tools/manager_gc_candidate.py"
            saved = PINNED_SOURCES[logical]
            try:
                PINNED_SOURCES[logical] = (str(fake), saved[1], saved[2])
                with self.assertRaises(AssertionError):
                    check_pinned_hashes({logical: (saved[1], saved[2])})
            finally:
                PINNED_SOURCES[logical] = saved

    def test_hash_detector_fails_on_mutated_size(self):
        with self.assertRaises(AssertionError):
            check_pinned_hashes({
                "tools/manager_gc_candidate.py": (
                    PINNED_SOURCES["tools/manager_gc_candidate.py"][1],
                    PINNED_SOURCES["tools/manager_gc_candidate.py"][2] + 1)})

    def test_binding_detector_fails_on_mutated_note_size(self):
        with self.assertRaises(AssertionError):
            check_binding(NOTE_REL, NOTE_SHA256, NOTE_SIZE + 1)

    def test_boundary_detector_fails_on_mutated_count(self):
        delivery = json.loads((REPO / DELIVERY_REL).read_text(encoding="utf-8"))
        delivery["delegated_validation"]["manager_gc_candidate"] = "24 passed"
        with self.assertRaises(AssertionError):
            check_delivery_boundary(delivery)

    def test_boundary_detector_fails_on_native_started(self):
        delivery = json.loads((REPO / DELIVERY_REL).read_text(encoding="utf-8"))
        delivery["native_started"] = True
        with self.assertRaises(AssertionError):
            check_delivery_boundary(delivery)

    def test_note_detector_fails_on_elevation_mutation(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        mutated = text.replace("不构成任何验收、批准、收口", "构成验收、批准、收口", 1)
        self.assertNotEqual(mutated, text)
        with self.assertRaises(AssertionError):
            check_note_boundaries(mutated)


class TestLifecycleDetectorsOffline(unittest.TestCase):
    """Pure offline A/B/C acceptance and rejection with injected readers.

    FAKE_SHAS never name real objects; the blob reader maps them to
    fixture bytes. Git is never mutated here.
    """

    def setUp(self):
        self.work = {rel: b"working bytes of " + rel.encode()
                     for rel in CANDIDATE_PATHS}
        self.blobs = {OTHER_FAKE_SHA: b"unrelated blob bytes"}

    def readers(self, head=None, index=None, work=None):
        head = head or {}
        index = index or {}
        work = self.work if work is None else work
        return (
            lambda rel: head.get(rel),
            lambda rel: index.get(rel, {}),
            lambda sha: self.blobs[sha],
            lambda rel: work.get(rel),
        )

    def classify(self, **kw):
        return classify_candidate_lifecycle(readers=self.readers(**kw))

    def map_fake_blobs(self):
        for rel in CANDIDATE_PATHS:
            self.blobs[FAKE_SHAS[rel]] = self.work[rel]

    def test_accepts_a_pre_admission(self):
        self.assertEqual(self.classify(), VALID_LIFECYCLE_STATES[0])

    def test_accepts_b_precommit(self):
        self.map_fake_blobs()
        index = {rel: {0: FAKE_SHAS[rel]} for rel in CANDIDATE_PATHS}
        self.assertEqual(self.classify(index=index), VALID_LIFECYCLE_STATES[1])

    def test_accepts_c_postcommit(self):
        self.map_fake_blobs()
        index = {rel: {0: FAKE_SHAS[rel]} for rel in CANDIDATE_PATHS}
        head = {rel: FAKE_SHAS[rel] for rel in CANDIDATE_PATHS}
        self.assertEqual(self.classify(head=head, index=index),
                         VALID_LIFECYCLE_STATES[2])

    def test_rejects_partial_mixed_presence(self):
        # only one candidate staged, the rest absent: neither A nor B
        self.map_fake_blobs()
        only = CANDIDATE_PATHS[1]
        index = {only: {0: FAKE_SHAS[only]}}
        with self.assertRaises(AssertionError):
            self.classify(index=index)

    def test_rejects_nonzero_stage(self):
        self.map_fake_blobs()
        index = {rel: {1: FAKE_SHAS[rel]} for rel in CANDIDATE_PATHS}
        with self.assertRaises(AssertionError):
            self.classify(index=index)

    def test_rejects_stage0_plus_higher_stage(self):
        self.map_fake_blobs()
        first = CANDIDATE_PATHS[0]
        index = {rel: {0: FAKE_SHAS[rel]} for rel in CANDIDATE_PATHS}
        index[first] = {0: FAKE_SHAS[first], 2: OTHER_FAKE_SHA}
        with self.assertRaises(AssertionError):
            self.classify(index=index)

    def test_rejects_index_blob_mismatch(self):
        index = {rel: {0: OTHER_FAKE_SHA} for rel in CANDIDATE_PATHS}
        with self.assertRaises(AssertionError):
            self.classify(index=index)

    def test_rejects_head_index_disagreement(self):
        # all three in HEAD but absent from the index: not A, not C
        self.map_fake_blobs()
        head = {rel: FAKE_SHAS[rel] for rel in CANDIDATE_PATHS}
        with self.assertRaises(AssertionError):
            self.classify(head=head)

    def test_rejects_head_blob_mismatch(self):
        self.map_fake_blobs()
        index = {rel: {0: FAKE_SHAS[rel]} for rel in CANDIDATE_PATHS}
        head = {rel: OTHER_FAKE_SHA for rel in CANDIDATE_PATHS}
        with self.assertRaises(AssertionError):
            self.classify(head=head, index=index)

    def test_rejects_missing_working_file(self):
        self.map_fake_blobs()
        index = {rel: {0: FAKE_SHAS[rel]} for rel in CANDIDATE_PATHS}
        work = dict(self.work)
        work[CANDIDATE_PATHS[0]] = None
        with self.assertRaises(AssertionError):
            self.classify(index=index, work=work)


@unittest.skipUnless(os.environ.get("WKSIM_GC_FREEZE_TEMP_INDEX") == "1",
                     "only meaningful in the temporary GIT_INDEX_FILE run")
class TestTemporaryIndex(unittest.TestCase):
    """The temp index must contain exactly the three force-added candidates
    (stage 0, blobs byte-identical to the working tree), and the real
    index/HEAD must still sit in a valid lifecycle state."""

    def test_candidates_staged_exactly(self):
        staged = set(git_out("ls-files", use_real_index=False).splitlines())
        # equality, not subset: the temp index must hold exactly the three
        # candidates and nothing else
        self.assertEqual(
            staged, set(CANDIDATE_PATHS),
            "temp index must hold exactly the three candidates, got: %r"
            % sorted(staged))
        # each candidate must sit at stage 0 with a blob byte-identical
        # to its working-tree file
        _, index_stages, blob_bytes, working_bytes = git_lifecycle_readers(
            use_real_index=False)
        for rel in CANDIDATE_PATHS:
            stages = index_stages(rel)
            self.assertEqual(set(stages), {0},
                             rel + " not staged exactly once at stage 0")
            self.assertEqual(blob_bytes(stages[0]), working_bytes(rel),
                             rel + " temp-index blob differs from working bytes")

    def test_real_index_unchanged(self):
        # the real index/HEAD must still be in one of the accepted
        # lifecycle states (not required to be pre-admission only)
        self.assertIn(classify_candidate_lifecycle(), VALID_LIFECYCLE_STATES)
        real = set(git_out("ls-files").splitlines())
        # real index must still carry the tracked anchors we verified
        for rel in (PLAN_REL, DELIVERY_REL, COMPARATOR_REL):
            self.assertIn(rel, real)


if __name__ == "__main__":
    unittest.main()
