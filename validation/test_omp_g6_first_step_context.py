"""Offline context-binding tests for the OMP G6 first-step ingest (2026-09-14).

Scope (pure Python, fully offline, no network, no native/build/MATLAB/ROS/
DDS/SITL/FC/UE/model/flight runs, no issue-83 rerun):

* Bind three candidate documents by SHA256 and size:
  - docs/coordination/omp-reference-first-step-review-20260913.md
    (7973f0220c05861547283fbc47f3cfb8e5875a6101023e64593ad7b2664bc17a, 2979 B)
  - docs/coordination/omp-first-step-comparison-review-20260913.md
    (2026-09-14 precision-corrected version, superseding 8b222e1d...; see
    codebuddy-omp-g6-first-step-independent-review-20260914-01 P2-1/P3-2)
  - docs/coordination/omp-g6-first-step-ingest-note-20260914.md
    (records the supersession and the corrected precision facts)
* Bind the tracked comparison artifact
  validation/coordination/g6-target-first-step-20260913/comparison-v2.json
  (byte binding + HEAD blob identity) and recompute IEEE-754 ULP distances
  from its hex pairs: earliest p,q/r stage2 derivatives[1] = 1 ULP; q stage3
  derivatives[2] = 1 ULP; q stage3 derivatives[3] = 64 ULP
  (36494aa6d36ff400 -> 36494aa6d36ff3c0); q final state index3 = 44 ULP
  (3581440763f7c6a8 -> 3581440763f7c67c); p,q,r stage3 cont_states[1] and
  ub,vb,wb stage3 derivatives[0] each 1 ULP; ub,vb,wb final index0 1 ULP.
  There is NO "all later propagation is 1 ULP" regularity. 3.46e-47 is a
  normal (not subnormal) double; -4.95e-18 is the earliest differing
  double's value magnitude, not the 1-ULP delta (~ -7.7e-34).
* Assert the comparison review's two retractions of the reference review
  (staged-copy claim; content-only distinction) plus the CREATE_NEW boundary
  kept as intentional evidence, and the corrected precision wording in the
  two edited documents (forbidden: "（均 1 ULP" claim form, "次正规").
* Assert the three artifact identities (99fc1ec8... reference,
  34350997... top-level target trace, d55542d7... with-major variant,
  distinct and never to be mixed), the instrumentation facts
  (72 = 20+20+16+16, dropped=0, PostDerivatives distribution, 240 major f64,
  stage order, v2 final-state selection, earliest divergence chain),
  the current-vs-staged unused-driver divergence (repo 42212463... vs staged
  7f3bc0c8...), and the recorded 2026-09-14 owner ruling: the frozen R1
  driver 7f3bc0c8... exists in validation/numerical-conformance-u56ce17a/C0
  and numerical-conformance-gxxh6xhr/C2G,C3G as immutable evidence of what
  executed; the repo-current driver 42212463... (git blob 1cedff93...,
  committed in 3f40ba03) is current source differing by exactly one type
  gate and one float cast; NEITHER frozen-copy update NOR repo backfill is
  authorized (the prior live two-option wording is explicitly superseded);
  unused_changed_driver is a non-defect (execution-03 invoked neither
  driver) and invalidates neither R1 nor first-step evidence; old 7f3bc0c8
  citations are historical R1-era identity, not a current repo pin; every
  future Python-driver execution must recompute and record its launch-time
  SHA and snapshot executed bytes; the ruling closes only the owner-ruling
  subissue — not G6/Full (23 states, ode4_stage_mapping, native/full-window
  remain; issue 83 never rerun). Further boundaries: the 13/36 scope, the
  1ms / 4-tick / no-catch-up / 100ms / full-window timing premises, AP/PX4
  separation, the MISSING mixed-ability row, "event 72 is not a G6 pass",
  "xtj8wk8i never issue-83 evidence", and historical-only / no-authority /
  no-rerun semantics. The ingest note must state that the
  ds-g6-major-time-binding v3 directory is untracked and ignored and
  cannot serve as a tracked anchor.
* Git-side checks are symbolic-HEAD only: ancestry of f333316e, 1c5656ed,
  e2ecd62e, 01181887 (merge-base --is-ancestor <sha> HEAD); no HEAD-equality
  assertion anywhere. The e2ecd62e..01181887 delta must be disjoint from the
  bound documents, this test file, the driver, and the g6 evidence areas.
  Required tracked g6 anchors must exist in the HEAD tree; on-disk extras
  under the two evidence directories are tolerated only when git-ignored.

Design constraints (staging-stable by construction):

* No assertion depends on the candidates being untracked or on the exact
  contents of the git index; every git invocation is index-independent
  (ls-tree/cat-file of HEAD, tree-to-tree diff, merge-base, check-ignore),
  so the suite passes both with the real index and with a temporary
  GIT_INDEX_FILE in which exactly the four primary candidates (the two OMP
  review documents, the remediated ingest note, and this test file) are
  force-added.
* Fail-closed point-in-time bindings (driver hash, delta shape, evidence
  counts) are intentional: any drift must fail loudly, never silently pass.

2026-09-14 owner-ruling remediation: the note's former live two-option
passage ("update staged or backfill repo, pending owner ruling") was a P2
(a later independent CodeBuddy review verified both actions unsafe) and is
now superseded by the encoded ruling above. The prior independent-review
-02 and context-ingest manifest -01 byte identities of the note
(e9f74bfc.../11165 B) and this test (f1db73fc.../45920 B) are superseded;
those directories are preserved unchanged and excluded; a new reviewer
(-03) and a new manifest writer (-02) re-establish current authority.

Observed at authoritative HEAD 31e5b65f5448c5558450d16d0f46da0ef0f0a03c
(note-writing HEAD e2ecd62e914e075d0d9e40eef8ea9c034b958d2f and review HEAD
011818876c1b94875fd67cedaaa73abfac866633 are ancestors).
Binding these documents as historical context confers no authority, approval,
acceptance, or rerun permission.
"""

import hashlib
import json
import math
import os
import struct
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REF_REL = "docs/coordination/omp-reference-first-step-review-20260913.md"
REF_SHA = "7973f0220c05861547283fbc47f3cfb8e5875a6101023e64593ad7b2664bc17a"
REF_SIZE = 2979

CMP_REL = "docs/coordination/omp-first-step-comparison-review-20260913.md"
CMP_SHA = "728bce90e0e2da893746e9113954694b6fb7147537db18f564e186dfa5769c14"
CMP_SIZE = 3985

NOTE_REL = "docs/coordination/omp-g6-first-step-ingest-note-20260914.md"
# Remediated 2026-09-14 (owner-ruling P2 fix); supersedes the pre-remediation
# bytes e9f74bfcecc62a3af8765dbfe0194abc8a0e40231aa2baad98275851729e992f
# (11165 B) bound by superseded review -02 / manifest -01.
NOTE_SHA = "c7f034535096047e321ab654fac418d7de5775854ac0e5ff06d97db2369308bc"
NOTE_SIZE = 14459

