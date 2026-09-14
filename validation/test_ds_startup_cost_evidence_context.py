"""Offline context-binding tests for the ds-startup-cost-evidence snapshot ingest.

Scope (single file, fully offline, no network, no native/build/runtime runs):

* Byte-bind the 2026-09-12 prior-slot DS-B startup-cost snapshot
  ``docs/coordination/ds-startup-cost-evidence-20260912.json`` (SHA256
  ``675026ab…`` / 18778 bytes), its Markdown twin
  ``docs/coordination/ds-startup-cost-evidence-20260912.md`` (``a1df834b…`` /
  17495 bytes) and the ingest note
  ``docs/coordination/ds-startup-cost-evidence-ingest-note-20260914.md``
  (``2ce0ac2d…`` / 12417 bytes).
* Strict-load the snapshot (rejecting duplicate keys, NaN/Infinity constants
  and ``1e999`` overflow) and verify the JSON/MD terminal-SHA tables agree
  11-of-11 (5 source pins after dropping ``*_role`` keys + 6 retained-raw
  pins).
* Re-verify the tracked arithmetic/trace/latch/phase-partition anchors named
  by the note §2.1: the diagnostic triple under
  ``validation/33-rate-profile/diagnostic-triple-20260912/`` and
  ``docs/coordination/ds-c1-actual-analysis-20260912.json``.
* Re-verify the runner truth registered by the note §2.2/§4.1: the historical
  runner pin ``fd0b7ee6…`` equals the blob content of
  ``tools/run_joint_flight.py`` at commit ``7cb7e8401776848fcb11e0a8dd2237c1eee2337b``
  (branch ``codex/planner-release-validation``), which is NOT an ancestor of
  HEAD; the cited historical line ranges match that blob; the current-tree
  runner semantics are the read-only snapshot request at ``:959`` and the
  reanchor gate at ``:975``; and C2 disposition remains unresolved by the
  note's own registration.
* Verify the note's four P3 corrections, all stale/current-tree boundaries,
  historical-only / no-authority / barrier / identity / physics / no-issue-83
  wording, and that the continuity snapshots are note-recorded untracked
  attestations (never tracked anchors).
* Assert symbolic-HEAD ancestry for ``f333316e``, ``76f77470``, ``1c5656ed``
  and the binding baseline ``e2ecd62e``: each must be an ANCESTOR of whatever
  HEAD the suite runs at; HEAD equality is deliberately never asserted, so
  the suite stays valid at descendant commits.

All git queries are index-independent (merge-base, cat-file, show) or scoped
to specific paths whose tracked status does not change when the three
candidates plus this test are staged, so the suite is staging-safe; apart from
the three bound candidates (which travel with the candidate set) only tracked
files are read, so the suite is fresh-clone safe.  The historical runner blob
lives only on a non-ancestor branch; tests needing it skip with a clear reason
if that object is absent from the clone.

Binding the snapshot as historical context does NOT confer authority,
approval, acceptance, or any current runtime state; the note's semantics are
asserted fail-closed below.

Observed at binding baseline ``e2ecd62e914e075d0d9e40eef8ea9c034b958d2f``.
"""

import copy
import hashlib
import json
import math
import os
import re
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JSON_REL = "docs/coordination/ds-startup-cost-evidence-20260912.json"
MD_REL = "docs/coordination/ds-startup-cost-evidence-20260912.md"
NOTE_REL = "docs/coordination/ds-startup-cost-evidence-ingest-note-20260914.md"

JSON_SHA256 = "675026ab4f13b1a61e44fa60a208483faa26a3b08794a30118a453103689e709"
JSON_SIZE = 18778
MD_SHA256 = "a1df834b37241f7dc8fb2e1a9ec4407f330a05158e8e8b11f31ca6911800e2c4"
MD_SIZE = 17495
NOTE_SHA256 = "2ce0ac2d86999543eb4789f5a3502078dc441d93a678f6c1e755865c140c89a1"
NOTE_SIZE = 12417

C1_REL = "docs/coordination/ds-c1-actual-analysis-20260912.json"
TRIPLE_DIR = "validation/33-rate-profile/diagnostic-triple-20260912"

