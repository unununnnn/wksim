"""Offline context tests: OMP perf-counter historical ingest binding (2026-09-14).

Binds two already-tracked performance-counter reviews as superseded
historical context at writing-time baseline HEAD 31e5b65f5448c5558450d16d0f46da0ef0f0a03c:

- docs/coordination/omp-perf-counter-integration-review-20260913.md
- docs/coordination/omp-perf-lost-counter-review-20260913.md

and verifies, entirely offline (no network, no native/ROS/SITL/build):

- full SHA256/bytes of both reviews, of the recorder/header/consumer/probe
  snapshots across the tracked evidence dirs, of the tracked receipts and
  raw captures -- each also byte-checked against the HEAD tree (not just
  the worktree), targeted checks only, no tree enumeration;
- receipt arithmetic: normal kernel_lost=0; overflow kernel_lost=385 with
  queued_records=127 so 127+385=512; 17-case consumer receipts x2 with
  failures=0; final consumer pin dee9a3b5 (normal exit0 / loss exit3
  kernel_loss_counter_nonzero 26471);
- mechanism content anchors in the pinned snapshots: recorder
  PERF_FORMAT_LOST read_format=16 (1ull<<4), inherit=0, ring mmap before
  ENABLE, after-DISABLE bounded-EINTR read16 before close(fd), fail-closed
  completeness, meta count null on read failure; consumer
  validate_kernel_loss_counter before decoding, --require-kernel-counter,
  post_disable_kernel_event_loss_counter window method;
- the sentinel-era mechanism is superseded by the kernel-counter
  integration and the documented debt remains (header G9 wording, consumer
  docstring);
- the P3 checkout-line discrepancy (reviews record main 9e8ba03e while
  main-verdict.json receipt source_head is 1b3dfdcc; both ancestors of
  HEAD, 9e8ba03e an ancestor of 1b3dfdcc, disjoint from the perf source
  bindings which use tracked snapshot bytes);
- HEAD relations are ancestry checks only (never permanent HEAD equality):
  baseline 31e5b65f, architecture f333316e, and both source-line commits
  must be ancestors of whatever HEAD is current;
- boundaries: no MIXED/G6/Full closure, no #84 closure, no #83 rerun,
  diagnostic_only/full_acceptance=false, and the live perf-stream contract
  docs/coordination/perf-stream-contract-20260913.md stays a tracked live
  pointer outside the candidate batch;
- mutation negatives (hash, size, receipt arithmetic, note boundary, and
  lifecycle detectors actually fail on mutated inputs).

The two CANDIDATE_PATHS (this ingest note and this test file) follow a
lifecycle; the suite accepts exactly three valid states and rejects
everything else (partial/mixed presence, nonzero stages, blob mismatch):

- A) pre-admission: neither candidate staged nor in HEAD;
- B) precommit: both staged at stage 0, each index blob byte-identical to
   its working-tree file, and neither yet in HEAD;
- C) postcommit: both in HEAD byte-identical to the working-tree files
   with the real index matching HEAD for them.

Run modes:
- normal: python -m unittest validation.test_codebuddy_perf_counter_context
  (or pytest). Any of the three lifecycle states is accepted; ordinary
  runs use read-only git plumbing only and must not mutate Git.
- temporary GIT_INDEX_FILE: with the two candidates staged into a private
  index and WKSIM_PERF_COUNTER_TEMP_INDEX=1 in the environment, the suite
  additionally asserts that index stages the two candidates at stage 0,
  blob-identical to the working-tree files. Extra independent-review or
  manifest files from later final batches are allowed in that index; the
  real index is not required to stay candidate-free forever (postcommit is
  a valid real-index state).
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
REVIEW_SOURCE_HEAD = "9e8ba03e43627918d5fab28aa59765a02fb068d1"
RECEIPT_SOURCE_HEAD = "1b3dfdcc106be18bcff8ff0e69269f6c7eab755d"

REVIEW1_REL = "docs/coordination/omp-perf-counter-integration-review-20260913.md"
REVIEW1_SHA256 = "9e4a857bb52fc740e25085cb955879f96942f29663a360c802b45e07dab50b2c"
REVIEW1_BYTES = 5601

REVIEW2_REL = "docs/coordination/omp-perf-lost-counter-review-20260913.md"
REVIEW2_SHA256 = "e35ba529ae1eb18eb04c591f8bec2aea7f10c1a96ee02c1db56cf696dfcfef39"
REVIEW2_BYTES = 4890

NOTE_REL = "docs/coordination/codebuddy-perf-counter-context-ingest-note-20260914.md"
TEST_REL = "validation/test_codebuddy_perf_counter_context.py"
CANDIDATE_PATHS = (NOTE_REL, TEST_REL)

VALID_LIFECYCLE_STATES = ("pre-admission", "precommit", "postcommit")

DS_RECORDER = "validation/coordination/ds-perf-stream-recorder-20260913-01"
DS_CONSUMER = "validation/coordination/ds-perf-stream-consumer-20260913-01"
INT01 = "validation/coordination/perf-counter-integration-20260913-01"
INT02 = "validation/coordination/perf-counter-integration-20260913-02"
LOST01 = "validation/coordination/perf-lost-counter-20260913-01"

RECORDER_SHA256 = "aa807f3baaafcd64ed6174a49f8010b49798a74d139ead2d4eb69eafa503c1d2"
HEADER_SHA256 = "ef1eabf247107098dc59a314d99b8fc82d4c54dbddd58d645bcec35141a12823"
CONSUMER_SHA256 = "dee9a3b5c3cafb42e69836758ccaebd4dbd78e8fa569d203c7ca1d36a03179bc"
PROBE_SHA256 = "93a95a4aa8d02cfcf5eedfd9abeb4db76bf80b92dda85fd2f7ecf8afe84e9b4a"
SUPERSEDED_SHA256 = "49303dab8cea513db3891924fa51813b441ca2e62fc038683ae6b775d0ad7b4d"

# Tracked snapshot copies that must be byte-identical across evidence dirs.
IDENTITY_GROUPS = {
    "recorder": [
        DS_RECORDER + "/wksim_perf_stream.c",
        INT01 + "/sources/wksim_perf_stream.c",
    ],
    "header": [
        DS_RECORDER + "/wksim_perf_stream.h",
        INT01 + "/sources/wksim_perf_stream.h",
    ],
    "consumer": [
        DS_CONSUMER + "/perf_stream_consumer.py",
        INT01 + "/sources/perf_stream_consumer.py",
    ],
    "probe": [
        LOST01 + "/lost_counter_probe.c",
        LOST01 + "/sources/lost_counter_probe.c",
    ],
}
GROUP_PINS = {
    "recorder": (RECORDER_SHA256, 55245),
    "header": (HEADER_SHA256, 7318),
    "consumer": (CONSUMER_SHA256, 29362),
    "probe": (PROBE_SHA256, 4579),
}

RECEIPTS = {
    LOST01 + "/receipt.json": ("9bb5a22c8327b4de518d5283d466d89fc05fb5036bfb0273dfbd0dda0b255f4f", 7177),
    INT01 + "/receipt.json": ("66a29ed985491b1884c190f53adbc2ca5676f874fbc064758ad4843f46fc9769", 8396),
    INT01 + "/main-verdict.json": ("4fcd7a6a217fb8e57e598a1b50bebf94e2c1181ab9e8c2f6d0c41bb7f15ebb96", 3174),
    INT01 + "/final-consumer-check.json": ("f7caf584ccf013503dcd011540634306345b909fb8d6b8790f586e9282cb2ebc", 881),
    INT01 + "/consumer-receipt.json": ("dc5476513cadb23e2fefb82c62d4e672c00160335c64b184dd136f621407518e", 6290),
    INT02 + "/consumer-receipt.json": ("6e246ec94eda958de44f348120fc547cc44385aaad635cbb19aa108cedc6e351", 6290),
    LOST01 + "/capture/normal.raw": ("c46d039bd5bc6daf043e31242b2608b4ee7076eaa2fcb509d78544d4a8525488", 128),
    LOST01 + "/capture/overflow_disabled_without_drain.raw": ("e096de8815f769e90ee3d985f879ff43a9fa314a50a0151c49f10a36ba5c0a97", 4064),
    INT01 + "/superseded-sentinel-source.c": (SUPERSEDED_SHA256, 57916),
}

EVIDENCE_DIRS = (
    LOST01, INT01, INT02, DS_RECORDER, DS_CONSUMER,
    "validation/coordination/ds-perf-stream-fixtures-20260913-01",
)

LIVE_CONTRACT_REL = "docs/coordination/perf-stream-contract-20260913.md"

RECORDER_REL = INT01 + "/sources/wksim_perf_stream.c"
CONSUMER_REL = INT01 + "/sources/perf_stream_consumer.py"
HEADER_REL = INT01 + "/sources/wksim_perf_stream.h"


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


def check_receipt_arithmetic(cases):
    """cases: {'normal': {...}, 'overflow': {...}} parsed probe stdout lines.

    Fail-closed on any drift of the receipt arithmetic."""
    normal, overflow = cases["normal"], cases["overflow_disabled_without_drain"]
    if normal.get("kernel_lost") != 0:
        raise AssertionError("normal kernel_lost must be exactly 0, got %r" % normal.get("kernel_lost"))
    if normal.get("read_bytes") != 16 or normal.get("queued_lost_records") != 0:
        raise AssertionError("normal read16/no-LOST anchors drifted: %r" % normal)
    if overflow.get("kernel_lost") != 385:
        raise AssertionError("overflow kernel_lost must be exactly 385, got %r" % overflow.get("kernel_lost"))
    if overflow.get("queued_records") != 127:
        raise AssertionError("overflow queued_records must be exactly 127, got %r" % overflow.get("queued_records"))
    if overflow.get("queued_lost_records") != 0:
        raise AssertionError("overflow must show 0 published LOST records")
    if overflow["queued_records"] + overflow["kernel_lost"] != 512:
        raise AssertionError("127+385 != 512: arithmetic no longer closes")


def check_note_boundaries(text):
    for required in (
        REVIEW1_SHA256, REVIEW2_SHA256, "5601", "4890",
        BASELINE_HEAD, ARCH_ANCESTOR, REVIEW_SOURCE_HEAD, RECEIPT_SOURCE_HEAD,
        "KEEP", "被取代的历史语境", "P1=0 / P2=0", "127+385=512",
        "diagnostic_only", "full_acceptance=false",
        "不重跑 #83", "不构成 #84 收口", "MIXED", "G6", "Full",
        "祖先检查", "不做永久 HEAD 相等断言",
        LIVE_CONTRACT_REL, "活指针",
        "superseded-sentinel-source.c", "PERF_FORMAT_LOST",
    ):
        if required not in text:
            raise AssertionError("ingest note lost required anchor: %r" % required)
    lowered = text.lower()
    for forbidden in (
        "验收通过", "已批准", "批准通过", "已收口", "closure approved",
        "approved by", "full_acceptance=true", "full_acceptance: true",
        "#83 已重跑", "#83重跑已", "已重跑 #83",
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

    def test_review_docs(self):
        check_pinned_file(REVIEW1_REL, REVIEW1_SHA256, REVIEW1_BYTES)
        check_pinned_file(REVIEW2_REL, REVIEW2_SHA256, REVIEW2_BYTES)
        self.assertEqual(sha256_bytes(head_bytes(REVIEW1_REL)), REVIEW1_SHA256)
        self.assertEqual(sha256_bytes(head_bytes(REVIEW2_REL)), REVIEW2_SHA256)

    def test_identity_groups_across_evidence_dirs(self):
        for group, rels in IDENTITY_GROUPS.items():
            want_sha, want_size = GROUP_PINS[group]
            for rel in rels:
                check_pinned_file(rel, want_sha, want_size)
                self.assertEqual(sha256_bytes(head_bytes(rel)), want_sha,
                                 rel + " HEAD-tree bytes drifted")
                self.assertIn(rel, git_out("ls-files", "--", rel).splitlines(),
                              rel + " must stay tracked")

    def test_receipts_and_raw_captures(self):
        for rel, (want_sha, want_size) in RECEIPTS.items():
            check_pinned_file(rel, want_sha, want_size)
            self.assertEqual(sha256_bytes(head_bytes(rel)), want_sha,
                             rel + " HEAD-tree bytes drifted")


class TestReceiptArithmetic(unittest.TestCase):
    """kernel_lost=0 normal; 385+127=512 overflow; consumer pins."""

    @staticmethod
    def _probe_cases():
        doc = json.loads((REPO / (LOST01 + "/receipt.json")).read_text(encoding="utf-8"))
        run = next(c for c in doc["commands"] if c["argv"] and c["argv"][0].startswith("./lost_counter"))
        cases = {}
        for line in run["stdout"].splitlines():
            obj = json.loads(line)
            if "case" in obj:
                cases[obj["case"]] = obj
            elif "kernel" in obj:
                cases["_env"] = obj
        return doc, cases

    def test_probe_receipt_arithmetic(self):
        doc, cases = self._probe_cases()
        self.assertEqual(doc["source_sha256"]["lost_counter_probe.c"], PROBE_SHA256)
        self.assertEqual(cases["_env"]["read_format"], 16)
        self.assertTrue(cases["_env"]["kernel"].startswith("6.6.87.2-microsoft-standard-WSL2"))
        self.assertTrue(doc["boot_id"].startswith("b3fa43aa"))
        check_receipt_arithmetic(cases)

    def test_final_consumer_pin(self):
        doc = json.loads((REPO / (INT01 + "/final-consumer-check.json")).read_text(encoding="utf-8"))
        self.assertEqual(doc["consumer_sha256"], CONSUMER_SHA256)
        by_case = {c["case"]: c for c in doc["checks"]}
        self.assertEqual(by_case["normal"]["exit_code"], 0)
        loss = by_case["loss"]
        self.assertEqual(loss["exit_code"], 3)
        self.assertIn("kernel_loss_counter_nonzero", loss["stderr"])
        self.assertIn("26471", loss["stderr"])

    def test_counter_consumer_receipts_17_cases(self):
        for rel in (INT01 + "/consumer-receipt.json", INT02 + "/consumer-receipt.json"):
            doc = json.loads((REPO / rel).read_text(encoding="utf-8"))
            self.assertIs(doc["synthetic"], True)
            self.assertEqual(doc["cases"], 17)
            self.assertEqual(doc["failures"], 0)
            names = {r["case"] for r in doc["results"]}
            for expected in ("zero", "inspect_legacy", "required_legacy", "raw_lost_despite_zero"):
                self.assertIn(expected, names, rel + " lost case " + expected)
            by_name = {r["case"]: r for r in doc["results"]}
            self.assertEqual(by_name["inspect_legacy"]["exit_code"], 0)
            self.assertEqual(by_name["required_legacy"]["exit_code"], 3)

    def test_main_verdict_pins_and_flags(self):
        doc = json.loads((REPO / (INT01 + "/main-verdict.json")).read_text(encoding="utf-8"))
        self.assertEqual(doc["source_head"], RECEIPT_SOURCE_HEAD)
        self.assertEqual(doc["classification"], "diagnostic_only")
        self.assertIs(doc["architecture_acceptance"], False)
        self.assertIs(doc["full_acceptance"], False)
        self.assertEqual(doc["recorder_sha256"], RECORDER_SHA256)
        self.assertEqual(doc["header_sha256"], HEADER_SHA256)
        self.assertEqual(doc["consumer_sha256"], CONSUMER_SHA256)
        self.assertEqual(doc["native_regression"]["compilations"], 6)
        self.assertEqual(doc["native_regression"]["fault_programs"], 5)
        self.assertEqual(doc["normal"]["kernel_lost_count"], 0)
        self.assertEqual(doc["pending_loss"]["records"], 16383)
        self.assertEqual(doc["pending_loss"]["lost_records"], [])
        self.assertEqual(doc["pending_loss"]["kernel_lost_count"], 26471)
        self.assertEqual(doc["pending_loss"]["reason"], "kernel_loss_counter_nonzero")

    def test_integration_receipt_pins(self):
        doc = json.loads((REPO / (INT01 + "/receipt.json")).read_text(encoding="utf-8"))
        self.assertEqual(doc["source_head"], REVIEW_SOURCE_HEAD)
        self.assertEqual(doc["source_sha256"]["wksim_perf_stream.c"], RECORDER_SHA256)
        self.assertEqual(doc["source_sha256"]["wksim_perf_stream.h"], HEADER_SHA256)


class TestSnapshotAnchors(unittest.TestCase):
    """Line anchors against the pinned snapshot bytes (aa807f3b / dee9a3b5)."""

    def test_recorder_mechanism_anchors(self):
        lines = snapshot_lines(RECORDER_REL)
        line_has(lines, 47, "1ull << 4")                      # PERF_FORMAT_LOST = 16
        line_has(lines, 754, "attr.read_format = WKSIM_PERF_FORMAT_LOST")
        line_has(lines, 757, "attr.inherit = 0")
        line_has(lines, 780, "void *mapping = mmap(")          # ring mmap
        line_has(lines, 898, "PERF_EVENT_IOC_ENABLE")          # ENABLE after mmap
        line_has(lines, 1087, "PERF_EVENT_IOC_DISABLE")
        line_has(lines, 1101, "for (int attempt = 0; attempt < 8; ++attempt)")
        line_has(lines, 1210, "close(stream->fd) != 0")
        line_has(lines, 1232, '"null"')                        # count null on read failure
        line_has(lines, 1361, "complete = (error_count_now(stream) == 0) && disable_ok")
        # ordering: mmap < ENABLE, and DISABLE < bounded read < close
        self.assertLess(780, 898)
        self.assertLess(1087, 1101)
        self.assertLess(1101, 1210)
        # EINTR bound actually retries only on EINTR
        self.assertIn("lost_read_errno != EINTR", "\n".join(lines[1100:1106]))
        # fail-closed: nonzero counter recorded as CAPTURE_INCOMPLETE
        self.assertIn("WKSIM_ERR_CAPTURE_INCOMPLETE", "\n".join(lines[1105:1117]))
        # sentinel-era mechanism fully removed from the integrated recorder
        self.assertNotIn("sentinel", "\n".join(lines).lower())

    def test_consumer_mechanism_anchors(self):
        lines = snapshot_lines(CONSUMER_REL)
        line_has(lines, 147, "def validate_kernel_loss_counter")
        line_has(lines, 165, "raise ContractError('kernel_loss_counter_nonzero'")
        line_has(lines, 238, "bounds['kernel_counter_verified'] = validate_kernel_loss_counter(meta)")
        line_has(lines, 268, "def decode_records")
        line_has(lines, 482, "'--require-kernel-counter'")
        line_has(lines, 497, "args.require_kernel_counter")
        line_has(lines, 498, "kernel_loss_counter_required")
        line_has(lines, 505, "post_disable_kernel_event_loss_counter")
        line_has(lines, 499, "decode_records(blob, meta, bounds)")
        # kernel-counter validation runs strictly before decoding
        self.assertLess(238, 268)
        self.assertLess(238, 499)
        # pure-int range check [0, 2^64-1]
        self.assertIn("(1 << 64) - 1", "\n".join(lines[147:167]))

    def test_documented_debt_still_present(self):
        header = snapshot_lines(HEADER_REL)
        self.assertIn("G9", header[79])
        self.assertIn("sentinel", header[83])
        self.assertIn("blocked", header[83])
        consumer = snapshot_lines(CONSUMER_REL)
        docstring = "\n".join(consumer[14:17]).lower()
        self.assertNotIn("kernel", docstring,
                         "consumer docstring debt was fixed; update the debt record")
        # superseded sentinel source preserved as tracked evidence
        self.assertTrue((REPO / (INT01 + "/superseded-sentinel-source.c")).is_file())


class TestNoteAndReviews(unittest.TestCase):
    """The note binds the reviews byte-level; reviews carry the claims."""

    def test_note_binds_reviews_and_baseline(self):
        check_note_boundaries((REPO / NOTE_REL).read_text(encoding="utf-8"))

    def test_review_content_anchors(self):
        r1 = (REPO / REVIEW1_REL).read_text(encoding="utf-8")
        for token in ("9e8ba03e43627918d5fab28aa59765a02fb068d1", "--require-kernel-counter",
                      "26471", "py:147-166", "c:754", "kernel_loss_counter_nonzero",
                      "post_disable_kernel_event_loss_counter"):
            self.assertIn(token, r1, "integration review lost anchor: " + token)
        r2 = (REPO / REVIEW2_REL).read_text(encoding="utf-8")
        for token in ("9e8ba03e43627918d5fab28aa59765a02fb068d1", "PERF_FORMAT_LOST",
                      "read_format=16", "kernel_lost=385", "kernel_lost=0",
                      "127+385=512", "427645e3db3a8896714f22a3d3fe0c3f7b317ad4",
                      "linux-msft-wsl-6.6.87.2"):
            self.assertIn(token, r2, "lost-counter review lost anchor: " + token)

    def test_p3_checkout_line_discrepancy_bound(self):
        # Reviews record 9e8ba03e; the main-verdict receipt records 1b3dfdcc.
        # Both are ancestors of current HEAD (ancestor checks, never equality),
        # and 9e8ba03e is an ancestor of 1b3dfdcc.
        self.assertEqual(
            git_out("merge-base", REVIEW_SOURCE_HEAD, RECEIPT_SOURCE_HEAD).strip(),
            REVIEW_SOURCE_HEAD)
        # The P3 does not touch the perf source bindings: snapshots are
        # pinned by bytes in tracked evidence dirs, independent of checkout.
        self.assertEqual(GROUP_PINS["recorder"][0], RECORDER_SHA256)

    def test_gitattributes_byte_identity_premise(self):
        for d in EVIDENCE_DIRS:
            path = REPO / d / ".gitattributes"
            self.assertTrue(path.is_file(), d + "/.gitattributes missing")
            self.assertEqual(path.read_bytes().decode("utf-8").strip(), "* -text")
            self.assertIn(d + "/.gitattributes",
                          git_out("ls-files", "--", d + "/.gitattributes").splitlines())
        # the repo-root .gitattributes neither sets a global rule nor lists
        # the evidence dirs -- no line conversion anywhere in the chain
        root = (REPO / ".gitattributes").read_text(encoding="utf-8")
        self.assertNotIn("* -text", root)

    def test_live_contract_stays_outside_batch(self):
        self.assertIn(LIVE_CONTRACT_REL,
                      git_out("ls-files", "--", LIVE_CONTRACT_REL).splitlines(),
                      "live perf-stream contract must remain tracked")
        note = (REPO / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("活指针", note)
        self.assertIn("候选之外", note)


class TestAncestry(unittest.TestCase):
    """Ancestor checks only -- never permanent HEAD equality."""

    def test_ancestors_of_current_head(self):
        for commit, label in (
            (BASELINE_HEAD, "baseline 31e5b65f"),
            (ARCH_ANCESTOR, "architecture f333316e"),
            (REVIEW_SOURCE_HEAD, "review source line 9e8ba03e"),
            (RECEIPT_SOURCE_HEAD, "receipt source line 1b3dfdcc"),
        ):
            proc = git("merge-base", "--is-ancestor", commit, "HEAD", allow_fail=True)
            self.assertEqual(proc.returncode, 0, label + " must stay an ancestor of HEAD")
        # 9e8ba03e is an ancestor of 1b3dfdcc (the P3 ordering)
        self.assertEqual(
            git_out("merge-base", REVIEW_SOURCE_HEAD, RECEIPT_SOURCE_HEAD).strip(),
            REVIEW_SOURCE_HEAD)


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
        data = (REPO / RECORDER_REL).read_bytes()
        mutated = data.replace(b"inherit = 0", b"inherit = 1", 1)
        self.assertNotEqual(sha256_bytes(mutated), RECORDER_SHA256)
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "mutated.c"
            fake.write_bytes(mutated)
            with self.assertRaises(AssertionError):
                check_pinned_file(str(fake), RECORDER_SHA256, len(data))

    def test_hash_detector_fails_on_mutated_size(self):
        with self.assertRaises(AssertionError):
            check_pinned_file(RECORDER_REL, RECORDER_SHA256, 55246)

    def test_receipt_arithmetic_fails_on_mutated_lost(self):
        _, cases = TestReceiptArithmetic._probe_cases()
        cases["overflow_disabled_without_drain"]["kernel_lost"] = 386
        with self.assertRaises(AssertionError):
            check_receipt_arithmetic(cases)

    def test_receipt_arithmetic_fails_on_mutated_records(self):
        _, cases = TestReceiptArithmetic._probe_cases()
        cases["overflow_disabled_without_drain"]["queued_records"] = 128
        with self.assertRaises(AssertionError):
            check_receipt_arithmetic(cases)

    def test_receipt_arithmetic_fails_on_normal_false_positive(self):
        _, cases = TestReceiptArithmetic._probe_cases()
        cases["normal"]["kernel_lost"] = 1
        with self.assertRaises(AssertionError):
            check_receipt_arithmetic(cases)

    def test_note_detector_fails_on_boundary_mutation(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        mutated = text.replace("不重跑 #83", "重跑 #83")
        self.assertNotEqual(mutated, text)
        self.assertNotIn("不重跑 #83", mutated)
        with self.assertRaises(AssertionError):
            check_note_boundaries(mutated)

    def test_note_detector_fails_on_elevation_injection(self):
        text = (REPO / NOTE_REL).read_text(encoding="utf-8")
        with self.assertRaises(AssertionError):
            check_note_boundaries(text + "\n验收通过\n")


@unittest.skipUnless(os.environ.get("WKSIM_PERF_COUNTER_TEMP_INDEX") == "1",
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

    def test_real_index_lifecycle_consistent(self):
        entries = read_index_entries()  # real index even under temp GIT_INDEX_FILE
        for rel in CANDIDATE_PATHS:
            if rel in entries:
                stage, blob = entries[rel]
                self.assertEqual(stage, 0, rel + " at nonzero stage in the real index")
                self.assertEqual(blob, worktree_blob(rel),
                                 rel + " real-index blob differs from working bytes")
        # the verified tracked anchors must still live in the real index
        for rel in (REVIEW1_REL, REVIEW2_REL, RECORDER_REL, CONSUMER_REL,
                    INT01 + "/main-verdict.json", LOST01 + "/receipt.json"):
            self.assertIn(rel, entries, "tracked anchor missing from real index: " + rel)


if __name__ == "__main__":
    unittest.main()