CANDIDATES = [
    (REF_REL, REF_SHA, REF_SIZE),
    (CMP_REL, CMP_SHA, CMP_SIZE),
    (NOTE_REL, NOTE_SHA, NOTE_SIZE),
]

TEST_REL = "validation/test_omp_g6_first_step_context.py"

# The four primary candidates staged under a repo-external temporary
# GIT_INDEX_FILE (the two OMP review documents, the remediated note, this
# test). Staging is exercised by the runner, not by this suite.
STAGING_PATHS = [REF_REL, CMP_REL, NOTE_REL, TEST_REL]

CMP_V2_REL = (
    "validation/coordination/g6-target-first-step-20260913/comparison-v2.json"
)
CMP_V2_SHA = "2a6b8fe9338224d64f0cc91fd4c66139b3422ca23c3032049cd529d6387ea3c9"
CMP_V2_SIZE = 3477

DRIVER_REL = "tools/run_numerical_conformance.py"
DRIVER_REPO_SHA = "4221246303642b26290b63c118ced5209a6e928a6101140cc00dc4cd12278040"
DRIVER_STAGED_SHA = "7f3bc0c88263a6e1c94a3f42658fe43db2a0b75abca7a5fb59fcfaafdba99cde"

# Owner ruling (2026-09-14), verified at remediation time by direct
# recomputation: the frozen R1 driver copies are immutable evidence of what
# executed; the repo-current driver is current source committed in
# 3f40ba03 (blob 1cedff93...), differing from the frozen copy by exactly
# one type gate (L137) and one float cast (L148); neither frozen-copy
# update nor repo backfill is authorized.
FROZEN_DRIVER_PATHS = [
    "validation/numerical-conformance-u56ce17a/C0/run_numerical_conformance.py",
    "validation/numerical-conformance-gxxh6xhr/C2G/run_numerical_conformance.py",
    "validation/numerical-conformance-gxxh6xhr/C3G/run_numerical_conformance.py",
]
DRIVER_BLOB = "1cedff93bd8fd48d7e867541ed83423edaa03089"
DRIVER_COMMIT = "3f40ba03"

IDENTITIES = {
    "reference_sha256": (
        "99fc1ec84a110bea1e5998a97b4f9c66231966474268ba74bfc343b584e03f85",
        "validation/coordination/g6-reference-probe-20260913/run-03/reference-first-step.json",
    ),
    "target_trace_sha256": (
        "343509972eb3233cd8b4c32c8f0747c2e959cefeb2dab57ea747930c40e3fb86",
        "validation/coordination/g6-target-first-step-20260913/first-step-trace.jsonl",
    ),
    "with_major_variant_sha256": (
        "d55542d743c456073d2d362ed3f71232d6d4697f450eaa8f8333b88699436360",
        "validation/coordination/g6-target-first-step-20260913/with-major/first-step-trace.jsonl",
    ),
}

NOTE_HEAD = "e2ecd62e914e075d0d9e40eef8ea9c034b958d2f"
REVIEW_HEAD = "011818876c1b94875fd67cedaaa73abfac866633"
ANCESTOR_SHAS = [
    "f333316e6efa6b299b4288a9d91fb2bccedfb9d6",
    "1c5656ed924020b3e626e68739caeeaef9f41a9e",
    NOTE_HEAD,
    REVIEW_HEAD,
]

REQUIRED_TRACKED_ANCHORS = [
    "docs/coordination/g6-first-divergence-20260913.md",
    "validation/coordination/g6-reference-probe-20260913/execution-03/input-checks.json",
    "docs/2026-09-07_joint-rate-contract-proposal.md",
]

EVIDENCE_DIRS = [
    "validation/coordination/g6-reference-probe-20260913",
    "validation/coordination/g6-target-first-step-20260913",
]
EVIDENCE_TRACKED_COUNT = 101  # 75 + 26 in the HEAD tree

DELTA_FORBIDDEN_EXACT = [
    REF_REL,
    CMP_REL,
    NOTE_REL,
    TEST_REL,
    DRIVER_REL,
] + REQUIRED_TRACKED_ANCHORS
DELTA_FORBIDDEN_PREFIXES = [
    "validation/coordination/g6-reference-probe-20260913/",
    "validation/coordination/g6-target-first-step-20260913/",
    "validation/coordination/ds-g6-major-time-binding-20260913-01/",
]

# Pinned IEEE-754 facts, all recomputed from comparison-v2.json at
# remediation time (2026-09-14). Keys are (block, stage, field, index) for
# stage differences and (block, index) for final-state differences; values
# are (ulp_distance, reference_hex, target_hex).
PINNED_STAGE_ULP = {
    ("p,q,r", 2, "derivatives", 1): (
        1,
        "bc56d4db33a987b8",
        "bc56d4db33a987b9",
    ),
    ("q0 q1 q2 q3", 3, "derivatives", 2): (
        1,
        "bba76121ffa77473",
        "bba76121ffa77474",
    ),
    ("q0 q1 q2 q3", 3, "derivatives", 3): (
        64,
        "36494aa6d36ff400",
        "36494aa6d36ff3c0",
    ),
    ("p,q,r", 3, "cont_states", 1): (
        1,
        "bbb76121ffa77473",
        "bbb76121ffa77474",
    ),
    ("ub,vb,wb", 3, "derivatives", 0): (
        1,
        "baa3bfd397a2d0d5",
        "baa3bfd397a2d0d6",
    ),
}
PINNED_FINAL_ULP = {
    ("q0 q1 q2 q3", 3): (44, "3581440763f7c6a8", "3581440763f7c67c"),
    ("ub,vb,wb", 0): (1, "b9e48cb0f57301da", "b9e48cb0f57301db"),
}

# The earliest differing double's exact value magnitude (recomputed from the
# hex bc56d4db33a987b8); the 1-ULP delta at this magnitude is ~ -7.7e-34.
EARLIEST_VALUE = -4.950785821689364e-18
DOUBLE_MIN_NORMAL = 2.2250738585072014e-308

BLOCK_Q = "q0 q1 q2 q3"
BLOCK_PQR = "p,q,r"
BLOCK_XYZ = "xe,ye,ze"
BLOCK_V = "ub,vb,wb"


# --------------------------------------------------------------------------
# Helpers (pure functions over bytes/strings/lists; mutation-friendly)
# --------------------------------------------------------------------------

def read_repo_bytes(rel_path):
    with open(os.path.join(REPO_ROOT, rel_path), "rb") as handle:
        return handle.read()


def sha256_hex(raw_bytes):
    return hashlib.sha256(raw_bytes).hexdigest()


