"""Offline binding tests for the CodeBuddy architecture-applicability G6
erratum (2026-09-14).

Scope (pure Python, fully offline, no network, no native/build/MATLAB/ROS/
DDS/SITL/FC/UE/model/flight runs, no issue-83 rerun):

* Byte-bind the single candidate document by SHA256 and size:
  - docs/coordination/codebuddy-architecture-applicability-g6-erratum-20260914.md
* Byte-bind its exact sources and verify the erratum's claims against them:
  - applicability: parent CONTEXT-MAP.md carries the cited sentence
    "既有 ADR 不自动约束 wksim"; the erratum states that for wksim migration
    work the governing local authority is wksim/AGENTS.md, wksim/CONTEXT.md,
    the accepted wksim contracts, and the migration architecture, that parent
    ADRs do not automatically constrain wksim unless explicitly adopted,
    that parent ADR 0009/0014 are consistent guidance while
    0005/0010/0011/0016 contain assumptions not adopted by wksim, and that it
    never amends the parent ADRs.
  - authority: the committed G6 ingest note's proposal anchor
    (docs/2026-09-07_joint-rate-contract-proposal.md:58) is historical /
    non-authoritative; the authoritative gates are
    docs/2026-09-07_joint-rate-contract-accepted.md (line-anchored source
    checks: 1 ms tick, 4 ms barrier, four ticks, 0.5x/1x with 8 ms/4 ms group
    periods, no catch-up / no covert re-anchor except explicit recovery,
    >100 ms cumulative lateness latch with freeze-and-revoke, full-window
    10 s +-2% / 60 s +-1%), and the sealed immutable proposal copy
    (54dcd1df...) matches the accepted record's pin.
  - nonclaims: the erratum changes no gate, approves no architecture change,
    reruns no #83, and closes neither #84, G6, nor Full; its supersession is
    limited to the erroneous citation, not the old evidence bytes.
  - consumer rule: a compact three-step rule (authority order, gate
    citation, historical-evidence byte identity).
* Prove the committed G6 bytes remain unchanged: the ingest note
  (c7f03453.../14459 B), the committed context test, the independent-review
  -03 trio, and the context-ingest manifest -02 quartet are byte-bound and
  byte-equal to their HEAD blobs (no correction was applied in place).
* Git-side checks are symbolic-HEAD only: ancestry of f333316e and 31e5b65f
  via merge-base --is-ancestor; no HEAD-equality assertion anywhere.

Design constraints (staging-stable by construction):

* Every git invocation is index-independent (ls-tree / cat-file /
  merge-base / rev-parse of HEAD). Nothing inspects or fingerprints the
  shared real index: no `git status`, no `git ls-files`, no diff against the
  real index, no index hashing. The suite therefore passes both in the
  normal untracked mode and under a repo-external temporary GIT_INDEX_FILE
  in which exactly the two candidate files (the erratum document and this
  test) are force-added ("exact-two staging"). Staging itself is exercised
  by the runner, not by this suite (STAGING_PATHS documents the contract).
* Fail-closed point-in-time bindings are intentional: any byte drift in the
  candidate, its sources, or the committed G6 anchors must fail loudly.

Observed at writing HEAD acf322860831cb2a7c83a45cb4e2586922444c57, with
f333316e6efa6b299b4288a9d91fb2bccedfb9d6 and
31e5b65f5448c5558450d16d0f46da0ef0f0a03c verified as ancestors.
This erratum is documentation/context only and confers no authority,
approval, acceptance, closure, or rerun permission.
"""

import hashlib
import os
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_ROOT = os.path.dirname(REPO_ROOT)

ERRATUM_REL = (
    "docs/coordination/codebuddy-architecture-applicability-g6-erratum-20260914.md"
)
ERRATUM_SHA = "b2e1d34141a86080927e979df6cb048ebe667bace99bf422394f96c22fb52a20"
ERRATUM_SIZE = 7468

