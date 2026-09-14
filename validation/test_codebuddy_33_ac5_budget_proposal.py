"""Offline stdlib unittest for docs/plan/33-ac5-budget-row-proposal-20260914.md.

Binds the proposal bytes (SHA-256 + size), the seven authoritative local anchor
documents (SHA-256 + size + content anchors), every required budget
value/unit/window, the PENDING OWNER DECISION and unsigned sign-off state,
nonclosure language, frozen RateUnmet/numerical_failed record preservation,
probe-field exclusion, and ancestry from 31e5b65f and f333316e (not an exact
HEAD pin).

Run modes (env WKSIM_33_BUDGET_TEST_MODE):
- "untracked" (default): normal worktree run. This suite never reads any git
  index in this mode; a guard test asserts no index-touching git call occurred.
- "external-index": requires GIT_INDEX_FILE pointing to a repo-external index
  in which exactly the two candidates are staged. The suite then verifies that
  external index only. The shared real .git/index is never read, fingerprinted
  or modified in any mode.

Suggested external run (repo-external temp index, real index untouched):
    TMPIDX="$PWD/../../wksim-tmpidx-33budget"   # any path outside the repo
    GIT_INDEX_FILE="$TMPIDX" git add -- \
        docs/plan/33-ac5-budget-row-proposal-20260914.md \
        validation/test_codebuddy_33_ac5_budget_proposal.py
    GIT_INDEX_FILE="$TMPIDX" WKSIM_33_BUDGET_TEST_MODE=external-index \
        python validation/test_codebuddy_33_ac5_budget_proposal.py -v
    rm -f "$TMPIDX"

No network, no gh, no native/MATLAB/ROS/DDS/SITL/FC/UE/build/flight, no #83
rerun. This slice does not close #33, #84, Q01, G6 or Full.
"""

import hashlib
import os
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_REL = "docs/plan/33-ac5-budget-row-proposal-20260914.md"
TEST_REL = "validation/test_codebuddy_33_ac5_budget_proposal.py"
PROPOSAL_PATH = REPO_ROOT / PROPOSAL_REL
TEST_PATH = REPO_ROOT / TEST_REL
CANDIDATES = (PROPOSAL_REL, TEST_REL)

MODE_ENV = "WKSIM_33_BUDGET_TEST_MODE"
MODE_UNTRACKED = "untracked"
MODE_EXTERNAL = "external-index"

ANCESTOR_COMMITS = (
    "31e5b65f5448c5558450d16d0f46da0ef0f0a03c",
    "f333316e6efa6b299b4288a9d91fb2bccedfb9d6",
)

PROPOSAL_SHA256 = "998ed98cc668bc36e08acbc401f60e5aa50e356250cd9a82fa6cde5e5c3db5c0"
PROPOSAL_SIZE = 5790

# (relative path, sha256, size, content anchors)
SOURCE_ANCHORS = (
    (
        "docs/plan/tickets/23-mixed-trajectory.md",
        "3852fafa30470a37f7388cd4192966ef8d5b76e74a9a73f137eded8ae37d058d",
        2066,
        ("固定轨迹的误差、驻留和恢复门槛预先确定",),
    ),
    (
        "docs/plan/full-original-ac-gap-ledger-20260914.md",
        "5a4d9a649abeb57b423d98b84fdf8c59c965afd74a92ba88061ee48a1c44ad3e",
        25570,
        (
            "Q01 Commit the per-quantity error/dwell/recovery budget row for #33 AC5",
            "blocked-owner-decision",
            "an owner-signed budget row committed in docs/plan",
        ),
    ),
    (
        "docs/2026-09-07_joint-rate-contract-accepted.md",
        "6a68840d3cb5612cba921468a370014b38e1416c81d6dc2c9c41ebc816ff71ab",
        3200,
        ("超过100ms", "±2%", "±1%", "不连续补跑积压组", "显式恢复5s"),
    ),
    (
        "docs/2026-09-06_joint-wall-supervision-accepted.md",
        "5aebe315637f4f7baa7be6dedb3702627de4d7ca30dc6bbe6b647f5a4f26fbd8",
        2042,
        ("显式恢复就绪等待 | 5s",),
    ),
    (
        "docs/2026-09-07-recovery-staging-revert-correction-report.md",
        "64326d9672759cae51fb773341aa39de944fead0912088f6fb0dafd8f474c5c1",
        5315,
        ("保持驻留门槛", "rate_unmet"),
    ),
    (
        "docs/2026-09-13-final-combo-pv-pass.md",
        "d3c70b49da4f090748ee19fc6101d0d86f5021b5daafef1ede5ef15dd146e512",
        4133,
        ("0.120215", "0.040880", "0.091560", "≤0.25m/s", "≤0.4", "12秒轨迹"),
    ),
    (
        "docs/2026-09-09-pv-flight-report.md",
        "d6043950dea8894298a56cdce41102b8667407bde19d9aa62d8c7cac2140a58a",
        8419,
        ("0.12668", "0.07790", "0.03950", "各连续12s", "各连续4s"),
    ),
)

