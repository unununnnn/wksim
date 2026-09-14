# Independent review — CodeBuddy architecture-applicability G6 erratum (2026-09-14)

- Reviewer role: independent CodeBuddy reviewer (read-only on candidates; no staging, commit, push, #83 run, or candidate/protected-file modification).
- Review date: 2026-09-14.
- Repo HEAD at review time: `acf322860831cb2a7c83a45cb4e2586922444c57`.
- Ancestry gate: `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0 (ANCESTRY_OK); same for `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` → exit 0.

## 1. Candidate identity (verified before review)

| File | Expected SHA256 | Observed | Size expected/observed | Status |
|---|---|---|---|---|
| `docs/coordination/codebuddy-architecture-applicability-g6-erratum-20260914.md` | `b2e1d34141a86080927e979df6cb048ebe667bace99bf422394f96c22fb52a20` | same | 7468 / 7468 | MATCH |
| `validation/test_codebuddy_architecture_applicability_g6_erratum.py` | `a98b8fd339d02cbb7544dd33bc623a03b9ad0318769745d3aeb3715602799428` | same | 26527 / 26527 | MATCH |

Command: `sha256sum <both files>` + `stat -c '%s %n'`; both untracked (`git status --porcelain` → `??` for both).

## 2. Sources read

`wksim/AGENTS.md`, `wksim/CONTEXT.md`, parent `CONTEXT-MAP.md`, parent ADRs 0005/0009/0010/0011/0014/0016, `docs/architecture-implementation-20260912.md`, `docs/coordination/architecture-continuation-20260913.md`, accepted record `docs/2026-09-07_joint-rate-contract-accepted.md`, proposal `docs/2026-09-07_joint-rate-contract-proposal.md` (title + line 58), sealed copy `validation/joint-rate-contract-20260907/approved-proposal.md`, committed G6 anchors (ingest note `omp-g6-first-step-ingest-note-20260914.md`, context test, review -03 trio, manifest -02 quartet). All 22 in-test pins (PARENT_SOURCES, GOV_SOURCES, G6_ANCHORS, SEALED) were independently recomputed with `sha256sum` and matched exactly, including sizes.

## 3. Findings

### F1 (P3) — Erratum gate restatement is not the full accepted-record protocol
The erratum §2 enumerates gate values (1 ms tick, 4 ms barrier, four ticks, 0.5×/1× with 8/4 ms periods, no catch-up, >100 ms latch, 10 s ±2% / 60 s ±1% / 100 ms phase) — each verified verbatim-consistent with accepted-record lines 9–14 and the 2026-09-07 amendment line 23 (`start-recovery-task`). However, protocol details such as "每档至少3个独立epoch" and the 2 s stabilization marking are not carried. The erratum explicitly directs future gate citations to `docs/*-accepted*.md` (§4 rule 2), so this is an incomplete-restatement observation, not an error. Not a blocker.

### F2 (P3) — Sealed proposal copy is untracked (gitignored territory)
`validation/joint-rate-contract-20260907/approved-proposal.md` (SHA256 `54dcd1df…`, 8848 B, verified) is absent from the HEAD tree (`git ls-tree HEAD` lists only the accepted and proposal blobs). Its identity rests on the disk hash plus the accepted record's own pin (line 5), which the erratum restates. The erratum cites it by SHA256, so identity is unambiguous. Observation only.

### F3 (P3) — "Consistent guidance" characterizations are supported but judgmental
ADR-0009 consistency is anchored by architecture-implementation line 12 ("统一 SI/NED/FRD `VehicleState`"; "具名执行器"); ADR-0014 consistency is anchored by `CONTEXT.md:19` ("数值对照验收…按预先约定的误差阈值比较"). Both hold; the erratum correctly labels them "一致指引（非自动约束）" and does not promote them to constraints.

No P1 or P2 findings.

## 4. Claim-by-claim verification

- **Applicability wording (§1)**: Parent `CONTEXT-MAP.md` line 12 carries verbatim "既有 ADR 不自动约束 wksim". Authority order (AGENTS.md → CONTEXT.md → accepted contracts → migration architecture) mirrors wksim AGENTS.md. ADR non-adoption entries (0005 gRPC/optional-ROS2-bridge, 0010 Gazebo Harmonic, 0011 Cosys-AirSim v3.3/UE5.5, 0016 Gazebo authority + Cosys mirror) each match the ADR texts; wksim's actual targets (WSL Ubuntu22.04 ROS2/DDS, PX4 + ArduCopter SITL, UE5.5 + `WksimVehicleVisual`) are confirmed in AGENTS.md and architecture-implementation lines 14/22. Correct.
- **Citation correction (§2)**: The ingest note's erroneous anchor is exactly at §5, line 48: "锚：`docs/2026-09-07_joint-rate-contract-proposal.md:58`、`ds-g6-major-time-binding` v3 记录" — quoted exactly by the erratum. Proposal title line 1 is "# #8/#20 联合倍率契约提案（未批准）"; proposal line 58 exists and carries the gate question. The proposal's editorial "后续状态" line points to the accepted record, corroborating that the accepted record is the gate authority. Correction is accurate.
- **Supersession scope (§3)**: Limited to the erroneous citation only; note bytes `c7f03453…`/14459 B verified unchanged and byte-equal to HEAD blob, as are all review -03 and manifest -02 anchors. Correct and enforced by the test's `G6_ANCHORS` head-equality checks.
- **Nonclosure (§0)**: Explicit nonclaims (no gate change, no architecture approval, no #83 rerun, no #84/G6/Full closure) present and consistent with the file's content-only nature.
- **Source pinning**: All 22 pins recomputed independently — exact match.
- **Ancestry checks (§0 header / test)**: Both ancestor exits 0, re-verified during this review.
- **Index independence (test design)**: The suite's git calls are limited to `rev-parse --verify`, `cat-file blob HEAD:…`, and `merge-base --is-ancestor` — no `git status`/`ls-files`/index inspection. Confirmed by code inspection and by run mode B below.

## 5. Test execution

Mode A — normal:
```
python -m unittest validation.test_codebuddy_architecture_applicability_g6_erratum -v
→ Ran 31 tests ... OK
```

Mode B — repo-external temporary index, exactly two candidates:
```
TMPIDX_DIR=$(mktemp -d); export GIT_INDEX_FILE="$TMPIDX_DIR/index"
git read-tree --empty
git add -f docs/coordination/codebuddy-architecture-applicability-g6-erratum-20260914.md \
           validation/test_codebuddy_architecture_applicability_g6_erratum.py
git ls-files -s   # exactly 2 entries:
# 100644 58e909d8c159079024d75b7a8043349546a21bb1 0  docs/coordination/...erratum-20260914.md
# 100644 858126147e8063fcde75f818e553133fa3498222 0  validation/test_...erratum.py
python -m unittest validation.test_codebuddy_architecture_applicability_g6_erratum -v
→ Ran 31 tests ... OK
```
Staged blob SHA1s equal `git hash-object` of the disk files (`core.autocrlf=false`), so staging introduced no content mangling. The real index was unchanged across the run (`.git/index` SHA256 `be697960…` identical before/after); the temporary index was removed after the run.

Negative tests are in-memory only; no file is modified by the suite.

## 6. Verdict

**KEEP** — both candidates.

- Findings: P1 = 0, P2 = 0, P3 = 3 (F1 incomplete protocol restatement, F2 untracked sealed copy, F3 judgmental-but-supported characterizations). None blocking.
- Tests: 31/31 pass in both modes.
- Blockers: none.

The erratum is correctly scoped (context-only), its single applicability clarification rests on the parent CONTEXT-MAP's own wording, its bibliographic correction is factually accurate, its supersession is limited to the erroneous citation while all evidence bytes remain pinned, and the binding suite is index-independent, fail-closed, and passes deterministically in both execution modes.