def check_binding(raw, expected_sha, expected_size, rel_path):
    """Bind a byte stream by SHA256 and byte size; raise on any drift."""
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
    return digest


def bind_doc(rel_path, expected_sha, expected_size):
    """Bind a repository document by SHA256 and byte size."""
    raw = read_repo_bytes(rel_path)
    check_binding(raw, expected_sha, expected_size, rel_path)
    return raw


def require_phrases(text, phrases, context):
    missing = [p for p in phrases if p not in text]
    if missing:
        raise ValueError(
            "%s: missing required phrase(s): %s" % (context, " | ".join(missing))
        )


def forbid_phrases(text, phrases, context):
    present = [p for p in phrases if p in text]
    if present:
        raise ValueError(
            "%s: forbidden phrase(s) present: %s" % (context, " | ".join(present))
        )


def validate_identity_table(mapping):
    """Each role must carry its pinned sha and object path; all shas distinct."""
    seen = {}
    for role, (sha, obj_path) in mapping.items():
        if role not in IDENTITIES:
            raise ValueError("unknown identity role: %s" % role)
        expected_sha, expected_path = IDENTITIES[role]
        if sha != expected_sha:
            raise ValueError("identity drift for %s: %s" % (role, sha))
        if obj_path != expected_path:
            raise ValueError("identity object drift for %s: %s" % (role, obj_path))
        if sha in seen:
            raise ValueError(
                "identity collision: %s and %s share %s" % (seen[sha], role, sha)
            )
        seen[sha] = role
    if len(mapping) != len(IDENTITIES):
        raise ValueError("identity table incomplete")
    return dict(mapping)


def assert_driver_divergence(repo_sha, staged_sha):
    """Repo-current and staged-expected driver identities must both hold and differ."""
    if repo_sha == staged_sha:
        raise ValueError("divergence collapsed: repo and staged hashes are equal")
    if repo_sha != DRIVER_REPO_SHA:
        raise ValueError("repo driver identity drift: %s" % repo_sha)
    if staged_sha != DRIVER_STAGED_SHA:
        raise ValueError("staged driver identity drift: %s" % staged_sha)
    return True


def assert_frozen_driver_identity(rel_path, digest):
    """A frozen R1 driver copy must carry the immutable staged identity."""
    if digest != DRIVER_STAGED_SHA:
        raise ValueError("frozen driver identity drift: %s" % rel_path)
    return True


def event_total(breakdown):
    """The 72-event instrumentation total with its pinned per-kind counts."""
    pinned = {
        "PreOutputs": 20,
        "PostOutputs": 20,
        "PreDerivatives": 16,
        "PostDerivatives": 16,
    }
    if breakdown != pinned:
        raise ValueError("event breakdown drift: %r" % (breakdown,))
    total = sum(breakdown.values())
    if total != 72:
        raise ValueError("event total drift: expected 72, observed %d" % total)
    return total


def assert_disjoint(delta_paths, forbidden_exact, forbidden_prefixes):
    """No delta path may equal a forbidden path or fall under a forbidden prefix."""
    clashes = []
    for path in delta_paths:
        normalized = path.replace(os.sep, "/")
        if normalized in forbidden_exact:
            clashes.append(normalized)
        for prefix in forbidden_prefixes:
            if normalized.startswith(prefix):
                clashes.append(normalized)
    if clashes:
        raise ValueError("delta intersects forbidden set: %s" % sorted(set(clashes)))
    return True


def hex_bits(hex_str):
    """The raw 64-bit pattern of an IEEE-754 double hex string."""
    return int(hex_str, 16)


def ordered_bits(bits):
    """Map a sign-magnitude bit pattern onto the total IEEE-754 ordering."""
    return bits if bits < (1 << 63) else (1 << 64) - bits


def ulp_distance(hex_a, hex_b):
    """IEEE-754 ULP distance between two double hex patterns."""
    return abs(ordered_bits(hex_bits(hex_a)) - ordered_bits(hex_bits(hex_b)))


def decode_double(hex_str):
    """Decode a double hex pattern to its exact Python float value."""
    return struct.unpack(">d", struct.pack(">Q", int(hex_str, 16)))[0]


def is_normal_double(value):
    """True iff value is a finite, non-zero, normal (not subnormal) double."""
    return (
        math.isfinite(value)
        and value != 0.0
        and abs(value) >= DOUBLE_MIN_NORMAL
    )


def extract_stage_ulp(cmp_v2):
    """Map (block, stage, field, index) -> (reference_hex, target_hex)."""
    observed = {}
    for blk in cmp_v2["blocks"]:
        for sd in blk["stage_differences"]:
            key = (blk["block"], sd["stage"], sd["field"], sd["index"])
            observed[key] = (sd["reference_hex"], sd["target_hex"])
    return observed


def extract_final_ulp(cmp_v2):
    """Map (block, index) -> (reference_hex, target_hex) for final states."""
    observed = {}
    for blk in cmp_v2["blocks"]:
        for fd in blk["final_state_differences"]:
            observed[(blk["block"], fd["index"])] = (
                fd["reference_hex"],
                fd["target_hex"],
            )
    return observed


def check_pinned_ulp(observed, pinned):
    """Observed hex pairs must equal the pinned pairs and ULP distances."""
    if set(observed) != set(pinned):
        drift = set(observed) ^ set(pinned)
        raise ValueError("ulp key set drift: %s" % sorted(map(repr, drift)))
    for key, (want_dist, want_ref_hex, want_tgt_hex) in pinned.items():
        ref_hex, tgt_hex = observed[key]
        if (ref_hex, tgt_hex) != (want_ref_hex, want_tgt_hex):
            raise ValueError(
                "ulp hex drift for %s: %s -> %s" % (key, ref_hex, tgt_hex)
            )
        dist = ulp_distance(ref_hex, tgt_hex)
        if dist != want_dist:
            raise ValueError(
                "ulp distance drift for %s: expected %d, observed %d"
                % (key, want_dist, dist)
            )
    return True


def assert_earliest_divergence(cmp_v2):
    """The unique minimum-stage difference must be p,q/r stage2 derivatives[1]."""
    items = []
    for blk in cmp_v2["blocks"]:
        for sd in blk["stage_differences"]:
            items.append((sd["stage"], blk["block"], sd["field"], sd["index"]))
    min_stage = min(item[0] for item in items)
    earliest = sorted(item for item in items if item[0] == min_stage)
    if earliest != [(2, BLOCK_PQR, "derivatives", 1)]:
        raise ValueError("earliest divergence drift: %s" % (earliest,))
    return True