# Source pins recorded in the JSON terminal_shas (full values).
JOINT_PIN = "f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50"
JOINT_RATE_PIN = "0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4"
WORKER_PIN = "0becd1f3214b53c6169fb61ae010a969fb57a4ccbe26fb3ed3c3652c26ef7fab"
ANALYZER_PIN = "14ed9d64bb0daf0fb2ef9f4e21028a4ec164bb1255f98701542b59a68d2538a8"
RUNNER_PIN = "fd0b7ee6dfb99be7a2d6f580555c6f9bfcddf721e25f68e97761d7f5670df246"

# Commits whose blobs carry the historical pins.
WORKER_BLOB_COMMIT = "acf81d564ba29b74f8ec2f612f5c6444b06278d9"
ANALYZER_BLOB_COMMIT = "e1c163144de844bdaffef1e2df596c5d178b1092"
RUNNER_BLOB_COMMIT = "7cb7e8401776848fcb11e0a8dd2237c1eee2337b"
RUNNER_REL = "tools/run_joint_flight.py"
WORKER_REL = "Simulator/wksim_core/worker.py"
JOINT_REL = "Simulator/wksim_core/joint.py"
ANALYZER_REL = "tools/analyze_joint_rate_intervals.py"

# Ancestors of the running HEAD (symbolic); no HEAD equality anywhere.
ANCESTORS_OF_HEAD = [
    "f333316e6efa6b299b4288a9d91fb2bccedfb9d6",   # architecture ancestor
    "76f77470e91ecc742148df0f3eba6f5b5494511c",   # evidence-audit baseline
    "1c5656ed924020b3e626e68739caeeaef9f41a9e",   # note-writing HEAD
    "e2ecd62e914e075d0d9e40eef8ea9c034b958d2f",   # binding baseline
]

# Tracked arithmetic/trace/latch/phase-partition anchors (note §2.1).
TRIPLE = {
    "ztdsk269": {
        "groups": 24146, "creep_total_ns": 99687759, "work_over_total_ns": 33372289,
        "release_excess_total_ns": 66315470, "early_intervals": 246,
        "groups_at_or_before_boundary": 247,
        "trace_sha256": "9c79867222989eac6f627dafa115a6c5f214a418412be2aec89f3f28a0f9cb92",
    },
    "vwen35gc": {
        "groups": 21763, "creep_total_ns": 99636668, "work_over_total_ns": 34868504,
        "release_excess_total_ns": 64768164, "early_intervals": 248,
        "groups_at_or_before_boundary": 249,
        "trace_sha256": "e8c1c9e343dec468cdfa7de7708a9f499bb2dfffa54185b6c56695944236e0d8",
    },
    "7bdfxkb": {
        "groups": 27434, "creep_total_ns": 99717577, "work_over_total_ns": 25703958,
        "release_excess_total_ns": 74013619, "early_intervals": 249,
        "groups_at_or_before_boundary": 250,
        "trace_sha256": "484016e746bfad78ef5d46f0d85d19e1761ebea30fea2d22e63649ea57e07d0b",
    },
}
LATCH_LATE_NS = 100129488
LATCH_BOUNDARY_TICK = 96624

CONTINUITY_SNAPSHOTS = [
    "validation/architecture-decoupling-20260912/precommit-state.json",
    "validation/architecture-decoupling-20260912/pre-main-switch-state.json",
]

TRACKED_ANCHOR_PATHS = [
    C1_REL,
    TRIPLE_DIR + "/ztdsk269.json",
    TRIPLE_DIR + "/vwen35gc.json",
    TRIPLE_DIR + "/7bdfxkb.json",
    JOINT_REL,
    WORKER_REL,
    "Simulator/wksim_runtime/joint_rate.py",
    RUNNER_REL,
]

NOTE_P3_PHRASES = [
    "P3-1", "P3-2", "P3-3", "P3-4",
    # P3-1: analyzer generation correction
    "75353c06", "1c43ac9c", "c3ba9de8",
    # P3-2: worker.py:182-193 attribution actually sits in joint.py:189-193
    "joint.py:189-193",
    # P3-3: the 24147-groups sum is a typo for the tracked 24146
    "24146",
    # P3-4: ns-granularity values are nearest-1000 ns roundings, not bitwise
    "最近 1000 ns 取整",
]

