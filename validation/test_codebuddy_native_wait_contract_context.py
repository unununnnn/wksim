"""Offline context tests: native-wait contract historical ingest binding (2026-09-14).

Binds two already-tracked native-wait documents as context-only historical
context at writing-time baseline HEAD 31e5b65f5448c5558450d16d0f46da0ef0f0a03c:

- docs/coordination/native-wait-integration-contract-20260913.md
- docs/coordination/claude-native-input-timing.md

and verifies, entirely offline (no network, no native/ROS/SITL/build/MATLAB):

- full SHA256/bytes of both documents and of the independently verified
  source anchors joint_rate.py, joint_rate_probe.py, joint_profile.py,
  joint.py and current-mixed-oxv29042/result.json -- each also byte-checked
  against the HEAD tree (not just the worktree), targeted checks only,
  no tree enumeration;
- line/content anchors in the four source files (final-1ms spin branches
  99-103/114-118, no-catch-up earliest at 93, LATE_LIMIT_NS=100_000_000 at 6,
  window invariant comment 120-123, probe env/identity/terminal anchors
  23-30/33-39/222-224, joint_profile marker loop 274-275 and required-set
  330-334, joint.py:54 cpu_timing opt-in gate) and the result.json identity
  (status=failed, source_unchanged=True, source_sha256 contains BOTH pacer
  files with values equal to the current tracked bytes);
- the contract section 5 historical drift, recorded explicitly: the current
  joint_profile.py required set includes both pacer files and the marker
  list includes perf_switch_capture, so the older exclusion/two-marker claim
  is historical, not current -- both facts are bound side by side;
- external /root probe evidence (probe-03 tick5504/tick2000 timings) is
  treated as non-reproducible: it is only a byte-level text anchor inside
  the bound document, and no PASS anywhere in this suite depends on it;
- boundaries: context-only, no G6/Full closure, no #84 closure, no #83
  rerun; the fixed tick/group/no-catch-up/100ms/full-window/physics/identity
  gates are preserved untouched; the live perf-stream contract
  docs/coordination/perf-stream-contract-20260913.md stays a tracked live
  pointer outside the candidate batch, and the untracked
  docs/coordination/claude-native-wait-next-probe.md is not bound;
- HEAD relations are ancestry checks only (never permanent HEAD equality):
  baseline 31e5b65f and architecture f333316e must be ancestors of whatever
  HEAD is current;
- mutation negatives (hash, size, result identity, note drift anchor, note
  boundary, and line-anchor detectors actually fail on mutated inputs).

The two CANDIDATE_PATHS (this ingest note and this test file) follow a
lifecycle; the suite accepts exactly three valid states and rejects
everything else (partial/mixed presence, nonzero stages, blob mismatch):

- A) pre-admission: neither candidate staged nor in HEAD;
- B) precommit: both staged at stage 0, each index blob byte-identical to
   its working-tree file, and neither yet in HEAD;
- C) postcommit: both in HEAD byte-identical to the working-tree files
   with the real index matching HEAD for them.

The real index is never fingerprinted or compared against a fixed
snapshot: lifecycle detection only classifies the observed state. HEAD may
advance with unrelated reviewed commits at any time; candidate/source bytes
are re-read from disk at test time, never cached at import beyond the run.

Run modes:
- normal: python -m unittest validation.test_codebuddy_native_wait_contract_context
  (or pytest). Any of the three lifecycle states is accepted; ordinary runs
  use read-only git plumbing only and must not mutate Git.
- temporary GIT_INDEX_FILE (repo-external path only): with the two
  candidates staged into a private index and
  WKSIM_NATIVE_WAIT_TEMP_INDEX=1 in the environment, the suite additionally
  asserts that index stages the two candidates at stage 0, blob-identical
  to the working-tree files. Extra independent-review or manifest files
  from later final batches are allowed in that index; the real index is not
  required to stay candidate-free forever (postcommit is a valid real-index
  state).
"""

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Writing-time baseline. Ancestry-checked, never equality-checked: the
# batch must stay lifecycle-safe before staging AND after commit.
BASELINE_HEAD = "31e5b65f5448c5558450d16d0f46da0ef0f0a03c"
ARCH_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"