def assert_all_difference_doubles_normal(cmp_v2):
    """Every recorded reference/target value must decode from its hex and be
    a normal (not subnormal) double — including the 3.46e-47 item."""
    for blk in cmp_v2["blocks"]:
        for sd in blk["stage_differences"]:
            for hex_str, value in (
                (sd["reference_hex"], sd["reference"]),
                (sd["target_hex"], sd["target"]),
            ):
                decoded = decode_double(hex_str)
                if decoded != value:
                    raise ValueError(
                        "hex/value mismatch at %s stage %d %s[%d]"
                        % (blk["block"], sd["stage"], sd["field"], sd["index"])
                    )
                if not is_normal_double(decoded):
                    raise ValueError(
                        "non-normal double at %s stage %d %s[%d]: %r"
                        % (blk["block"], sd["stage"], sd["field"], sd["index"], value)
                    )
    return True


def assert_ulp_delta_distinct_from_value(ref_value, delta):
    """A 1-ULP delta must be many orders of magnitude smaller than the
    differing double's own value magnitude."""
    if not abs(delta) * 1e12 < abs(ref_value):
        raise ValueError(
            "value magnitude not distinct from ULP delta: %r vs %r"
            % (ref_value, delta)
        )
    return True


def assert_value_magnitude_not_ulp_delta(cmp_v2):
    """The earliest divergence double's value magnitude (-4.95e-18) must be
    orders of magnitude larger than its 1-ULP delta (~ -7.7e-34)."""
    blk = next(b for b in cmp_v2["blocks"] if b["block"] == BLOCK_PQR)
    sd = next(
        s
        for s in blk["stage_differences"]
        if (s["stage"], s["field"], s["index"]) == (2, "derivatives", 1)
    )
    ref = decode_double(sd["reference_hex"])
    tgt = decode_double(sd["target_hex"])
    if ref != EARLIEST_VALUE:
        raise ValueError("earliest divergence value drift: %r" % ref)
    one_ulp_delta = tgt - ref
    if not 0 < abs(one_ulp_delta) < 1e-33:
        raise ValueError("one-ULP delta out of range: %r" % one_ulp_delta)
    return assert_ulp_delta_distinct_from_value(ref, one_ulp_delta)


def git(*args, check=True):
    return subprocess.run(
        ["git"] + list(args),
        cwd=REPO_ROOT,
        capture_output=True,
        check=check,
    )


def head_tree_paths(*pathspecs):
    result = git("ls-tree", "-r", "--name-only", "HEAD", "--", *pathspecs)
    return set(result.stdout.decode("utf-8").splitlines())


def head_has_path(rel_path):
    result = git("cat-file", "-e", "HEAD:%s" % rel_path, check=False)
    return result.returncode == 0


def head_blob_bytes(rel_path):
    result = git("cat-file", "blob", "HEAD:%s" % rel_path)
    return result.stdout


def disk_files_under(rel_dir):
    """All files on disk under rel_dir as forward-slash repo-relative paths."""
    found = set()
    base = os.path.join(REPO_ROOT, rel_dir)
    for root, _dirs, names in os.walk(base):
        for name in names:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
            found.add(rel)
    return found


def is_ignored(rel_path):
    result = git("check-ignore", "-q", "--", rel_path, check=False)
    return result.returncode == 0


# --------------------------------------------------------------------------
# Positive tests
# --------------------------------------------------------------------------

class TestCandidateBindings(unittest.TestCase):
    def test_reference_review_binding(self):
        raw = bind_doc(REF_REL, REF_SHA, REF_SIZE)
        self.assertEqual(len(raw), REF_SIZE)
        self.assertIn("参考端首步证据独立审查", raw.decode("utf-8"))

    def test_comparison_review_binding(self):
        raw = bind_doc(CMP_REL, CMP_SHA, CMP_SIZE)
        self.assertEqual(len(raw), CMP_SIZE)
        self.assertIn("首步两端对照独立审查", raw.decode("utf-8"))

    def test_ingest_note_binding(self):
        raw = bind_doc(NOTE_REL, NOTE_SHA, NOTE_SIZE)
        self.assertEqual(len(raw), NOTE_SIZE)
        text = raw.decode("utf-8")
        self.assertIn("历史语境绑定与取代登记", text)
        # The note binds its own writing HEAD and both ancestor pins.
        self.assertIn(NOTE_HEAD, text)
        self.assertIn("f333316e6efa6b299b4288a9d91fb2bccedfb9d6", text)
        self.assertIn("1c5656ed924020b3e626e68739caeeaef9f41a9e", text)


class TestComparisonV2Corrections(unittest.TestCase):
    def setUp(self):
        self.ref_text = read_repo_bytes(REF_REL).decode("utf-8")
        self.cmp_text = read_repo_bytes(CMP_REL).decode("utf-8")
        self.note_text = read_repo_bytes(NOTE_REL).decode("utf-8")

    def test_two_retractions_and_create_new_boundary(self):
        # B retracts A's staged-copy claim: the probe calls neither the repo
        # nor the staged driver; the False entry is the honest
        # unused_changed_driver record.
        require_phrases(
            self.cmp_text,
            [
                '~~"本次执行用的是 staged 副本"~~ 错误',
                "既不调用仓库也不调用",
                "unused_changed_driver",
            ],
            "comparison retraction 1",
        )
        require_phrases(
            self.note_text,
            [
                "comparison-v2 更正 reference review 两处错误",
                "unused_changed_driver",
                "登记为已变更且未使用",
                "既不调用仓库也不调用 staged 的",
            ],
            "note retraction 1",
        )
        # B completes A's content-only claim: order index strictly
        # distinguishes the two same-time 0.0005 observations.
        require_phrases(
            self.cmp_text,
            [
                '~~"只能按内容区分"~~ 不完整',
                "可由序位严格区分",
                "内容差异另存为佐证",
            ],
            "comparison retraction 2",
        )
        require_phrases(
            self.note_text,
            ["可由序位（order index）严格区分"],
            "note retraction 2",
        )
        # A's original claims remain present as the retracted historical record.
        require_phrases(
            self.ref_text,
            ["本次执行用的是 staged 副本", "只能靠内容区分"],
            "reference original claims",
        )
        # CREATE_NEW half-write boundary kept as intentional evidence.
        require_phrases(
            self.cmp_text,
            ["CREATE_NEW 半成品边界属", "有意保留证据", "不再建议覆盖原路径"],
            "comparison create-new boundary",
        )
        require_phrases(self.note_text, ["有意保留证据"], "note create-new boundary")