TEST_REL = "validation/test_codebuddy_architecture_applicability_g6_erratum.py"

# The two candidate files staged under a repo-external temporary
# GIT_INDEX_FILE (exact-two staging). Staging is exercised by the runner,
# never against the real index.
STAGING_PATHS = [ERRATUM_REL, TEST_REL]

NOTE_REL = "docs/coordination/omp-g6-first-step-ingest-note-20260914.md"
NOTE_SHA = "c7f034535096047e321ab654fac418d7de5775854ac0e5ff06d97db2369308bc"
NOTE_SIZE = 14459

ACCEPTED_REL = "docs/2026-09-07_joint-rate-contract-accepted.md"
ACCEPTED_SHA = "6a68840d3cb5612cba921468a370014b38e1416c81d6dc2c9c41ebc816ff71ab"
ACCEPTED_SIZE = 3200

PROPOSAL_REL = "docs/2026-09-07_joint-rate-contract-proposal.md"
PROPOSAL_SHA = "db4d0306ec813e9c01ae764bdefcee259bb74afc2e0583752e276270abb49962"
PROPOSAL_SIZE = 9125

SEALED_REL = "validation/joint-rate-contract-20260907/approved-proposal.md"
SEALED_SHA = "54dcd1df7d70caeb483ab101e7071f8d48168f29e22a93da594e455a459a02a5"
SEALED_SIZE = 8848

# Parent-repository sources (outside this repo; disk-hash bindings only).
PARENT_SOURCES = [
    ("../CONTEXT-MAP.md", "a52a4676905738e20384e27fa29bb0c9cbc8ad792ec9e89fd849795e9652ce20", 696),
    ("../docs/adr/0005-versioned-python-contract-with-an-optional-ros2-bridge.md",
     "9e952bc386fe0e5294d69190f398db65cf1bf4e1b6cbd5a3b8eef297e5b88a4d", 475),
    ("../docs/adr/0009-use-ned-frd-and-si-at-the-public-boundary.md",
     "08e30ff2306f6bc3e0efd1703179a890405ab4fa690e0c9fc4b4796312327f14", 411),
    ("../docs/adr/0010-pin-modern-gazebo-harmonic.md",
     "259af35765bba766429dac0eb838cc1cf95ecaa58639232d4069c277dfffc9a2", 352),
    ("../docs/adr/0011-pin-cosys-airsim-v3-3-and-unreal-5-5.md",
     "f330c7e9fba1b2317a13785f8aee7c0a6bc0c6971429033732e7b2420c7e96af", 357),
    ("../docs/adr/0014-compare-invariants-and-envelopes-not-identical-trajectories.md",
     "857f0cdf2ba5b5c3336cc5495cdbfa0d360a5eae4b756d8716bc45730477a387", 487),
    ("../docs/adr/0016-gazebo-authority-with-an-asynchronous-cosys-visual-mirror.md",
     "19d5aa4288fa827a5befcdc127b7f3c1bfc42bf31e2ee10fca5804a5342b0c56", 572),
]

# In-repo governance/architecture sources (tracked; HEAD blob equality also
# verified, index-independently).
GOV_SOURCES = [
    ("CONTEXT.md", "7932cda0d609c4de74a3df4cbc47553f8f7951fc3ae6c61319b9733dd2d512a2", 4804),
    ("AGENTS.md", "144d5157d37e90412840cb38b728581d66293f178a4645c93d3778447f4edac8", 5234),
    ("docs/architecture-implementation-20260912.md",
     "2c0d23b204b0cd70da9343106c4f3749f8adef56563cefdf39f0539706500d4d", 10627),
    ("docs/coordination/architecture-continuation-20260913.md",
     "665890489b087085d1bf143143b8ae7ddfa0a37af4d3506f3525c31372c1295d", 5470),
    (ACCEPTED_REL, ACCEPTED_SHA, ACCEPTED_SIZE),
    (PROPOSAL_REL, PROPOSAL_SHA, PROPOSAL_SIZE),
]