NOTE_BOUNDARY_PHRASES = [
    # historical-only / no authority semantics
    "历史语境绑定",
    "historical context only",
    "不构成任何验收、批准、收口或复核记录",
    "不是当前的权威、批准、验收或收口状态",
    "只证明字节稳定，不证明内容正确",
    # stale/current-tree boundaries (§2.2/§4)
    "不在当前 HEAD 祖先链上",
    "退出码 1",
    "run_joint_flight.py:959",
    "reanchor 门 `:975`",
    "worker.py:94-96",
    "e1c16314", "f21fc3af", "75353c06",
    "physics_health",
    # continuity snapshots are untracked attestations
    "precommit-state.json", "pre-main-switch-state.json",
    "untracked",
    # unresolved current state: C2 not adjudicated, unexcluded stays unexcluded
    "C2 处置状态仍未解决",
    "仍然未排除",
    "不声称其已完成或已放弃",
    "不改变任何 rate 预算",
    # runner-truth registration correction
    "7cb7e8401776848fcb11e0a8dd2237c1eee2337b",
    "fd0b7ee6…",
    "11/11 一致",
    # no issue-83 rerun; protected files untouched
    "未重跑 #83 的任何工作",
    "docs/Prometheus.gitmodules.reference",
    "validation/coordination/short-cycle-dispatches.json",
]

JSON_PHRASES = [
    "wksim.ds-startup-cost-evidence.v2",
    "4-tick barrier",
    "candidate C2 under A",
    "that the runtime is fixed",
    RUNNER_PIN,
]

MD_PHRASES = [
    "已证 / 未排除 / 仍需测量",
    "4-tick 屏障",
    "不宣称",
    # P3-3: the MD retains the historical typo "24147 组"; the tracked truth
    # is 24146 and the note registers the correction — the typo is pinned
    # here as a historical fact, never as arithmetic.
    "24147 组",
    "100.129 ms",
    "24146 组，@ tick 96624",
]


# --------------------------------------------------------------------------
# Strict JSON loading and evidence helpers
# --------------------------------------------------------------------------

def strict_loads(text):
    """json.loads rejecting duplicate keys, NaN/Infinity and 1e999 overflow."""
    def _no_duplicate_keys(pairs):
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            raise ValueError("duplicate JSON key(s): %s" % ", ".join(dupes))
        return dict(pairs)

    def _reject_constant(name):
        raise ValueError("non-finite JSON constant not allowed: %s" % name)

    def _parse_float(token):
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("numeric overflow in JSON float: %s" % token)
        return value

    return json.loads(
        text,
        object_pairs_hook=_no_duplicate_keys,
        parse_constant=_reject_constant,
        parse_float=_parse_float,
    )


def read_repo_bytes(rel_path):
    with open(os.path.join(REPO_ROOT, rel_path), "rb") as handle:
        return handle.read()


def sha256_hex(raw_bytes):
    return hashlib.sha256(raw_bytes).hexdigest()


def git(*args):
    return subprocess.run(
        ["git"] + list(args), cwd=REPO_ROOT, capture_output=True, check=True
    )


def git_tracked(rel_path):
    return bool(git("ls-files", "-z", "--", rel_path).stdout.strip(b"\x00"))


def require_tracked(paths):
    missing = [p for p in paths if not git_tracked(p)]
    if missing:
        raise ValueError("not tracked in git index: %s" % "; ".join(missing))


def require_phrases(text, phrases):
    missing = [phrase for phrase in phrases if phrase not in text]
    if missing:
        raise ValueError("missing required phrase(s): %s" % " | ".join(missing))


def file_line_contains(rel_path, lineno, *tokens):
    """True when every token appears in the 1-based line `lineno`."""
    lines = read_repo_bytes(rel_path).decode("utf-8").splitlines()
    if lineno < 1 or lineno > len(lines):
        return False
    return all(token in lines[lineno - 1] for token in tokens)