class TestIdentities(unittest.TestCase):
    def setUp(self):
        self.cmp_text = read_repo_bytes(CMP_REL).decode("utf-8")
        self.note_text = read_repo_bytes(NOTE_REL).decode("utf-8")

    def test_three_artifact_identities(self):
        table = validate_identity_table(IDENTITIES)
        self.assertEqual(len(table), 3)
        # The note renders each object path relative to its evidence directory.
        note_path_renderings = {
            "reference_sha256": "g6-reference-probe-20260913/run-03/reference-first-step.json",
            "target_trace_sha256": "g6-target-first-step-20260913/first-step-trace.jsonl",
            "with_major_variant_sha256": "with-major/first-step-trace.jsonl",
        }
        for role, (sha, _obj_path) in table.items():
            self.assertIn(sha, self.note_text, role)
            self.assertIn(note_path_renderings[role], self.note_text, role)
        # The top-level trace is distinguished from the with-major variant.
        self.assertIn("**顶层**", self.note_text)
        # The comparison review pins the same identities by short prefix and
        # forbids mixing the top-level trace with the with-major variant.
        for prefix in ("99fc1ec8", "34350997", "d55542d7"):
            self.assertIn(prefix, self.cmp_text)
        require_phrases(
            self.cmp_text,
            ["两者身份不同但 v2 引用对象明确无误"],
            "comparison identity distinction",
        )
        require_phrases(self.note_text, ["不得混用"], "note identity distinction")


class TestInstrumentation(unittest.TestCase):
    def setUp(self):
        self.ref_text = read_repo_bytes(REF_REL).decode("utf-8")
        self.cmp_text = read_repo_bytes(CMP_REL).decode("utf-8")
        self.note_text = read_repo_bytes(NOTE_REL).decode("utf-8")

    def test_instrumentation_counts(self):
        self.assertEqual(
            event_total(
                {
                    "PreOutputs": 20,
                    "PostOutputs": 20,
                    "PreDerivatives": 16,
                    "PostDerivatives": 16,
                }
            ),
            72,
        )
        # PostDerivatives timing distribution: 4 + 8 + 4 = 16.
        self.assertEqual(4 + 8 + 4, 16)
        # Major outputs: (30 + 30 + 60) sensor/GPS/vehicle rows x 2 = 240 f64.
        self.assertEqual((30 + 30 + 60) * 2, 240)
        require_phrases(
            self.note_text,
            [
                "72 = PreOutputs 20 + PostOutputs 20 + PreDerivatives 16 + PostDerivatives 16",
                "dropped=0",
                "PostDerivatives 时点分布 0×4、0.0005×8、0.001×4",
                "240 个 f64 全核",
                "legacy_target_bit_mismatches=[]",
                "parse_int=Decimal",
                "保全 `-0` 符号",
            ],
            "note instrumentation",
        )
        require_phrases(
            self.ref_text,
            ["72 = PreOutputs 20 + PostOutputs 20 + PreDerivatives 16 + PostDerivatives 16"],
            "reference instrumentation",
        )
        require_phrases(
            self.cmp_text,
            ["legacy_target_bit_mismatches=[]"],
            "comparison instrumentation",
        )

    def test_stage_order_and_final_state_selection(self):
        require_phrases(
            self.note_text,
            [
                "stage0(0)→stage1(0.0005)→stage2(0.0005)→stage3(0.001)→**ode4_update(0.001)**",
                "v2 末态取最后 0.001（update，RK4 积分终态），不取第四级 minor",
            ],
            "note stage order",
        )
        require_phrases(
            self.cmp_text,
            ["stage0(0)", "ode4_update(0.001)", "保留未删", "v1 用首个", "v2 改取最后一个"],
            "comparison stage order and v1/v2 supersession",
        )

    def test_earliest_divergence_chain(self):
        require_phrases(
            self.note_text,
            [
                "跨块最早差异：p,q,r 块 stage2 `derivatives[1]`（0 基）1 ULP",
                "bc56d4db33a987b8",
                "4.95e-18",
                "stage3 传播",
                "差异源未定",
            ],
            "note earliest divergence",
        )
        require_phrases(
            self.cmp_text,
            ["p,q,r 块 stage2", "bc56d4db33a987b8", "1 ULP"],
            "comparison earliest divergence",
        )


class TestComparisonV2UlPFacts(unittest.TestCase):
    """Recompute IEEE-754 ULP distances from the tracked comparison-v2.json.

    Pinned facts: earliest p,q/r stage2 derivatives[1] = 1 ULP; q stage3
    derivatives[2] = 1 ULP and derivatives[3] = 64 ULP; q final state
    index3 = 44 ULP; p,q,r stage3 cont_states[1] and ub,vb,wb stage3
    derivatives[0] each 1 ULP; ub,vb,wb final index0 1 ULP. 3.46e-47 is a
    normal double; -4.95e-18 is the value magnitude, not the ULP delta.
    """

    def setUp(self):
        self.raw = bind_doc(CMP_V2_REL, CMP_V2_SHA, CMP_V2_SIZE)
        # The artifact must be the tracked HEAD blob (index-independent check).
        self.assertEqual(head_blob_bytes(CMP_V2_REL), self.raw)
        self.cmp_v2 = json.loads(self.raw.decode("utf-8"))
        self.cmp_text = read_repo_bytes(CMP_REL).decode("utf-8")
        self.note_text = read_repo_bytes(NOTE_REL).decode("utf-8")

    def test_pinned_stage_ulp_distances(self):
        check_pinned_ulp(extract_stage_ulp(self.cmp_v2), PINNED_STAGE_ULP)

    def test_pinned_final_state_ulp_distances(self):
        check_pinned_ulp(extract_final_ulp(self.cmp_v2), PINNED_FINAL_ULP)

    def test_earliest_divergence_is_pqr_stage2_derivatives1(self):
        assert_earliest_divergence(self.cmp_v2)

    def test_all_difference_doubles_are_normal(self):
        assert_all_difference_doubles_normal(self.cmp_v2)
        # The 3.46e-47 item specifically: normal, not subnormal.
        value = decode_double("36494aa6d36ff400")
        self.assertEqual(value, 3.461044095416801e-47)
        self.assertTrue(is_normal_double(value))
        self.assertGreater(abs(value), DOUBLE_MIN_NORMAL)

    def test_value_magnitude_distinct_from_ulp_delta(self):
        assert_value_magnitude_not_ulp_delta(self.cmp_v2)

    def test_no_zero_difference_in_xyz_block(self):
        for blk in self.cmp_v2["blocks"]:
            if blk["block"] == BLOCK_XYZ:
                self.assertEqual(blk["stage_difference_count"], 0)
                self.assertEqual(blk["stage_differences"], [])
                self.assertEqual(blk["final_state_differences"], [])

    def test_docs_state_corrected_precision(self):
        # Both edited documents must carry the corrected 1/64/44 chain and
        # the normal-double / value-magnitude wording.
        for text, label in ((self.cmp_text, "comparison"), (self.note_text, "note")):
            require_phrases(
                text,
                [
                    "64 ULP",
                    "44 ULP",
                    "36494aa6d36ff400",
                    "36494aa6d36ff3c0",
                    "3581440763f7c6a8",
                    "3581440763f7c67c",
                    "值量级",
                    "不存在",
                ],
                "%s corrected precision" % label,
            )
        require_phrases(
            self.cmp_text,
            ["规格化（normal）"],
            "comparison normal-double wording",
        )
        require_phrases(
            self.note_text,
            ["规格化（normal）double"],
            "note normal-double wording",
        )
        # The retracted "all later propagation is 1 ULP" claim form and the
        # subnormal mischaracterization must be gone from B.
        forbid_phrases(
            self.cmp_text,
            ["（均 1 ULP", "次正规"],
            "comparison retracted precision claim",
        )
        # The ingest note must register the supersession of the old B bytes.
        require_phrases(
            self.note_text,
            ["8b222e1d1d93ab6710b0e7bb887b3d46203f0053f7f6516457f45e15a0a1a5e6"],
            "note old-B supersession registration",
        )

    def test_note_states_v3_dir_cannot_be_tracked_anchor(self):
        require_phrases(
            self.note_text,
            [
                "ds-g6-major-time-binding-20260913-01/",
                "未跟踪且被忽略",
                "不能作为 tracked 锚",
                "离线复现仅依赖本地留存",
            ],
            "note v3-dir untracked-anchor boundary",
        )
        # The v3 directory really is untracked and ignored at this checkout.
        self.assertFalse(head_tree_paths("validation/coordination/ds-g6-major-time-binding-20260913-01"))
        self.assertTrue(
            is_ignored(
                "validation/coordination/ds-g6-major-time-binding-20260913-01/README.md"
            )
        )