# Committed G6 first-step anchors whose bytes must remain unchanged.
G6_ANCHORS = [
    (NOTE_REL, NOTE_SHA, NOTE_SIZE),
    ("validation/test_omp_g6_first_step_context.py",
     "ef7e613b0781902a76f5b88ac383510eaa200599a7fb8a4ec7e4c9885eea25cf", 54340),
    ("validation/coordination/codebuddy-omp-g6-first-step-independent-review-20260914-03/SHA256SUMS",
     "288de5da0ff23daf3bea36dba8fab508404b013aa1cc16871da52f83ebee3f50", 154),
    ("validation/coordination/codebuddy-omp-g6-first-step-independent-review-20260914-03/review.md",
     "bd9ddbe4ddec784966819e53d29894cf52935faf25361b6f972dc748c706a169", 8917),
    ("validation/coordination/codebuddy-omp-g6-first-step-independent-review-20260914-03/review.json",
     "65cb4a8466d1665bed1ea47c48447b03e81b88956644d283a9ce13f997be5fb4", 6834),
    ("validation/coordination/omp-g6-first-step-context-ingest-manifest-20260914-02/SHA256SUMS",
     "71e73f3d1ec13152483debc9b5a9aaef4a250aa1b9f23682e637a3b4825c48d6", 236),
    ("validation/coordination/omp-g6-first-step-context-ingest-manifest-20260914-02/exact-paths.txt",
     "fb45e44a81391b3d2c8ebc0b4cd09d5df1545721b75cd92927e74bb736a5fdbb", 873),
    ("validation/coordination/omp-g6-first-step-context-ingest-manifest-20260914-02/review.md",
     "da6d9fc6c2f4cf827eb2f67bd37aea6a7126736ee29af99b4fa713d97a535fa8", 10596),
    ("validation/coordination/omp-g6-first-step-context-ingest-manifest-20260914-02/review.json",
     "d0ea41f588f9034e29beb144a4a3a5e664a5f5be6528967b08f93db5e64d5de3", 10618),
]

ANCESTOR_SHAS = [
    "f333316e6efa6b299b4288a9d91fb2bccedfb9d6",
    "31e5b65f5448c5558450d16d0f46da0ef0f0a03c",
]

# Line-anchored gate values inside the accepted record (0-based indexes).
ACCEPTED_LINE_GROUP_PERIOD = 9   # line 10: 1ms / 4ms / 0.5x-1x / 8ms-4ms
ACCEPTED_LINE_DEFAULT = 8        # line 9:  0.5x/1x, default 0.5x
ACCEPTED_LINE_LATCH = 11         # line 12: >100ms latch, freeze and revoke
ACCEPTED_LINE_FULLWINDOW = 13    # line 14: 10s +-2% / 60s +-1% / 100ms phase
ACCEPTED_LINE_RECOVERY = 22      # line 23: start-recovery-task amendment


def repo_path(rel_path):
    return os.path.join(REPO_ROOT, rel_path)


def parent_path(rel_path):
    # Parent-repository rel paths start with "../"; resolve from REPO_ROOT.
    return os.path.normpath(os.path.join(REPO_ROOT, rel_path))


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def sha256_hex(raw):
    return hashlib.sha256(raw).hexdigest()


def check_binding(raw, expected_sha, expected_size, label):
    digest = sha256_hex(raw)
    if digest != expected_sha:
        raise ValueError(
            "%s hash drift: expected %s, observed %s"
            % (label, expected_sha, digest)
        )
    if len(raw) != expected_size:
        raise ValueError(
            "%s size drift: expected %d, observed %d"
            % (label, expected_size, len(raw))
        )
    return digest


def bind_repo(rel_path, expected_sha, expected_size):
    raw = read_bytes(repo_path(rel_path))
    check_binding(raw, expected_sha, expected_size, rel_path)
    return raw