def blob_line_contains(blob_text, lineno, *tokens):
    lines = blob_text.splitlines()
    if lineno < 1 or lineno > len(lines):
        return False
    return all(token in lines[lineno - 1] for token in tokens)


def bind_bytes(rel_path, expected_sha, expected_size, raw=None):
    if raw is None:
        raw = read_repo_bytes(rel_path)
    digest = sha256_hex(raw)
    if digest != expected_sha:
        raise ValueError(
            "%s hash drift: expected %s, observed %s"
            % (rel_path, expected_sha, digest)
        )
    if len(raw) != expected_size:
        raise ValueError(
            "%s size drift: expected %d, observed %d"
            % (rel_path, expected_size, len(raw))
        )
    return raw


def json_terminal_pins(checks_data):
    """The 11 pins: sources minus *_role keys (5) + retained_raw (6)."""
    terminal = checks_data["terminal_shas"]
    sources = {
        path: sha for path, sha in terminal["sources"].items()
        if not path.endswith("_role")
    }
    pins = dict(sources)
    pins.update(terminal["retained_raw"])
    return sources, terminal["retained_raw"], pins


def md_terminal_table(md_text):
    """Parse the MD 终态 SHA table into {path: sha256} (11 rows expected)."""
    rows = {}
    for line in md_text.splitlines():
        if not line.startswith("| `"):
            continue
        match = re.match(r"^\|\s*`([^`]+)`", line)
        sha_match = re.search(r"`([0-9a-f]{64})`", line)
        if match and sha_match:
            rows[match.group(1)] = sha_match.group(1)
    return rows


def runner_blob_available():
    probe = subprocess.run(
        ["git", "cat-file", "-e", RUNNER_BLOB_COMMIT + "^{commit}"],
        cwd=REPO_ROOT, capture_output=True,
    )
    return probe.returncode == 0


# --------------------------------------------------------------------------
# Positive tests
# --------------------------------------------------------------------------

class TestCandidateByteBinding(unittest.TestCase):
    def test_three_candidate_bytes_bound(self):
        bind_bytes(JSON_REL, JSON_SHA256, JSON_SIZE)
        bind_bytes(MD_REL, MD_SHA256, MD_SIZE)
        bind_bytes(NOTE_REL, NOTE_SHA256, NOTE_SIZE)


class TestStrictJsonLoading(unittest.TestCase):
    def test_strict_loads_candidate_and_tracked_anchors(self):
        data = strict_loads(read_repo_bytes(JSON_REL).decode("utf-8"))
        self.assertEqual(data["kind"], "ds-startup-cost-evidence")
        self.assertEqual(data["schema"], "wksim.ds-startup-cost-evidence.v2")
        self.assertEqual(data["revision"], 2)
        c1 = strict_loads(read_repo_bytes(C1_REL).decode("utf-8"))
        self.assertIn("terminal_latch_closure", c1)
        for field in ("ztdsk269", "vwen35gc", "7bdfxkb"):
            triple = strict_loads(
                read_repo_bytes(TRIPLE_DIR + "/%s.json" % field).decode("utf-8")
            )
            self.assertEqual(triple["schema"], "wksim.rate-interval-attribution.v1")

    def test_rejects_duplicate_keys_nonfinite_and_overflow(self):
        for text in (
            '{"a": 1, "a": 2}',   # duplicate key
            '{"a": NaN}',          # non-finite constant
            '{"a": Infinity}',     # non-finite constant
            '{"a": 1e999}',        # numeric overflow
        ):
            with self.assertRaises(ValueError):
                strict_loads(text)


class TestJsonMdConsistency(unittest.TestCase):
    def setUp(self):
        self.json_data = strict_loads(read_repo_bytes(JSON_REL).decode("utf-8"))
        self.md_text = read_repo_bytes(MD_REL).decode("utf-8")

    def test_terminal_shas_structure_is_5_sources_plus_6_raw(self):
        sources, raw, pins = json_terminal_pins(self.json_data)
        self.assertEqual(len(sources), 5)
        self.assertEqual(len(self.json_data["terminal_shas"]["retained_raw"]), 6)
        self.assertEqual(len(pins), 11)
        # The *_role annotation key is dropped, not counted as a source pin.
        self.assertIn("tools/analyze_joint_rate_intervals.py_role",
                      self.json_data["terminal_shas"]["sources"])

    def test_md_terminal_sha_table_matches_json_11_of_11(self):
        _, _, pins = json_terminal_pins(self.json_data)
        table = md_terminal_table(self.md_text)
        self.assertEqual(len(table), 11)
        self.assertEqual(table, pins)