class TestDriverDivergence(unittest.TestCase):
    def setUp(self):
        self.cmp_text = read_repo_bytes(CMP_REL).decode("utf-8")
        self.note_text = read_repo_bytes(NOTE_REL).decode("utf-8")

    def test_unused_driver_divergence_current_vs_staged(self):
        # The divergence is real: the working-tree driver is the repo-current
        # identity, not the staged-expected one recorded by execution-03.
        self.assertEqual(sha256_hex(read_repo_bytes(DRIVER_REL)), DRIVER_REPO_SHA)
        assert_driver_divergence(DRIVER_REPO_SHA, DRIVER_STAGED_SHA)
        require_phrases(
            self.note_text,
            [
                DRIVER_REPO_SHA,
                DRIVER_STAGED_SHA,
                "unused_changed_driver",
                "登记为已变更且未使用",
                "该分歧**未影响本次被对照的运行**",
            ],
            "note driver divergence",
        )
        require_phrases(
            self.cmp_text,
            ["unused_changed_driver", "既不调用仓库也不调用"],
            "comparison driver non-use",
        )

    def test_owner_ruling_encoded_not_pending(self):
        # The former live two-option passage ("update staged or backfill
        # repo, pending owner ruling") is superseded and must be gone; the
        # encoded ruling must be present in exact, safe terms.
        forbid_phrases(
            self.note_text,
            [
                "待 owner 裁定",
                "是更新 staged 还是回填仓库",
                "应更新冻结副本",
                "应回填仓库",
                "授权更新冻结副本",
                "授权回填仓库",
            ],
            "note owner ruling: superseded two-option / destructive authorization",
        )
        require_phrases(
            self.note_text,
            [
                "owner 裁定已下",
                "既不更新冻结副本，也不回填仓库，两者均未获授权",
                "明确取代",
                "不可变证据",
                "是**当前源**",
                "恰差一个类型门与一次 float 强转",
                DRIVER_BLOB,
                DRIVER_COMMIT,
                "unused_changed_driver",
                "非缺陷",
                "不影响 R1 证据",
                "不影响首步对照证据",
                "R1 时期的历史身份",
                "不是当前仓库 pin",
                "启动时重算并记录其 SHA",
                "快照",
                "只关闭 owner-ruling 子议题",
                "不构成 G6/Full 通过",
                "23 个状态",
                "ode4_stage_mapping",
                "native/full-window",
                "issue 83 不重跑",
            ],
            "note owner ruling encoding",
        )
        # §6 must close the divergence by ruling, not by mutation.
        require_phrases(
            self.note_text,
            [
                "已由 owner 裁定闭合",
                "不更新冻结副本、不回填仓库、不单方",
                "以裁定而非字节变更闭合",
            ],
            "note section-6 ruling closure",
        )

    def test_frozen_driver_copies_immutable_evidence(self):
        # The frozen R1 driver copies must exist on disk with the staged
        # identity in all three conformance evidence locations; they are
        # immutable evidence of what executed and are never mutated here.
        for rel_path in FROZEN_DRIVER_PATHS:
            assert_frozen_driver_identity(
                rel_path, sha256_hex(read_repo_bytes(rel_path))
            )

    def test_repo_driver_blob_and_commit_identity(self):
        # The repo-current driver's HEAD blob is 1cedff93... and that blob
        # was committed in 3f40ba03 (index-independent checks).
        result = git("ls-tree", "HEAD", "--", DRIVER_REL)
        entry = result.stdout.decode("utf-8").split()
        self.assertEqual(entry[2], DRIVER_BLOB)
        result = git("ls-tree", DRIVER_COMMIT, "--", DRIVER_REL)
        entry = result.stdout.decode("utf-8").split()
        self.assertEqual(entry[2], DRIVER_BLOB)

    def test_driver_diff_is_exactly_type_gate_and_float_cast(self):
        # Frozen copy vs repo-current driver: exactly two differing lines —
        # the type gate and the float cast — nothing else.
        frozen = (
            read_repo_bytes(FROZEN_DRIVER_PATHS[0]).decode("utf-8").splitlines()
        )
        current = read_repo_bytes(DRIVER_REL).decode("utf-8").splitlines()
        self.assertEqual(len(frozen), len(current))
        differing = [
            i for i in range(len(frozen)) if frozen[i] != current[i]
        ]
        self.assertEqual(differing, [136, 147])
        self.assertIn("math.isfinite(x) for x in values", frozen[136])
        self.assertIn("type(x) in (int, float)", current[136])
        self.assertNotIn("type(x) in (int, float)", frozen[136])
        self.assertIn(
            "x = sample['major_root_outputs'][name][index]", frozen[147]
        )
        self.assertIn(
            "x = float(sample['major_root_outputs'][name][index])",
            current[147],
        )