def bind_parent(rel_path, expected_sha, expected_size):
    raw = read_bytes(parent_path(rel_path))
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


def git(*args, check=True):
    return subprocess.run(
        ["git"] + list(args),
        cwd=REPO_ROOT,
        capture_output=True,
        check=check,
    )


def head_blob_bytes(rel_path):
    return git("cat-file", "blob", "HEAD:%s" % rel_path).stdout


# --------------------------------------------------------------------------
# Positive tests
# --------------------------------------------------------------------------

class TestCandidateBinding(unittest.TestCase):
    def test_erratum_byte_binding(self):
        raw = bind_repo(ERRATUM_REL, ERRATUM_SHA, ERRATUM_SIZE)
        text = raw.decode("utf-8")
        self.assertIn("架构适用性澄清与 G6 门引用勘误", text)
        self.assertIn("erratum，context-only", text)
        self.assertIn("acf322860831cb2a7c83a45cb4e2586922444c57", text)


class TestSourceBindings(unittest.TestCase):
    def test_parent_sources_bound(self):
        for rel, sha, size in PARENT_SOURCES:
            raw = bind_parent(rel, sha, size)
            self.assertEqual(len(raw), size)

    def test_governance_sources_bound_and_head_byte_equal(self):
        for rel, sha, size in GOV_SOURCES:
            raw = bind_repo(rel, sha, size)
            self.assertEqual(head_blob_bytes(rel), raw)

    def test_committed_g6_anchors_unchanged_and_head_byte_equal(self):
        for rel, sha, size in G6_ANCHORS:
            raw = bind_repo(rel, sha, size)
            self.assertEqual(head_blob_bytes(rel), raw)

    def test_sealed_proposal_copy_matches_accepted_pin(self):
        raw = bind_repo(SEALED_REL, SEALED_SHA, SEALED_SIZE)
        self.assertEqual(len(raw), SEALED_SIZE)