# Frozen, owner-approved rate/supervision bounds (row regexes into the proposal).
FROZEN_ROW_PATTERNS = (
    r"累计墙钟迟到\s*\|\s*>100 ms",
    r"相对请求倍率误差\s*\|\s*±2%\s*\|\s*每个不重叠 10 s 窗口",
    r"相对请求倍率误差\s*\|\s*±1%\s*\|\s*完整 60 s 有效段",
    r"dt = 1 ms",
    r"4 ms（单步严格四 tick）",
    r"显式恢复就绪等待\s*\|\s*5 s",
)

# Proposed carry-over rows: name | threshold | dwell window | observed max | status.
PROPOSED_ROWS = (
    ("轨迹位置误差", r"≤0\.5 m", "每连续 12 s 轨迹段", r"0\.12668 m"),
    ("逐轴速度误差", r"≤0\.3 m/s", "每连续 12 s 轨迹段", r"0\.07790 m/s"),
    ("yaw 角误差", r"≤0\.15 rad", "每连续 12 s 轨迹段", r"0\.03950 rad"),
    ("停止保持速度", r"≤0\.25 m/s", "每连续 4 s 停止保持段", r"0\.040880 m/s"),
    ("停止保持漂移", r"≤1 m", "每连续 4 s 停止保持段", r"0\.091560 m"),
)

REQUIRED_TOKENS = (
    "PENDING OWNER DECISION",
    "Q01 保持开放",
    "blocked-owner-decision",
    "33:5",
    ">100 ms",
    "rate_unmet",
    "no catch-up",
    "RateUnmet",
    "numerical_failed",
    "classification=diagnostic_only",
    "production_performance=false",
    "PENDING OWNER DECISION（待所有者决策）",
    "不关闭 #33、#84、Q01、G6 或 Full",
    "Full = not-closed",
    "not-closed",
    "不构成任何批准",
    "不是 G6 每量动力学等价预算",
    "签署前本提案不构成任何批准；Q01 与 `33:5` 保持开放",
)

ANCHOR_REFS_IN_PROPOSAL = (
    "docs/plan/tickets/23-mixed-trajectory.md",
    "docs/plan/full-original-ac-gap-ledger-20260914.md",
    "docs/2026-09-07_joint-rate-contract-accepted.md",
    "docs/2026-09-06_joint-wall-supervision-accepted.md",
    "docs/2026-09-07-recovery-staging-revert-correction-report.md",
    "docs/2026-09-13-final-combo-pv-pass.md",
    "docs/2026-09-09-pv-flight-report.md",
    "docs/plan/33-rate-timing-probe.md",
)

# Index-touching git subcommands; every invocation is recorded for the
# no-real-index guard. `merge-base` never touches the index and is excluded.
INDEX_CMDS = frozenset(
    {"ls-files", "update-index", "add", "rm", "write-tree", "read-tree",
     "commit", "reset", "checkout", "restore", "status", "diff", "stash"}
)
INDEX_TOUCHING_CALLS = []