class TestGitAnchors(unittest.TestCase):
    def test_required_tracked_g6_anchors_and_evidence_dirs(self):
        for rel_path in REQUIRED_TRACKED_ANCHORS:
            self.assertTrue(
                head_has_path(rel_path), "not tracked at HEAD: %s" % rel_path
            )
        tree = head_tree_paths(*EVIDENCE_DIRS)
        self.assertEqual(len(tree), EVIDENCE_TRACKED_COUNT)
        disk = set()
        for rel_dir in EVIDENCE_DIRS:
            self.assertTrue(
                os.path.isdir(os.path.join(REPO_ROOT, rel_dir)),
                "evidence dir missing on disk: %s" % rel_dir,
            )
            disk |= disk_files_under(rel_dir)
        missing_from_disk = sorted(tree - disk)
        self.assertEqual(
            missing_from_disk, [], "tracked evidence files absent on disk"
        )
        extras = sorted(disk - tree)
        unignored = [path for path in extras if not is_ignored(path)]
        self.assertEqual(
            unignored,
            [],
            "untracked-and-unignored residue under evidence dirs: %s" % unignored,
        )
        # The note's gitignore citation and tracked-count claim bind verbatim.
        note_text = read_repo_bytes(NOTE_REL).decode("utf-8")
        require_phrases(
            note_text,
            [".gitignore:53", "101 个跟踪文件"],
            "note evidence-dir claims",
        )
        gitignore_lines = (
            read_repo_bytes(".gitignore").decode("utf-8").splitlines()
        )
        self.assertEqual(gitignore_lines[52].strip(), "/validation/*/")

    def test_delta_e2ecd62e_to_01181887_disjoint(self):
        result = git("diff", "--name-only", NOTE_HEAD, REVIEW_HEAD)
        delta = result.stdout.decode("utf-8").splitlines()
        self.assertTrue(delta, "delta between the two pinned commits is empty")
        assert_disjoint(delta, DELTA_FORBIDDEN_EXACT, DELTA_FORBIDDEN_PREFIXES)

    def test_symbolic_head_ancestors(self):
        # Symbolic-HEAD ancestry only: no HEAD-equality assertion anywhere.
        result = git("rev-parse", "--verify", "HEAD^{commit}")
        self.assertTrue(result.stdout.decode("utf-8").strip())
        for sha in ANCESTOR_SHAS:
            ancestry = git(
                "merge-base", "--is-ancestor", sha, "HEAD", check=False
            )
            self.assertEqual(
                ancestry.returncode, 0, "%s is not an ancestor of HEAD" % sha
            )


class TestScopeAndBoundaries(unittest.TestCase):
    def setUp(self):
        self.ref_text = read_repo_bytes(REF_REL).decode("utf-8")
        self.cmp_text = read_repo_bytes(CMP_REL).decode("utf-8")
        self.note_text = read_repo_bytes(NOTE_REL).decode("utf-8")

    def test_scope_13_of_36_not_full_model(self):
        require_phrases(
            self.note_text,
            [
                "36 个连续状态中 **13 个已映射刚体状态**",
                "23 个未覆盖",
                "13/36 不构成全模型一致，也不构成 G6 通过",
            ],
            "note scope",
        )
        require_phrases(
            self.cmp_text,
            ["36 连续状态中 13 个已映射", "23 个状态未覆盖", "仅 13/36 状态已对照"],
            "comparison scope",
        )

    def test_timing_premises_and_anchors(self):
        require_phrases(
            self.note_text,
            [
                "1ms 物理精确 major 步（相位 `k*0.001`，501/501 核验）",
                "RK4 每 major 4 个 minor 阶段（4-tick",
                "0/0.0005/0.0005/0.001",
                "不追赶补发",
                "超 100ms 迟到冻结撤销且显式恢复",
                "全窗（full-window）口径",
                "ds-g6-major-time-binding",
                "docs/2026-09-07_joint-rate-contract-proposal.md:58",
            ],
            "note timing premises",
        )
        anchor_lines = (
            read_repo_bytes("docs/2026-09-07_joint-rate-contract-proposal.md")
            .decode("utf-8")
            .splitlines()
        )
        line58 = anchor_lines[57]
        self.assertTrue(line58.startswith("建议只问一条"))
        for phrase in ("不追赶补发", "超100ms迟到冻结撤销且显式恢复", "1ms物理精确性"):
            self.assertIn(phrase, line58)

    def test_ap_px4_separation_and_missing_ability_row(self):
        require_phrases(
            self.note_text,
            [
                "不同载具、不同物理与不同身份",
                "永不合并",
                "AP 0.905m 正常下降",
                "PX4 已落地",
                "能力证明行仍 MISSING",
                "omp-mixed-failure-review-20260913.md:59",
                "本场为诊断证据",
            ],
            "note AP/PX4 and MISSING row",
        )

    def test_stage_mapping_and_event72_not_g6_pass(self):
        unverified = (
            "ode4_stage_mapping: unverified; event order alone is not a solver-stage proof"
        )
        self.assertIn(unverified, self.ref_text)
        self.assertIn(unverified, self.note_text)
        self.assertIn("不得仅以事件数（72）宣称 G6 通过", self.ref_text)
        self.assertIn("事件数 72 不是 G6 通过", self.note_text)

    def test_xtj8wk8i_never_issue83_evidence(self):
        require_phrases(
            self.note_text,
            [
                "xtj8wk8i 永不充当 issue 83 证据",
                "诊断/probe 场永不得充当 #83 通过证据",
                "1w6dru32",
                "通过并 CLOSED",
                "issue 83 不重跑",
            ],
            "note xtj8wk8i / issue-83 boundary",
        )

    def test_historical_only_no_authority_no_rerun(self):
        require_phrases(
            self.note_text,
            [
                "historical context only",
                "它自身不构成 G6 的验收、批准、收口、复核或任何重跑许可",
                "基于**当下**的工件重新作出",
                '读作"现在是什么状态"',
                "不得据此重跑任何场或 issue 83",
                "不得以事件数、单点差异或 13/36 覆盖推断全模型一致",
            ],
            "note historical-only semantics",
        )


# --------------------------------------------------------------------------
# Negative tests (in-memory mutations only; no file is modified)
# --------------------------------------------------------------------------