class TestTrackedArithmeticAnchors(unittest.TestCase):
    def setUp(self):
        require_tracked(TRACKED_ANCHOR_PATHS)
        self.triples = {
            field: strict_loads(
                read_repo_bytes(TRIPLE_DIR + "/%s.json" % field).decode("utf-8")
            )
            for field in TRIPLE
        }

    def test_diagnostic_triple_arithmetic_and_trace_pins(self):
        for field, expected in TRIPLE.items():
            data = self.triples[field]
            self.assertEqual(data["groups"], expected["groups"], field)
            self.assertEqual(data["creep_total_ns"], expected["creep_total_ns"], field)
            self.assertEqual(
                data["work_over_total_ns"], expected["work_over_total_ns"], field
            )
            self.assertEqual(
                data["release_excess_total_ns"],
                expected["release_excess_total_ns"], field
            )
            self.assertEqual(data["trace_sha256"], expected["trace_sha256"], field)
        # The three trace pins are exactly the retained_raw rate.jsonl pins.
        json_data = strict_loads(read_repo_bytes(JSON_REL).decode("utf-8"))
        retained = json_data["terminal_shas"]["retained_raw"]
        for field, expected in TRIPLE.items():
            self.assertIn(expected["trace_sha256"], retained.values(), field)

    def test_phase_partition_early_and_boundary_values(self):
        for field, expected in TRIPLE.items():
            partition = self.triples[field]["phase_partition"]
            boundary = partition["boundary"]
            self.assertEqual(
                boundary["groups_at_or_before_boundary"],
                expected["groups_at_or_before_boundary"], field
            )
            self.assertEqual(
                partition["classes"]["early"]["intervals"],
                expected["early_intervals"], field
            )

    def test_latch_closure_anchors_from_c1(self):
        c1 = strict_loads(read_repo_bytes(C1_REL).decode("utf-8"))
        candidate = c1["terminal_latch_closure"]["candidate"]
        self.assertEqual(candidate["recorded_latch_lateness_ns"], LATCH_LATE_NS)
        self.assertEqual(candidate["last_group_boundary_tick"], LATCH_BOUNDARY_TICK)
        self.assertIs(candidate["identity_sums_to_recorded"], True)
        self.assertIs(candidate["closes"], True)
        self.assertIs(c1["terminal_latch_closure"]["closure_holds"], True)