_TEST_SOURCE = TEST_PATH.read_bytes().decode("utf-8")


def current_mode() -> str:
    return os.environ.get(MODE_ENV, MODE_UNTRACKED)


def blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def _git(args, extra_env=None):
    env = {k: v for k, v in os.environ.items() if k != "GIT_INDEX_FILE"}
    if extra_env:
        env.update(extra_env)
    if args and args[0] in INDEX_CMDS:
        INDEX_TOUCHING_CALLS.append(tuple(args))
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )


def _proposal_text() -> str:
    return PROPOSAL_PATH.read_bytes().decode("utf-8")


class TestProposalBytes(unittest.TestCase):
    """Byte/content binding of the proposal. Runs in both modes."""

    def test_file_bytes_bound(self):
        data = PROPOSAL_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), PROPOSAL_SHA256)
        self.assertEqual(len(data), PROPOSAL_SIZE)

    def test_required_tokens_present(self):
        text = _proposal_text()
        for token in REQUIRED_TOKENS:
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_status_is_pending_owner_decision(self):
        text = _proposal_text()
        self.assertGreaterEqual(text.count("PENDING OWNER DECISION"), 6)
        self.assertIn("**状态：PENDING OWNER DECISION", text)

    def test_frozen_approved_bounds_rows(self):
        text = _proposal_text()
        for pattern in FROZEN_ROW_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertRegex(text, pattern)

    def test_proposed_carry_over_rows(self):
        text = _proposal_text()
        for name, threshold, window, observed in PROPOSED_ROWS:
            pattern = (
                re.escape(name) + r"\s*\|\s*" + threshold +
                r"\s*\|\s*" + re.escape(window) +
                r"\s*\|\s*" + observed +
                r"\s*\|\s*PENDING OWNER DECISION"
            )
            with self.subTest(quantity=name):
                self.assertRegex(text, pattern)

    def test_owner_choice_checkboxes_unchecked(self):
        text = _proposal_text()
        section4 = text.split("## 4.", 1)[1].split("## 5.", 1)[0]
        self.assertEqual(section4.count("- [ ]"), 7)
        self.assertNotIn("- [x]", section4)
        self.assertNotIn("- [X]", section4)

    def test_signoff_block_unsigned(self):
        text = _proposal_text()
        section8 = text.split("## 8.", 1)[1]
        self.assertEqual(section8.count("- [ ]"), 3)
        self.assertNotIn("- [x]", section8)
        self.assertNotIn("- [X]", section8)
        # No checkbox anywhere in the document is ticked.
        self.assertNotIn("- [x]", text)
        self.assertNotIn("- [X]", text)
        self.assertEqual(text.count("- [ ]"), 10)
        self.assertIn("所有者签署块（未签署）", text)

    def test_nonclosure_language(self):
        text = _proposal_text()
        for token in (
            "不关闭 #33、#84、Q01、G6 或 Full",
            "Full = not-closed",
            "G0–G6 全部 `not-closed`",
            "签署前 Q01 与 `33:5` 保持未勾选、未关闭",
            "Q01 与 `33:5` 保持开放",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_frozen_records_and_probe_exclusion(self):
        text = _proposal_text()
        self.assertIn("既有 `RateUnmet` / `numerical_failed` 失败记录原样保留", text)
        self.assertIn("不改判、不复用、不抹除任何失败记录", text)
        self.assertIn("`rate_timing_probe` 记录带 `classification=diagnostic_only`", text)
        self.assertIn("`production_performance=false`", text)
        self.assertIn("探针样本不得冒充 production 性能", text)
        self.assertIn("不得作为本预算行的验收证据", text)

    def test_scope_separation_from_g6(self):
        text = _proposal_text()
        self.assertIn("它们不是 G6 每量动力学等价预算", text)
        self.assertIn("属于控制集成（控制接缝）预算", text)
        self.assertIn("墙钟性能预算，不是动力学等价误差", text)

    def test_proposal_references_anchor_docs(self):
        text = _proposal_text()
        for ref in ANCHOR_REFS_IN_PROPOSAL:
            with self.subTest(ref=ref):
                self.assertIn(ref, text)


class TestSourceAnchors(unittest.TestCase):
    """SHA-256 + size + content anchors of the seven source documents."""

    def test_anchor_files_bound_with_content(self):
        for rel, sha, size, anchors in SOURCE_ANCHORS:
            path = REPO_ROOT / rel
            with self.subTest(file=rel):
                data = path.read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), sha)
                self.assertEqual(len(data), size)
                text = data.decode("utf-8")
                for anchor in anchors:
                    self.assertIn(anchor, text)