class TestMutationNegatives(unittest.TestCase):
    def setUp(self):
        self.ref_raw = read_repo_bytes(REF_REL)
        self.note_text = read_repo_bytes(NOTE_REL).decode("utf-8")
        self.cmp_text = read_repo_bytes(CMP_REL).decode("utf-8")
        result = git("diff", "--name-only", NOTE_HEAD, REVIEW_HEAD)
        self.delta = result.stdout.decode("utf-8").splitlines()
        self.stage_observed = extract_stage_ulp(json.loads(
            read_repo_bytes(CMP_V2_REL).decode("utf-8")
        ))
        self.final_observed = extract_final_ulp(json.loads(
            read_repo_bytes(CMP_V2_REL).decode("utf-8")
        ))

    def test_mutation_negatives(self):
        # Byte drift must fail hash binding.
        with self.assertRaisesRegex(ValueError, "hash drift"):
            check_binding(
                self.ref_raw.replace(b"run-03", b"run-04XXXXXXX"),
                REF_SHA,
                REF_SIZE,
                REF_REL,
            )
        # Size drift must fail size binding.
        with self.assertRaisesRegex(ValueError, "size drift"):
            check_binding(self.ref_raw, REF_SHA, REF_SIZE + 1, REF_REL)
        # Swapping the with-major identity into the top-level trace slot must fail.
        swapped = {
            "reference_sha256": IDENTITIES["reference_sha256"],
            "target_trace_sha256": IDENTITIES["with_major_variant_sha256"],
            "with_major_variant_sha256": IDENTITIES["target_trace_sha256"],
        }
        with self.assertRaisesRegex(ValueError, "identity drift"):
            validate_identity_table(swapped)
        # A collapsed divergence (equal hashes) must fail.
        with self.assertRaisesRegex(ValueError, "collapsed"):
            assert_driver_divergence(DRIVER_REPO_SHA, DRIVER_REPO_SHA)
        # A wrong repo slot must fail the repo identity check.
        with self.assertRaisesRegex(ValueError, "repo driver identity drift"):
            assert_driver_divergence(DRIVER_STAGED_SHA, "0" * 64)
        # Injecting a bound document into the delta must break disjointness.
        with self.assertRaisesRegex(ValueError, "forbidden set"):
            assert_disjoint(
                self.delta + [REF_REL],
                DELTA_FORBIDDEN_EXACT,
                DELTA_FORBIDDEN_PREFIXES,
            )
        # Injecting a path under a forbidden prefix must break disjointness.
        with self.assertRaisesRegex(ValueError, "forbidden set"):
            assert_disjoint(
                self.delta
                + ["validation/coordination/g6-target-first-step-20260913/x.json"],
                DELTA_FORBIDDEN_EXACT,
                DELTA_FORBIDDEN_PREFIXES,
            )
        # An mutated event breakdown must fail both shape and total checks.
        with self.assertRaisesRegex(ValueError, "event breakdown drift"):
            event_total(
                {
                    "PreOutputs": 20,
                    "PostOutputs": 20,
                    "PreDerivatives": 16,
                    "PostDerivatives": 15,
                }
            )
        # Stripping a required boundary phrase must fail the phrase check.
        stripped = self.note_text.replace("historical context only", "elided")
        with self.assertRaisesRegex(ValueError, "missing required phrase"):
            require_phrases(stripped, ["historical context only"], "mutation")
        # Stripping the driver divergence record must fail the phrase check.
        stripped2 = self.note_text.replace("unused_changed_driver", "elided")
        with self.assertRaisesRegex(ValueError, "missing required phrase"):
            require_phrases(stripped2, ["unused_changed_driver"], "mutation")
        # Re-injecting the superseded live two-option wording into the note
        # must trip the forbidden-phrase check.
        with self.assertRaisesRegex(ValueError, "forbidden phrase"):
            forbid_phrases(
                self.note_text + "（是更新 staged 还是回填仓库，待 owner 裁定）",
                ["待 owner 裁定", "是更新 staged 还是回填仓库"],
                "mutation",
            )
        # Re-injecting a destructive authorization must trip the check.
        with self.assertRaisesRegex(ValueError, "forbidden phrase"):
            forbid_phrases(
                self.note_text + "（授权回填仓库）",
                ["授权回填仓库"],
                "mutation",
            )
        # Stripping the ruling's no-update/no-backfill clause must fail.
        stripped3 = self.note_text.replace(
            "既不更新冻结副本，也不回填仓库，两者均未获授权", "elided"
        )
        with self.assertRaisesRegex(ValueError, "missing required phrase"):
            require_phrases(
                stripped3,
                ["既不更新冻结副本，也不回填仓库，两者均未获授权"],
                "mutation",
            )
        # A frozen driver copy that drifted from the R1 identity must fail
        # the immutable-evidence binding (in-memory; no file is touched).
        with self.assertRaisesRegex(ValueError, "frozen driver identity drift"):
            assert_frozen_driver_identity(FROZEN_DRIVER_PATHS[0], "0" * 64)

    def test_ulp_mutation_negatives(self):
        # A one-bit mutation of the 64-ULP target hex must fail hex pinning.
        mutated = dict(self.stage_observed)
        mutated[(BLOCK_Q, 3, "derivatives", 3)] = (
            "36494aa6d36ff400",
            "36494aa6d36ff301",
        )
        with self.assertRaisesRegex(ValueError, "ulp hex drift"):
            check_pinned_ulp(mutated, PINNED_STAGE_ULP)
        # A wrong pinned distance (43 instead of 44) must fail distance check.
        bad_pin = {(BLOCK_Q, 3): (43, "3581440763f7c6a8", "3581440763f7c67c")}
        with self.assertRaisesRegex(ValueError, "ulp distance drift"):
            check_pinned_ulp(
                {(BLOCK_Q, 3): ("3581440763f7c6a8", "3581440763f7c67c")}, bad_pin
            )
        # Dropping a pinned item must fail the key-set check.
        dropped = {
            k: v
            for k, v in self.final_observed.items()
            if k != (BLOCK_V, 0)
        }
        with self.assertRaisesRegex(ValueError, "ulp key set drift"):
            check_pinned_ulp(dropped, PINNED_FINAL_ULP)
        # Recomputing the 64-ULP item honestly must yield exactly 64; the
        # same one-bit flip must move the computed distance (mutating the
        # hex cannot preserve the pinned distance).
        self.assertEqual(
            ulp_distance("36494aa6d36ff400", "36494aa6d36ff3c0"), 64
        )
        self.assertEqual(
            ulp_distance("3581440763f7c6a8", "3581440763f7c67c"), 44
        )
        self.assertNotEqual(
            ulp_distance("36494aa6d36ff400", "36494aa6d36ff301"), 64
        )
        # A genuinely subnormal value must fail the normal-double check.
        self.assertFalse(is_normal_double(5e-324))
        with self.assertRaisesRegex(ValueError, "non-normal double"):
            assert_all_difference_doubles_normal(
                {
                    "blocks": [
                        {
                            "block": BLOCK_V,
                            "stage_differences": [
                                {
                                    "stage": 3,
                                    "field": "derivatives",
                                    "index": 0,
                                    "reference_hex": "0000000000000001",
                                    "target_hex": "0000000000000002",
                                    "reference": 5e-324,
                                    "target": 1e-323,
                                }
                            ],
                        }
                    ]
                }
            )
        # Re-injecting the retracted "（均 1 ULP" claim into B must fail the
        # forbidden-phrase check.
        with self.assertRaisesRegex(ValueError, "forbidden phrase"):
            forbid_phrases(
                self.cmp_text + "（均 1 ULP",
                ["（均 1 ULP"],
                "mutation",
            )
        # Recasting the value magnitude as the ULP delta must fail.
        with self.assertRaisesRegex(ValueError, "value magnitude"):
            assert_ulp_delta_distinct_from_value(
                EARLIEST_VALUE, EARLIEST_VALUE * 1e-6
            )


if __name__ == "__main__":
    unittest.main()