CONTRACT_REL = "docs/coordination/native-wait-integration-contract-20260913.md"
CONTRACT_SHA256 = "947e759873513ce8d1f11363cb6df9c8c5fc7dc1c868037fbff3b24e90a7b823"
CONTRACT_BYTES = 6132

CLAUDE_REL = "docs/coordination/claude-native-input-timing.md"
CLAUDE_SHA256 = "f15cd0e28396722c23e005f38b2738ca2dfa889975f5f38ae345b7cbacaf0735"
CLAUDE_BYTES = 8714

JOINT_RATE_REL = "Simulator/wksim_runtime/joint_rate.py"
JOINT_RATE_SHA256 = "0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4"
JOINT_RATE_BYTES = 7271

PROBE_REL = "Simulator/wksim_runtime/joint_rate_probe.py"
PROBE_SHA256 = "a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653"
PROBE_BYTES = 7826

PROFILE_REL = "Simulator/wksim_runtime/joint_profile.py"
PROFILE_SHA256 = "90cc868b8050b41e54ef0c38cf20104c58aefb97f07d1448dfd0be1f8633320a"
PROFILE_BYTES = 31113

JOINT_REL = "Simulator/wksim_core/joint.py"
JOINT_SHA256 = "f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50"
JOINT_BYTES = 15808

RESULT_REL = "validation/33-formal-promotion/current-mixed-oxv29042/result.json"
RESULT_SHA256 = "68114715ac4057337fe8174cd708f03ae8343e205335ab61a63ca4ad47e73dbd"
RESULT_BYTES = 130322

NOTE_REL = "docs/coordination/codebuddy-native-wait-contract-ingest-note-20260914.md"
TEST_REL = "validation/test_codebuddy_native_wait_contract_context.py"
CANDIDATE_PATHS = (NOTE_REL, TEST_REL)

VALID_LIFECYCLE_STATES = ("pre-admission", "precommit", "postcommit")

LIVE_CONTRACT_REL = "docs/coordination/perf-stream-contract-20260913.md"
UNTRACKED_PROBE_REL = "docs/coordination/claude-native-wait-next-probe.md"