class TestAncestry(unittest.TestCase):
    """Ancestry from 31e5b65f and f333316e; no exact-HEAD pin."""

    def _assert_ancestor(self, sha):
        result = _git(["merge-base", "--is-ancestor", sha, "HEAD"])
        self.assertEqual(
            result.returncode, 0,
            msg="not an ancestor of HEAD: %s (%s)" % (sha, result.stderr.strip()),
        )

    def test_31e5b65f_is_ancestor_of_head(self):
        self._assert_ancestor(ANCESTOR_COMMITS[0])

    def test_f333316e_is_ancestor_of_head(self):
        self._assert_ancestor(ANCESTOR_COMMITS[1])

    def test_no_exact_head_pin(self):
        # Ancestry is required, not an exact HEAD value; guard against a
        # pinned-HEAD constant ever being introduced.
        self.assertIsNone(
            re.search(r"(?m)^(PINNED_HEAD|HEAD_SHA|EXACT_HEAD)\s*=", _TEST_SOURCE),
            "a pinned-HEAD constant must not be introduced",
        )


class TestIndexModes(unittest.TestCase):
    """Mode-dependent index behavior. Never reads the shared real index."""

    def test_untracked_mode_never_touches_any_index(self):
        if current_mode() != MODE_UNTRACKED:
            self.skipTest("only meaningful in %s mode" % MODE_UNTRACKED)
        # Both candidates must exist as worktree bytes (content itself is
        # verified byte-for-byte by the other classes in every mode).
        for rel in CANDIDATES:
            with self.subTest(path=rel):
                self.assertTrue((REPO_ROOT / rel).is_file())
        # No index-touching git call may have been made in this mode. The real
        # index is never read, fingerprinted, staged or modified.
        self.assertEqual(INDEX_TOUCHING_CALLS, [])

    def test_external_index_has_exactly_two_candidates(self):
        if current_mode() != MODE_EXTERNAL:
            self.skipTest("only meaningful in %s mode" % MODE_EXTERNAL)
        idx = os.environ.get("GIT_INDEX_FILE")
        if not idx:
            self.fail(
                "%s mode requires GIT_INDEX_FILE pointing to a repo-external index"
                % MODE_EXTERNAL
            )
        idx_path = Path(idx).resolve()
        repo_root = REPO_ROOT.resolve()
        self.assertNotIn(repo_root, idx_path.parents,
                         "GIT_INDEX_FILE must be outside the repository")
        self.assertNotEqual(idx_path, repo_root / ".git" / "index",
                            "the shared real index must never be used")
        result = _git(["ls-files", "-s", "-z"], extra_env={"GIT_INDEX_FILE": str(idx_path)})
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        entries = [e for e in result.stdout.split("\x00") if e]
        self.assertEqual(
            len(entries), 2,
            "exactly the two candidates must be staged, got: %r" % (entries,),
        )
        parsed = {}
        for entry in entries:
            meta, path = entry.split("\t", 1)
            mode, sha, stage = meta.split()
            parsed[path] = (mode, sha, stage)
        self.assertEqual(set(parsed), set(CANDIDATES))
        for rel in CANDIDATES:
            mode, sha, stage = parsed[rel]
            data = (REPO_ROOT / rel).read_bytes()
            with self.subTest(path=rel):
                self.assertEqual(mode, "100644")
                self.assertEqual(stage, "0")
                self.assertEqual(sha, blob_sha1(data))


if __name__ == "__main__":
    unittest.main(verbosity=2)