class TestSourcePins(unittest.TestCase):
    def test_ancestor_blob_and_current_pins(self):
        # joint.py and joint_rate.py: current tree still equals the pins.
        self.assertEqual(sha256_hex(read_repo_bytes(JOINT_REL)), JOINT_PIN)
        self.assertEqual(
            sha256_hex(read_repo_bytes("Simulator/wksim_runtime/joint_rate.py")),
            JOINT_RATE_PIN,
        )
        # worker.py: current tree drifted (1abf5f39), pin resolves to the
        # acf81d56 blob.
        self.assertEqual(
            sha256_hex(git("show", WORKER_BLOB_COMMIT + ":" + WORKER_REL).stdout),
            WORKER_PIN,
        )
        self.assertNotEqual(sha256_hex(read_repo_bytes(WORKER_REL)), WORKER_PIN)
        # analyzer: pin = the e1c16314 blob (the expired fe3 private copy).
        self.assertEqual(
            sha256_hex(git("show", ANALYZER_BLOB_COMMIT + ":" + ANALYZER_REL).stdout),
            ANALYZER_PIN,
        )

    def test_runner_pin_is_7cb7e840_blob_and_off_ancestry(self):
        if not runner_blob_available():
            self.skipTest(
                "historical runner commit %s absent from this clone"
                % RUNNER_BLOB_COMMIT[:8]
            )
        blob = git("show", RUNNER_BLOB_COMMIT + ":" + RUNNER_REL).stdout
        self.assertEqual(sha256_hex(blob), RUNNER_PIN)
        # 7cb7e840 is NOT an ancestor of the running HEAD (exit 1).
        probe = subprocess.run(
            ["git", "merge-base", "--is-ancestor", RUNNER_BLOB_COMMIT, "HEAD"],
            cwd=REPO_ROOT, capture_output=True,
        )
        self.assertNotEqual(probe.returncode, 0)
        # The current tree rewrote the runner; the pin no longer matches it.
        self.assertNotEqual(sha256_hex(read_repo_bytes(RUNNER_REL)), RUNNER_PIN)

    def test_cited_historical_runner_lines_match_blob(self):
        if not runner_blob_available():
            self.skipTest(
                "historical runner commit %s absent from this clone"
                % RUNNER_BLOB_COMMIT[:8]
            )
        blob = git("show", RUNNER_BLOB_COMMIT + ":" + RUNNER_REL).stdout.decode("utf-8")
        # :296-305 request_graph_ready gate and initialized.json write
        self.assertTrue(blob_line_contains(blob, 296, "task.request_graph_ready()"))
        self.assertTrue(blob_line_contains(blob, 301, "initialized.json"))
        # :901-903 tick-0 read-only snapshot request
        self.assertTrue(blob_line_contains(blob, 902, "receive_worker", "snapshot=True"))
        # :916-919 reanchor gate on the synchronized 4-tick boundary
        self.assertTrue(blob_line_contains(blob, 916, "clock.tick%4 == 0",
                                           "clock.synchronized"))
        self.assertTrue(blob_line_contains(blob, 918, "rate.reanchor",
                                           "synchronized_boundary"))
        # :963-967 in-loop import math / summaries row rebuild
        region = "\n".join(blob.splitlines()[962:967])
        self.assertIn("import math", region)
        self.assertIn("math.dist(state[6:9]", region)

    def test_current_tree_semantics_959_975_worker_joint(self):
        # runner :959 read-only snapshot request; :975 reanchor gate
        self.assertTrue(file_line_contains(RUNNER_REL, 959, "receive_worker",
                                           "snapshot=True"))
        self.assertTrue(file_line_contains(RUNNER_REL, 975, "rate.reanchor",
                                           "synchronized_boundary"))
        # worker current anchors: snapshot branch ≈ :94-96, initial_request
        # ≈ :114, initial sidecar ≈ :249
        self.assertTrue(file_line_contains(WORKER_REL, 93, "def step_request"))
        self.assertTrue(file_line_contains(WORKER_REL, 94, "read-only snapshot"))
        self.assertTrue(file_line_contains(WORKER_REL, 96, "'snapshot'"))
        self.assertTrue(file_line_contains(WORKER_REL, 114, "def initial_request"))
        self.assertTrue(file_line_contains(WORKER_REL, 249, "initial.jsonl"))
        # P3-2: request-dict rebuild and 120-element state copy at joint.py:189/:193
        self.assertTrue(file_line_contains(JOINT_REL, 189, "requests[name] = ("))
        self.assertTrue(file_line_contains(JOINT_REL, 193, "list(response['state'])"))


class TestNoteBinding(unittest.TestCase):
    def setUp(self):
        self.note_text = read_repo_bytes(NOTE_REL).decode("utf-8")

    def test_note_four_p3_corrections_pinned(self):
        require_phrases(self.note_text, NOTE_P3_PHRASES)

    def test_note_boundaries_and_honesty_wording(self):
        require_phrases(self.note_text, NOTE_BOUNDARY_PHRASES)
        # The JSON/MD carry the barrier / C2 / no-exclusive-claim wording.
        json_text = read_repo_bytes(JSON_REL).decode("utf-8")
        md_text = read_repo_bytes(MD_REL).decode("utf-8")
        require_phrases(json_text, JSON_PHRASES)
        require_phrases(md_text, MD_PHRASES)

    def test_continuity_snapshots_are_untracked_attestations(self):
        # The note records the continuity snapshots as untracked attestations;
        # they must never serve as tracked anchors for this binding.
        for path in CONTINUITY_SNAPSHOTS:
            self.assertFalse(
                git_tracked(path),
                "%s must stay untracked (note-recorded attestation only)" % path,
            )
        # When present locally they record the two candidate hashes by bytes.
        for path in CONTINUITY_SNAPSHOTS:
            if os.path.exists(os.path.join(REPO_ROOT, path)):
                text = read_repo_bytes(path).decode("utf-8")
                self.assertIn(JSON_SHA256, text, path)
                self.assertIn(MD_SHA256, text, path)