class TestApplicabilityWording(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.erratum = read_bytes(repo_path(ERRATUM_REL)).decode("utf-8")
        cls.context_map = read_bytes(
            parent_path("../CONTEXT-MAP.md")
        ).decode("utf-8")

    def test_context_map_carries_the_cited_sentence(self):
        self.assertIn("既有 ADR 不自动约束 wksim", self.context_map)
        self.assertIn("**AeroTwinSim → wksim**", self.context_map)

    def test_erratum_cites_context_map_and_local_authority(self):
        require_phrases(
            self.erratum,
            [
                "父仓库 `CONTEXT-MAP.md` 的关系原文为",
                "既有 ADR 不自动约束 wksim",
                "治理本地权威（governing local authority）",
                "`wksim/AGENTS.md`",
                "`wksim/CONTEXT.md`",
                "已获批准的 wksim 契约",
                "`docs/architecture-implementation-20260912.md`",
                "`docs/coordination/architecture-continuation-20260913.md`",
                "不自动约束 wksim，除非被 wksim 明确采纳",
                "explicitly adopted",
            ],
            "erratum applicability authority",
        )

    def test_erratum_registers_0009_0014_as_consistent_guidance(self):
        require_phrases(
            self.erratum,
            [
                "父 ADR 0009",
                "父 ADR 0014",
                "一致指引（consistent guidance，非自动约束）",
                "统一 SI/NED/FRD",
                "误差阈值",
            ],
            "erratum consistent-guidance registration",
        )

    def test_erratum_registers_0005_0010_0011_0016_as_not_adopted(self):
        require_phrases(
            self.erratum,
            [
                "父 ADR 0005",
                "父 ADR 0010",
                "父 ADR 0011",
                "父 ADR 0016",
                "assumptions not adopted by wksim",
                "未采纳其 gRPC",
                "未采纳 Gazebo Harmonic pin",
                "未采纳 Cosys-AirSim 后端",
                "ROS2/DDS",
            ],
            "erratum not-adopted registration",
        )

    def test_erratum_never_claims_to_amend_parent_adrs(self):
        forbid_phrases(
            self.erratum,
            ["修订父 ADR", "修改父 ADR", "取代父 ADR", "废止父 ADR"],
            "erratum no-parent-ADR-amendment",
        )
        require_phrases(
            self.erratum,
            ["不修订、不修改、不取代任何父 ADR"],
            "erratum explicit non-amendment statement",
        )


class TestAcceptedVsProposalAuthority(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.erratum = read_bytes(repo_path(ERRATUM_REL)).decode("utf-8")
        cls.accepted_lines = (
            read_bytes(repo_path(ACCEPTED_REL)).decode("utf-8").splitlines()
        )
        cls.proposal_lines = (
            read_bytes(repo_path(PROPOSAL_REL)).decode("utf-8").splitlines()
        )

    def test_proposal_is_historical_non_authoritative(self):
        self.assertIn("提案（未批准）", self.proposal_lines[0])
        require_phrases(
            self.erratum,
            [
                "该提案文档是历史文档（historical），自身不承载门权威",
                "其标题即\"提案（未批准）\"",
                "其批准状态由批准记录另行登记",
                "文献引用错误**（bibliographic error）",
            ],
            "erratum proposal status",
        )

    def test_erratum_names_the_erroneous_anchor_and_the_authority(self):
        require_phrases(
            self.erratum,
            [
                "`docs/coordination/omp-g6-first-step-ingest-note-20260914.md`",
                "docs/2026-09-07_joint-rate-contract-proposal.md:58",
                "当前权威的门出处是批准记录 `docs/2026-09-07_joint-rate-contract-accepted.md`",
                SEALED_SHA,
                "approved-proposal.md",
            ],
            "erratum anchor correction",
        )

    def test_accepted_record_line_anchors(self):
        # Line 10 (group period): 1 ms tick, 4 ms barrier, 0.5x/1x, 8/4 ms.
        line = self.accepted_lines[ACCEPTED_LINE_GROUP_PERIOD]
        for phrase in ("1ms", "4ms", "0.5×/1×", "8ms/4ms"):
            self.assertIn(phrase, line)
        # Line 9 (default tier).
        line = self.accepted_lines[ACCEPTED_LINE_DEFAULT]
        for phrase in ("0.5×、1×", "默认0.5×"):
            self.assertIn(phrase, line)
        # Line 12 (cumulative lateness latch).
        line = self.accepted_lines[ACCEPTED_LINE_LATCH]
        for phrase in ("超过100ms", "rate_unmet/resource_insufficient",
                       "冻结并撤销控制", "不自动降档、恢复或补发"):
            self.assertIn(phrase, line)
        # Line 14 (full-window budget).
        line = self.accepted_lines[ACCEPTED_LINE_FULLWINDOW]
        for phrase in ("10s窗口相对请求倍率误差 **±2%**", "完整60s有效段 **±1%**",
                       "100ms相位迟到上限"):
            self.assertIn(phrase, line)
        # Line 23 (explicit recovery re-anchor amendment).
        self.assertIn("start-recovery-task",
                      self.accepted_lines[ACCEPTED_LINE_RECOVERY])
        self.assertIn("显式分段重锚点",
                      self.accepted_lines[ACCEPTED_LINE_RECOVERY])
        # The accepted record seals the immutable proposal copy.
        self.assertIn(SEALED_SHA,
                      read_bytes(repo_path(ACCEPTED_REL)).decode("utf-8"))

    def test_no_catch_up_and_four_ticks_anchored(self):
        accepted = read_bytes(repo_path(ACCEPTED_REL)).decode("utf-8")
        for phrase in (
            "不连续补跑积压组，不暗中重锚掩盖性能不足",
            "单步仍严格四tick",
            "迟到只向后滑动",
        ):
            self.assertIn(phrase, accepted)
        erratum = self.erratum
        for phrase in ("不追赶补发", "单步严格**四 tick（four ticks）**"):
            self.assertIn(phrase, erratum)


class TestNumericGateValuesInErratum(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.erratum = read_bytes(repo_path(ERRATUM_REL)).decode("utf-8")

    def test_all_gate_values_present(self):
        require_phrases(
            self.erratum,
            [
                "**1 ms**",
                "**4 ms**",
                "**0.5×/1×**（默认 0.5×）",
                "**8 ms/4 ms**",
                "不追赶补发",
                "不连续补跑积压组",
                "不暗中重锚",
                "显式分段重锚（显式继续/恢复，含 `start-recovery-task`）",
                "**超过 100 ms**",
                "`rate_unmet/resource_insufficient`",
                "冻结并撤销控制",
                "不自动降档、不自动恢复、不补发动作",
                "全窗（full-window）",
                "**10 s**",
                "**±2%**",
                "**60 s**",
                "**±1%**",
                "100 ms 相位迟到上限",
                "所有窗口和最坏值均报告",
            ],
            "erratum numeric gates",
        )

    def test_budget_not_equivalence_boundary_kept(self):
        self.assertIn("属墙钟性能预算，不是 G6 动力学数值等价误差", self.erratum)


class TestNonclaimsAndSupersession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.erratum = read_bytes(repo_path(ERRATUM_REL)).decode("utf-8")

    def test_nonclaims(self):
        require_phrases(
            self.erratum,
            [
                "documentation/context only",
                "不改任何门（changes no gate）",
                "不批准任何架构变更（approves no architecture change）",
                "不重跑 issue 83（reruns no #83）",
                "不收口 #84",
                "不收口 G6",
                "不收口 Full",
                "不授予任何验收、批准、收口、复核或重跑许可",
            ],
            "erratum nonclaims",
        )

    def test_supersession_limited_to_the_citation(self):
        require_phrases(
            self.erratum,
            [
                "仅限于 §2 所述错误引用本身",
                "字节不被取代、保持不变",
                NOTE_SHA,
                "14459 B",
                "全部既有字节身份同样保持不变",
                "今后引用 G6 门时应引用 `docs/2026-09-07_joint-rate-contract-accepted.md`",
                "仍按其原字节身份引用",
            ],
            "erratum supersession scope",
        )
        forbid_phrases(
            self.erratum,
            ["取代被勘误文件的字节", "取代其绑定的证据", "取代既有 manifest"],
            "erratum supersession must not reach evidence bytes",
        )

    def test_consumer_rule_present(self):
        require_phrases(
            self.erratum,
            [
                "消费者规则（compact consumer rule）",
                "**权威顺序**",
                "`wksim/AGENTS.md` → `wksim/CONTEXT.md`",
                "**门引用**",
                "`docs/*-accepted*.md`",
                "不得把提案文档当门权威引用",
                "path:line",
                "**历史证据**",
                "SHA256 + 大小",
                "区分\"历史语境\"与\"当前权威\"",
            ],
            "erratum consumer rule",
        )


class TestGitAnchors(unittest.TestCase):
    def test_symbolic_head_and_ancestry(self):
        # Symbolic-HEAD ancestry only; no HEAD-equality assertion anywhere.
        result = git("rev-parse", "--verify", "HEAD^{commit}")
        self.assertTrue(result.stdout.decode("utf-8").strip())
        for sha in ANCESTOR_SHAS:
            ancestry = git("merge-base", "--is-ancestor", sha, "HEAD",
                           check=False)
            self.assertEqual(
                ancestry.returncode, 0, "%s is not an ancestor of HEAD" % sha
            )

    def test_erratum_records_ancestry_pins(self):
        erratum = read_bytes(repo_path(ERRATUM_REL)).decode("utf-8")
        for sha in ANCESTOR_SHAS:
            self.assertIn(sha, erratum)


# --------------------------------------------------------------------------
# Negative tests (in-memory mutations only; no file is modified)
# --------------------------------------------------------------------------

class TestMutationNegatives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.erratum_raw = read_bytes(repo_path(ERRATUM_REL))
        cls.erratum = cls.erratum_raw.decode("utf-8")
        cls.accepted_lines = (
            read_bytes(repo_path(ACCEPTED_REL)).decode("utf-8").splitlines()
        )

    def test_erratum_hash_and_size_drift_fail(self):
        with self.assertRaisesRegex(ValueError, "hash drift"):
            check_binding(
                self.erratum_raw.replace(b"1 ms", b"2 msXXXXXXX"),
                ERRATUM_SHA,
                ERRATUM_SIZE,
                ERRATUM_REL,
            )
        with self.assertRaisesRegex(ValueError, "size drift"):
            check_binding(self.erratum_raw, ERRATUM_SHA, ERRATUM_SIZE + 1,
                          ERRATUM_REL)

    def test_stripping_applicability_phrase_fails(self):
        stripped = self.erratum.replace("不自动约束 wksim，除非被 wksim 明确采纳",
                                        "elided")
        with self.assertRaisesRegex(ValueError, "missing required phrase"):
            require_phrases(stripped,
                            ["不自动约束 wksim，除非被 wksim 明确采纳"],
                            "mutation")

    def test_stripping_gate_value_fails(self):
        stripped = self.erratum.replace("**±2%**", "elided")
        with self.assertRaisesRegex(ValueError, "missing required phrase"):
            require_phrases(stripped, ["**±2%**"], "mutation")

    def test_stripping_nonclaim_fails(self):
        stripped = self.erratum.replace("不收口 #84", "elided")
        with self.assertRaisesRegex(ValueError, "missing required phrase"):
            require_phrases(stripped, ["不收口 #84"], "mutation")

    def test_source_gate_mutation_fails_line_anchor(self):
        mutated = list(self.accepted_lines)
        mutated[ACCEPTED_LINE_GROUP_PERIOD] = mutated[
            ACCEPTED_LINE_GROUP_PERIOD
        ].replace("1ms", "2ms")
        with self.assertRaisesRegex(AssertionError, "1ms"):
            self.assertIn("1ms", mutated[ACCEPTED_LINE_GROUP_PERIOD])

    def test_reinjecting_parent_adr_amendment_claim_fails(self):
        with self.assertRaisesRegex(ValueError, "forbidden phrase"):
            forbid_phrases(self.erratum + "（本勘误修订父 ADR 0009）",
                           ["修订父 ADR"], "mutation")

    def test_reinjecting_proposal_authority_claim_fails(self):
        with self.assertRaisesRegex(ValueError, "forbidden phrase"):
            forbid_phrases(
                self.erratum + "（以提案文档为门权威引用 G6 门）",
                ["以提案文档为门权威"],
                "mutation",
            )

    def test_reinjecting_automatic_constraint_claim_fails(self):
        with self.assertRaisesRegex(ValueError, "forbidden phrase"):
            forbid_phrases(
                self.erratum + "（父 ADR 自动约束 wksim 之肯定句）",
                ["父 ADR 自动约束 wksim 之肯定句"],
                "mutation",
            )

    def test_widened_supersession_claim_fails(self):
        with self.assertRaisesRegex(ValueError, "forbidden phrase"):
            forbid_phrases(
                self.erratum + "（取代被勘误文件的字节）",
                ["取代被勘误文件的字节"],
                "mutation",
            )

    def test_note_bytes_drift_detection(self):
        # If the committed note ever drifted from its pinned identity, the
        # binding itself (not this suite) must fail loudly.
        with self.assertRaisesRegex(ValueError, "hash drift"):
            check_binding(
                self.erratum_raw,  # wrong bytes for the note slot
                NOTE_SHA,
                NOTE_SIZE,
                NOTE_REL,
            )


if __name__ == "__main__":
    unittest.main()