SOURCE_PINS = (
    (JOINT_RATE_REL, JOINT_RATE_SHA256, JOINT_RATE_BYTES),
    (PROBE_REL, PROBE_SHA256, PROBE_BYTES),
    (PROFILE_REL, PROFILE_SHA256, PROFILE_BYTES),
    (JOINT_REL, JOINT_SHA256, JOINT_BYTES),
    (RESULT_REL, RESULT_SHA256, RESULT_BYTES),
)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args, use_real_index=True, allow_fail=False):
    env = dict(os.environ)
    if use_real_index:
        # "Real index" semantics: even under a temporary GIT_INDEX_FILE,
        # index assertions about the repo use the real index unless the
        # caller explicitly asks for the temporary one.
        env.pop("GIT_INDEX_FILE", None)
    proc = subprocess.run(["git", *args], cwd=str(REPO), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode and not allow_fail:
        raise AssertionError(
            "git %s failed: %s" % (" ".join(args), proc.stderr.decode(errors="replace")))
    return proc


def git_out(*args, **kw):
    return git(*args, **kw).stdout.decode("utf-8", errors="replace")


def head_blob(rel):
    """Blob sha of rel in HEAD, or None if absent."""
    proc = git("ls-tree", "HEAD", "--", rel, allow_fail=True)
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode or not out:
        return None
    meta = out.split()[1]
    return meta if meta != "commit" else out.split()[2]


def worktree_blob(rel):
    return git_out("hash-object", str(REPO / rel)).strip()


def head_bytes(rel):
    return git("show", "HEAD:" + rel).stdout


def snapshot_lines(rel):
    return (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()


def line_has(lines, n, token):
    assert 0 < n <= len(lines), "line %d out of range (%d lines)" % (n, len(lines))
    assert token in lines[n - 1], "line %d lacks %r (got %r)" % (n, token, lines[n - 1])


# ---- pure detectors (reused by mutation negatives) ----

def check_pinned_file(rel, want_sha, want_size):
    path = REPO / rel
    got_sha = sha256_file(path)
    got_size = path.stat().st_size
    if got_sha != want_sha or got_size != want_size:
        raise AssertionError(
            "%s: worktree %s/%d bytes, expected %s/%d"
            % (rel, got_sha[:12], got_size, want_sha[:12], want_size))


def check_result_identity(doc):
    """current-mixed-oxv29042/result.json identity, fail-closed."""
    if doc.get("status") != "failed":
        raise AssertionError("result.json status drifted: %r" % doc.get("status"))
    if doc.get("source_unchanged") is not True:
        raise AssertionError("result.json source_unchanged drifted: %r" % doc.get("source_unchanged"))
    sources = doc.get("source_sha256") or {}
    for name, want in (("Simulator/wksim_runtime/joint_rate.py", JOINT_RATE_SHA256),
                       ("Simulator/wksim_runtime/joint_rate_probe.py", PROBE_SHA256)):
        if sources.get(name) != want:
            raise AssertionError(
                "result.json source_sha256[%s] drifted: %r (want %s)"
                % (name, sources.get(name), want[:12]))


def check_note_boundaries(text):
    for required in (
        CONTRACT_SHA256, CLAUDE_SHA256, "6132", "8714",
        JOINT_RATE_SHA256, PROBE_SHA256, PROFILE_SHA256, JOINT_SHA256, RESULT_SHA256,
        BASELINE_HEAD, ARCH_ANCESTOR,
        "merge-base --is-ancestor", "祖先检查", "不做永久 HEAD 相等断言",
        "context-only",
        # historical drift record (contract section 5)
        "330-334", "perf_switch_capture", "两标记表", "历史性记录", "333", "334",
        # preserved gates
        "不重跑 #83", "不构成 #84 收口", "G6/Full",
        "no-catch-up", "previous_start+period_ns", "LATE_LIMIT_NS",
        "full-window", "physics", "identity", "diagnostic_only",
        # exclusions
        LIVE_CONTRACT_REL, "活指针", UNTRACKED_PROBE_REL, "untracked",
        # non-reproducible external probe evidence
        "/root/wksim-scheduler-probe-35728b1-03", "不可复现",
        # companion test reference
        TEST_REL,
    ):
        if required not in text:
            raise AssertionError("ingest note lost required anchor: %r" % required)
    lowered = text.lower()
    for forbidden in (
        "验收通过", "已批准", "已收口", "closure approved", "approved by",
        "full_acceptance=true", "full_acceptance: true",
        "#83 已重跑", "已重跑 #83",
    ):
        if forbidden in lowered:
            raise AssertionError("ingest note contains elevation phrase: %r" % forbidden)


def detect_lifecycle(index_entries, head_blobs, wt_blobs):
    """Pure lifecycle detector.

    index_entries: rel -> (stage, blob) as seen in the relevant index.
    head_blobs: rel -> blob sha in HEAD (None if absent).
    wt_blobs: rel -> working-tree blob sha.
    Returns one of VALID_LIFECYCLE_STATES; raises on anything else.
    """
    rels = list(wt_blobs)
    staged = {r: index_entries[r] for r in rels if r in index_entries}
    in_head = {r: head_blobs[r] for r in rels if head_blobs.get(r)}
    if not staged and not in_head:
        return "pre-admission"
    if (len(staged) == len(rels) and not in_head
            and all(s == 0 and b == wt_blobs[r] for r, (s, b) in staged.items())):
        return "precommit"
    if (len(in_head) == len(rels)
            and all(head_blobs[r] == wt_blobs[r] for r in rels)
            and all(s == 0 and b == head_blobs[r] for r, (s, b) in staged.items())):
        return "postcommit"
    raise AssertionError(
        "invalid candidate lifecycle state: staged=%r in_head=%r"
        % ({r: staged.get(r) for r in rels}, {r: in_head.get(r) for r in rels}))


def read_index_entries(index_file=None):
    args = ["ls-files", "-s"]
    if index_file is not None:
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = index_file
        proc = subprocess.run(["git", *args], cwd=str(REPO), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode:
            raise AssertionError("ls-files failed on temp index")
        out = proc.stdout.decode("utf-8", errors="replace")
    else:
        out = git_out("ls-files", "-s")
    entries = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            entries[parts[3]] = (int(parts[2]), parts[1])
    return entries


class TestByteBinding(unittest.TestCase):
    """Full hash/size pins, worktree AND HEAD-tree bytes (targeted)."""

    def test_bound_contract_doc(self):
        check_pinned_file(CONTRACT_REL, CONTRACT_SHA256, CONTRACT_BYTES)
        self.assertEqual(sha256_bytes(head_bytes(CONTRACT_REL)), CONTRACT_SHA256)

    def test_bound_claude_doc(self):
        check_pinned_file(CLAUDE_REL, CLAUDE_SHA256, CLAUDE_BYTES)
        self.assertEqual(sha256_bytes(head_bytes(CLAUDE_REL)), CLAUDE_SHA256)

    def test_source_anchor_files(self):
        for rel, want_sha, want_size in SOURCE_PINS:
            check_pinned_file(rel, want_sha, want_size)
            self.assertEqual(sha256_bytes(head_bytes(rel)), want_sha,
                             rel + " HEAD-tree bytes drifted")
            self.assertIn(rel, git_out("ls-files", "--", rel).splitlines(),
                          rel + " must stay tracked")


class TestSourceAnchors(unittest.TestCase):
    """Line/content anchors against the pinned current source bytes."""

    def test_joint_rate_anchors(self):
        lines = snapshot_lines(JOINT_RATE_REL)
        line_has(lines, 6, "LATE_LIMIT_NS=100_000_000")
        line_has(lines, 93, "previous_start+self.period_ns")   # no-catch-up earliest
        line_has(lines, 99, "if remaining<=1_000_000:")        # first final-1ms branch
        line_has(lines, 100, "while now<earliest:")
        line_has(lines, 102, "self.check(max(0,now-ideal))")
        line_has(lines, 114, "if remaining<=1_000_000:")       # branch after health
        line_has(lines, 115, "while now<earliest:")
        line_has(lines, 122, "Final 1ms uses only the monotonic clock")
        line_has(lines, 124, "self.sleep(min((remaining-1_000_000)/1e9,.002))")
        line_has(lines, 126, "actual_start_ns=now")
        line_has(lines, 127, "self.previous_start=now")
        line_has(lines, 128, "self.record('rate_group_start'")
        # ordering: no-catch-up < both spin branches; branches are disjoint
        self.assertLess(93, 99)
        self.assertLess(99, 114)
        self.assertLess(100, 115)

    def test_joint_rate_probe_anchors(self):
        lines = snapshot_lines(PROBE_REL)
        line_has(lines, 23, "def timing_probe_enabled")        # explicit env opt-in
        line_has(lines, 30, "must be unset, 0 or 1")
        line_has(lines, 33, "def timing_probe_identity")
        line_has(lines, 36, '"diagnostic_only"')
        line_has(lines, 221, "terminal = self._last_observed_ns")
        line_has(lines, 222, 'if outcome == "started" and self.group is not None:')
        line_has(lines, 223, 'self.group["actual_start_ns"]')
        line_has(lines, 224, 'self.group["ideal_start_ns"]')

    def test_joint_profile_anchors(self):
        lines = snapshot_lines(PROFILE_REL)
        line_has(lines, 274, "('rate_timing_probe', 'group_work_timing', 'perf_switch_capture')")
        line_has(lines, 275, "if marker in flight:")
        line_has(lines, 330, "required = {")
        line_has(lines, 335, "if not required <= sources.keys():")
        line_has(lines, 338, "'source__'+name.replace('/', '__')+'.txt'")

    def test_joint_anchors(self):
        lines = snapshot_lines(JOINT_REL)
        line_has(lines, 53, "Opt-in diagnostic sampling")
        line_has(lines, 54, "self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'")

    def test_result_json_identity(self):
        doc = json.loads((REPO / RESULT_REL).read_text(encoding="utf-8"))
        check_result_identity(doc)


class TestDocumentAnchors(unittest.TestCase):
    """Content anchors inside the two bound documents."""

    def test_contract_content_anchors(self):
        text = (REPO / CONTRACT_REL).read_text(encoding="utf-8")
        for token in (
            "joint_rate.py:99-103", "100-101", "114-118", "115-116",
            "LATE_LIMIT_NS", "joint_rate_probe.py:23-30",
            "joint_rate_probe.py:33-39", "joint_rate_probe.py:222-224",
            "current-mixed-oxv29042", "source_sha256", "静默回退",
            "previous_start+period_ns", "120-123",
        ):
            self.assertIn(token, text, "contract lost anchor: " + token)

    def test_claude_doc_content_anchors_nonreproducible_root(self):
        text = (REPO / CLAUDE_REL).read_text(encoding="utf-8")
        for token in (
            "tick5504", "5.754904ms", "tick2000", "5.130931ms",
            "/root/wksim-scheduler-probe-35728b1-03", "WKSIM_JOINT_CPU_TIMING",
            "_native_wait", "diagnostic_native_input_timing",
            "analyze_native_input_waits.py", "stub",
        ):
            self.assertIn(token, text, "claude doc lost anchor: " + token)
        # /root evidence is documented as not a real flight acceptance and
        # is NOT reproducible here; this suite only binds it as text.
        self.assertIn("不是真实", text)


class TestHistoricalDrift(unittest.TestCase):
    """Contract section 5 drift: older exclusion/two-marker claim is historical."""

    def test_current_required_set_includes_pacer_files(self):
        lines = snapshot_lines(PROFILE_REL)
        line_has(lines, 333, "'Simulator/wksim_runtime/joint_rate.py',")
        line_has(lines, 334, "'Simulator/wksim_runtime/joint_rate_probe.py'}")

    def test_current_marker_list_includes_perf_switch_capture(self):
        lines = snapshot_lines(PROFILE_REL)
        line_has(lines, 274, "'perf_switch_capture'")

    def test_contract_older_claim_coexists_with_current_bytes(self):
        # The contract text still records the older claim (required set at
        # 328-331 excluding the pacer files; marker rejection cited at
        # 274-275), while the current bytes contradict it. Both facts are
        # bound; the note records the drift explicitly.
        contract = (REPO / CONTRACT_REL).read_text(encoding="utf-8")
        self.assertIn("328-331", contract)
        self.assertIn("274-275", contract)
        note = (REPO / NOTE_REL).read_text(encoding="utf-8")
        check_note_boundaries(note)
        self.assertIn("历史性记录", note)


class TestAncestry(unittest.TestCase):
    """Ancestor checks only -- never permanent HEAD equality."""

    def test_ancestors_of_current_head(self):
        for commit, label in (
            (BASELINE_HEAD, "baseline 31e5b65f"),
            (ARCH_ANCESTOR, "architecture f333316e"),
        ):
            proc = git("merge-base", "--is-ancestor", commit, "HEAD", allow_fail=True)
            self.assertEqual(proc.returncode, 0, label + " must stay an ancestor of HEAD")


class TestExclusions(unittest.TestCase):
    """Live contract and untracked probe doc stay outside the candidate batch."""

    def test_live_contract_stays_outside_batch(self):
        self.assertIn(LIVE_CONTRACT_REL,
                      git_out("ls-files", "--", LIVE_CONTRACT_REL).splitlines(),
                      "live perf-stream contract must remain tracked")
        note = (REPO / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("活指针", note)
        self.assertIn("候选之外", note)
        self.assertNotIn(LIVE_CONTRACT_REL, CANDIDATE_PATHS)

    def test_untracked_probe_doc_not_bound(self):
        # Not pinned by this suite: its bytes appear in no pin table and it
        # is not a candidate. Untracked-ness itself is only recorded in the
        # note at writing time (HEAD may advance; later tracking by an
        # independently reviewed batch is not this batch's business).
        note = (REPO / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn(UNTRACKED_PROBE_REL, note)
        self.assertIn("untracked", note)
        self.assertNotIn(UNTRACKED_PROBE_REL, CANDIDATE_PATHS)
        self.assertNotIn(UNTRACKED_PROBE_REL,
                         tuple(rel for rel, _, _ in SOURCE_PINS) + (CONTRACT_REL, CLAUDE_REL))


class TestLifecycle(unittest.TestCase):
    """Exactly three valid states of the two candidates; rejects the rest."""

    def _live_maps(self):
        entries = read_index_entries()
        index_entries = {rel: entries[rel] for rel in CANDIDATE_PATHS if rel in entries}
        head_blobs = {rel: head_blob(rel) for rel in CANDIDATE_PATHS}
        wt_blobs = {rel: worktree_blob(rel) for rel in CANDIDATE_PATHS}
        return index_entries, head_blobs, wt_blobs

    def test_live_state_is_valid(self):
        state = detect_lifecycle(*self._live_maps())
        self.assertIn(state, VALID_LIFECYCLE_STATES)

    def test_detector_rejects_mixed_state(self):
        wt = {rel: "a" * 40 for rel in CANDIDATE_PATHS}
        head = {rel: None for rel in CANDIDATE_PATHS}
        index = {CANDIDATE_PATHS[0]: (0, wt[CANDIDATE_PATHS[0]])}
        with self.assertRaises(AssertionError):
            detect_lifecycle(index, head, wt)  # one staged, one not

    def test_detector_rejects_nonzero_stage(self):
        wt = {rel: "a" * 40 for rel in CANDIDATE_PATHS}
        head = {rel: None for rel in CANDIDATE_PATHS}
        index = {rel: (2, wt[rel]) for rel in CANDIDATE_PATHS}
        with self.assertRaises(AssertionError):
            detect_lifecycle(index, head, wt)

    def test_detector_rejects_blob_mismatch(self):
        wt = {rel: "a" * 40 for rel in CANDIDATE_PATHS}
        head = {rel: None for rel in CANDIDATE_PATHS}
        index = {rel: (0, "b" * 40) for rel in CANDIDATE_PATHS}
        with self.assertRaises(AssertionError):
            detect_lifecycle(index, head, wt)

    def test_detector_accepts_each_valid_state(self):
        wt = {rel: "a" * 40 for rel in CANDIDATE_PATHS}
        head = {rel: None for rel in CANDIDATE_PATHS}
        self.assertEqual(detect_lifecycle({}, head, wt), "pre-admission")
        index = {rel: (0, wt[rel]) for rel in CANDIDATE_PATHS}
        self.assertEqual(detect_lifecycle(index, head, wt), "precommit")
        head_c = {rel: wt[rel] for rel in CANDIDATE_PATHS}
        self.assertEqual(detect_lifecycle(index, head_c, wt), "postcommit")


class TestMutationNegatives(unittest.TestCase):
    """Detectors must fail on mutated inputs (offline, temp copies)."""

    def test_hash_detector_fails_on_mutated_bytes(self):
        data = (REPO / JOINT_RATE_REL).read_bytes()
        mutated = data.replace(b"LATE_LIMIT_NS=100_000_000", b"LATE_LIMIT_NS=100_000_001", 1)
        self.assertNotEqual(sha256_bytes(mutated), JOINT_RATE_SHA256)
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "mutated.py"
            fake.write_bytes(mutated)
            with self.assertRaises(AssertionError):
                check_pinned_file(str(fake), JOINT_RATE_SHA256, len(data))

    def test_hash_detector_fails_on_mutated_size(self):
        with self.assertRaises(AssertionError):
            check_pinned_file(CONTRACT_REL, CONTRACT_SHA256, CONTRACT_BYTES + 1)

    def test_result_detector_fails_on_mutated_status(self):
        doc = json.loads((REPO / RESULT_REL).read_text(encoding="utf-8"))
        mutated = dict(doc)
        mutated["status"] = "pass"
        with self.assertRaises(AssertionError):
            check_result_identity(mutated)

    def test_result_detector_fails_on_dropped_pacer_entry(self):
        doc = json.loads((REPO / RESULT_REL).read_text(encoding="utf-8"))
        mutated = json.loads(json.dumps(doc))
        del mutated["source_sha256"]["Simulator/wksim_runtime/joint_rate_probe.py"]
        with self.assertRaises(AssertionError):
            check_result_identity(mutated)

    def test_note_detector_fails_on_removed_drift_anchor(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        mutated = text.replace("perf_switch_capture", "removed_marker")
        self.assertNotIn("perf_switch_capture", mutated)
        with self.assertRaises(AssertionError):
            check_note_boundaries(mutated)

    def test_note_detector_fails_on_elevation_injection(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        with self.assertRaises(AssertionError):
            check_note_boundaries(text + "\n验收通过\n")

    def test_line_anchor_detector_fails_on_wrong_line(self):
        lines = snapshot_lines(JOINT_RATE_REL)
        with self.assertRaises(AssertionError):
            line_has(lines, 5, "LATE_LIMIT_NS=100_000_000")  # it is line 6


@unittest.skipUnless(os.environ.get("WKSIM_NATIVE_WAIT_TEMP_INDEX") == "1",
                     "only meaningful in the temporary GIT_INDEX_FILE run")
class TestTemporaryIndex(unittest.TestCase):
    """The temp index must stage the two candidates at stage 0, blob-identical
    to the working tree. Extra independent-review/manifest files from later
    final batches are allowed; the real index is not required to stay
    candidate-free forever."""

    def test_candidates_staged_stage0_blob_identical(self):
        temp_index = os.environ.get("GIT_INDEX_FILE")
        self.assertTrue(temp_index, "GIT_INDEX_FILE must be set for this run")
        entries = read_index_entries(temp_index)
        for rel in CANDIDATE_PATHS:
            self.assertIn(rel, entries, "candidate missing from temp index: " + rel)
            stage, blob = entries[rel]
            self.assertEqual(stage, 0, rel + " must be at stage 0")
            self.assertEqual(blob, worktree_blob(rel),
                             rel + " staged blob differs from working bytes")

    def test_tracked_anchors_present_in_real_index(self):
        entries = read_index_entries()  # real index even under temp GIT_INDEX_FILE
        for rel, _, _ in SOURCE_PINS:
            self.assertIn(rel, entries, "tracked anchor missing from real index: " + rel)
            stage, blob = entries[rel]
            self.assertEqual(stage, 0, rel + " at nonzero stage in the real index")
        for rel in (CONTRACT_REL, CLAUDE_REL):
            self.assertIn(rel, entries, "bound document missing from real index: " + rel)


if __name__ == "__main__":
    unittest.main()