class TestAncestry(unittest.TestCase):
    def test_symbolic_head_ancestry_without_equality(self):
        # Every binding commit must be an ANCESTOR of whatever HEAD the suite
        # runs at.  HEAD equality is deliberately never asserted so the suite
        # remains valid at descendant commits.
        for rev in ANCESTORS_OF_HEAD:
            git("merge-base", "--is-ancestor", rev, "HEAD")


# --------------------------------------------------------------------------
# Negative tests (in-memory mutations only; no file is modified)
# --------------------------------------------------------------------------

class TestNegativeMutations(unittest.TestCase):
    def setUp(self):
        self.json_raw = read_repo_bytes(JSON_REL)
        self.json_data = strict_loads(self.json_raw.decode("utf-8"))
        self.md_text = read_repo_bytes(MD_REL).decode("utf-8")
        self.note_text = read_repo_bytes(NOTE_REL).decode("utf-8")

    def test_hash_drift_and_malformed_json_rejected(self):
        drifted = self.json_raw.replace(b'"revision": 2', b'"revision": 3')
        self.assertNotEqual(sha256_hex(drifted), JSON_SHA256)
        # Binding drifted bytes must fail on the pinned hash.
        with self.assertRaisesRegex(ValueError, "hash drift"):
            bind_bytes(JSON_REL, JSON_SHA256, JSON_SIZE, raw=drifted)
        # A correct hash with a wrong size must fail on the pinned size.
        with self.assertRaisesRegex(ValueError, "size drift"):
            bind_bytes(JSON_REL, JSON_SHA256, JSON_SIZE + 1)
        for text in (
            '{"schema": "x", "schema": "dup"}',
            '{"schema": NaN}',
            '{"schema": 1e999}',
        ):
            with self.assertRaises(ValueError):
                strict_loads(text)

    def test_consistency_and_arithmetic_mutations_rejected(self):
        # Dropping one of the 11 pins breaks the 11-of-11 equality.
        _, _, pins = json_terminal_pins(self.json_data)
        mutated = dict(pins)
        mutated.pop(next(iter(mutated)))
        table = md_terminal_table(self.md_text)
        self.assertEqual(len(table), 11)
        with self.assertRaises(AssertionError):
            self.assertEqual(table, mutated)
        # A drifted terminal pin breaks the table equality the same way.
        first_path = next(iter(pins))
        drifted_pins = dict(pins)
        drifted_pins[first_path] = "0" * 64
        with self.assertRaises(AssertionError):
            self.assertEqual(table, drifted_pins)
        # A mutated tracked triple value must fail the arithmetic comparison.
        triple = copy.deepcopy(
            strict_loads(
                read_repo_bytes(TRIPLE_DIR + "/ztdsk269.json").decode("utf-8")
            )
        )
        triple["creep_total_ns"] += 1
        self.assertNotEqual(triple["creep_total_ns"], TRIPLE["ztdsk269"]["creep_total_ns"])

    def test_missing_note_wording_rejected(self):
        require_phrases(self.note_text, NOTE_BOUNDARY_PHRASES)
        require_phrases(self.note_text, NOTE_P3_PHRASES)
        for anchor, phrase_list in (
            ("未重跑 #83 的任何工作", NOTE_BOUNDARY_PHRASES),
            ("C2 处置状态仍未解决", NOTE_BOUNDARY_PHRASES),
            ("joint.py:189-193", NOTE_P3_PHRASES),
        ):
            stripped = self.note_text.replace(anchor, "elided")
            with self.assertRaisesRegex(ValueError, "missing required phrase"):
                require_phrases(stripped, phrase_list)


if __name__ == "__main__":
    unittest.main()
