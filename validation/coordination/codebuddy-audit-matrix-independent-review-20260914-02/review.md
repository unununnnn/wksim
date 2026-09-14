# CodeBuddy independent review — remediated audit-matrix context batch (2026-09-14, -02)

Read-only independent review of the remediated audit-matrix historical-context batch
(the P2 lifecycle fix). Supersedes `codebuddy-audit-matrix-independent-review-20260914-01`
(superseded: candidate note/test bytes changed after -01) and excludes the blocked
`codebuddy-audit-matrix-context-ingest-manifest-20260914-01` (its failure conclusion is
unchanged; this review does not rehabilitate it). Only the three files in this directory
were written.

## Scope and checkout

- Expected HEAD `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` ("Bind mixed failure context
  offline"): present and is `HEAD` exactly at session start (2026-09-14T20:38+09:00);
  dispatch required only ancestry — satisfied either way.
- Architecture anchor `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` is an ancestor of HEAD
  (direct `git merge-base --is-ancestor` rc=0, and asserted by the suite).
- No stage, commit, reset, clean, push, fetch, native/build/MATLAB/ROS/DDS/SITL/FC/UE/
  model/flight execution; #83 not rerun; no GitHub queries.

## Candidate identity (recomputed full SHA256 + size)

| Candidate | SHA256 (recomputed) | bytes | Dispatch | match |
|---|---|---|---|---|
| `docs/coordination/codebuddy-audit-matrix-review-20260912.md` | `fbb2568bea73167997ee62782fb71f1aba98dd54cd3e2f99108c591f41abcbf1` | 5805 | prefix `fbb2568b` | yes |
| `docs/coordination/codebuddy-audit-matrix-review-ingest-note-20260914.md` | `7fa1bdcc2c210e3e6e3fbe76be1dded409abd793f66c2b643753712962b8f22c` | 16071 | full hash + size | yes |
| `validation/test_codebuddy_audit_matrix_review_context.py` | `59fd4eaa8d1ba35abf246b890a5db8ac979b00b2297ac3a8631f0e607b19a106` | 30616 | full hash + size | yes |

The review doc is a read-only historical review record (2026-09-12, two rounds, frozen
release auditor + probe-run-02 one-positive/four-negative matrix). The ingest note binds
it as historical context only, registers drift (auditor `e8d33c5d…` → `bd90c75a…` via
`09b9729e`; probe tool in-progress 47554 B → tracked 49128 B via `5ec3d389`; session.py
accept 88–101 → 86), and correctly refuses all acceptance/closure semantics. The test
suite re-enacts the note's seams with 31 offline tests.

## Lifecycle fix verification (the P2 remediation under review)

All runs `python -B validation/test_codebuddy_audit_matrix_review_context.py`; temp-index
runs used `GIT_INDEX_FILE` pointing at a non-existent `mktemp -u` path (real index never
touched).

1. **Normal run:** 31 tests, 0 failures, 0 errors — OK.
2. **Private temp index, exactly the 3 candidates:** 3 staged entries, all mode
   `100644`/stage `0`; 31 tests — OK.
3. **Private temp index, the 10 paths of the blocked -01 manifest (lifecycle proof):**
   3 candidates staged normally + 7 gitignored coordination files staged with
   `git add -f` (temp index only); exactly 10 entries, all mode `100644`/stage `0`;
   31 tests — OK. This is the shape the former exact-3 check rejected; the remediated
   candidate-subset verifier accepts it, so the same suite can now validate larger
   admission batches. The blocked -01 manifest itself remains superseded/blocked.
4. **Real negative (missing candidate):** temp index with only 2 of 3 candidates →
   suite fails in `setUpClass` with `AssertionError: staged index must contain
   candidate path validation/test_codebuddy_audit_matrix_review_context.py`,
   python rc=1.
5. **In-suite negatives (all passing as expected-to-raise):** binding hash/size drift,
   untracked paths, bogus ancestor, wrong blob sha256, missing literal; staged-subset
   negatives (missing candidate, nonzero stage, duplicated candidate entry, blob
   mismatch) plus exact-3 and extra-pars-allowed positives; strict-JSON duplicate-key
   and NaN rejection; promotion-wording negatives (7 phrases) with sanity positives.

## Point checks

- **Candidate subset enforcement:** proven positive (runs 2–3) and negative (run 4).
  Extra independent-review/manifest paths are permitted by design per note §8 step 5;
  exact batch equality is deferred to the manifest/final verifier.
- **Stage 0/blob identity:** every staged sha1 across runs 2–3 equals
  `git hash-object` of the working bytes (candidates `64947957`, `68dcba6d`, `d6bcfb2e`;
  coordination files `cd7f17e4`, `890db747`, `39588f7e`, `65035202`, `0fb48504`,
  `823d869b`, `ed1f5721`); all entries mode `100644`, stage `0`.
- **No promotion/closure:** `assert_no_promotion` passes on both note and review doc;
  manual read confirms the note grants no acceptance/approval/closure/rerun permission;
  #83 stays CLOSED/PASS, never rerun; #84/G6/Full stay incomplete.
- **Architecture ancestor:** `f333316e…` ancestor of HEAD, verified directly and by the
  suite (which also asserts `e897fb8e`, `5ec3d389`, `09b9729e` ancestry).
- **Note factual spot-checks:** `session.py:86 def accept`, `trajectory_bridge.py:91 def
  build_ros_mode_request`, `node.py:512 elif msg.cmd == UAVSetup.SET_PX4_MODE` — all
  exact. The suite byte-binds the 5 tracked matrix files, both current tools, F4 source
  anchors, handoff (16 keys, no envelope payload), and confirms F5 (70 vs 66) and
  dedup regression test tracked — all passing.
- **Protected baselines unchanged by this session:** the 5 protected files were only
  read. Two show pre-existing worktree-vs-HEAD drift that predates this session (mtimes
  2026-09-12 08:27, session start 2026-09-14 20:38): `docs/Prometheus.gitmodules.reference`
  (pure CRLF/LF byte difference; visible content identical) and
  `validation/coordination/short-cycle-dispatches.json` (live automation heartbeat/
  status content). Neither was touched here; candidates and protected files show no
  session-caused modification.
- **Real index byte-identical:** `.git/index` sha256 `a7fd6154…e9253` and
  `git ls-files -s | sha256sum` `5e08ccab…835ef` identical before first write and after
  last write. Status-porcelain hash is reported for the artifact-creation window only
  (see review.json) per sibling-session concurrency policy.
- **Superseded -01 dirs untouched:** all 7 files of
  `codebuddy-audit-matrix-independent-review-20260914-01/` and
  `codebuddy-audit-matrix-context-ingest-manifest-20260914-01/` re-hashed at review end
  identical to session-start values (aggregate `aaeb475c…703e`). Excluded from this
  batch as required.
- **Suite performs no writes:** source scan finds no file-write/unlink/mkdir/shutil
  operations; runs are offline (no network).

## Findings

- **P3-1** — `assert_no_promotion` (test file, PROMOTION_PATTERNS, lines 310–319) is
  English-only while the ingest note is predominantly Chinese; a Chinese-language
  promotion claim would not be caught by the regex guard. Manual read found no
  promotion wording in either candidate. Guard-depth limitation only; no action
  required for this batch.
- **P3-2** — `test_note_registers_line_drift` (test file, line 563–565) asserts the bare
  substring `"86"`, which matches anywhere in the note; weak as a drift-registration
  check. The actual anchor is enforced where it matters
  (`require_literal(SESSION_REL, "def accept(self, request):")`), and this reviewer
  confirmed line 86 directly. Cosmetic.
- **P3-3** — With the P2 fix, the candidate suite no longer detects an over-broad
  staged batch (extra unrelated paths pass silently); exact-path equality is deferred
  to the manifest/final verifier by documented design (note §8 step 5, test docstring).
  Registered so subset semantics are not misread as batch-equality enforcement.

No P1, no P2.

## Verdict

**ADOPT** — the remediated lifecycle fix works as specified: normal, exact-3-candidate,
and 10-path blocked-manifest temp-index runs all pass; missing-candidate and in-memory
negatives are rejected; staged entries are mode 100644/stage 0 with blob-identical
bytes; no promotion/closure semantics; architecture ancestor holds; protected baselines
and the real index are untouched. The blocked -01 manifest remains blocked, unchanged.

## Provenance

- SHA256SUMS (binary `*` mode, files written without EOL translation, `* -text`):
  see `SHA256SUMS` in this directory.
- Session window: 2026-09-14T20:38:27+09:00 to post-write verification.
