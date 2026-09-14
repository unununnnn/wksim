# Independent review: interface decision packet offline-admission context (2026-09-14-01)

- Reviewer: CodeBuddy (independent, offline)
- Reviewed HEAD: `e8defc1d8317892e022ee24de086b026c1317e5a` (verified via `git rev-parse HEAD`)
- Architecture ancestor check: not re-run here; HEAD is the same commit the ingest note binds (ancestor `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` is recorded in the note and in both pinned JSONs).
- Scope: exactly the three candidate files below; no other candidate scope inspected, no candidate or protected file modified, nothing staged/committed/pushed, no native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight or #83 work executed.

## Candidate identity (verified by `sha256sum` at HEAD)

| Path | SHA256 (declared) | Match |
| --- | --- | --- |
| `docs/coordination/ds-interface-decision-packet-20260912.md` | `a7cfe224f2528a5651c6037eae7cf1547ae57e1dfe210c7792308ad247d5e382` | yes |
| `docs/coordination/interface-decision-packet-ingest-note-20260914.md` | `e1e8171fc6ab46dba28b94ac550eca1893e9d844ddf22b46252f382742302632` | yes |
| `validation/test_interface_decision_packet_context.py` | `89e96db007bb822a2d24ac25b2d07069046ee88e98b07ac84d4dbcd3cc3bf363` | yes |

## Test command and result (proven behavior)

Command: `python -B -m unittest validation.test_interface_decision_packet_context -v`

- Exit code: 0
- Tests: 9 ran, 9 ok, 0 failures, 0 errors, 0 skipped (0.036 s)

## Criteria review

### 1. Strict JSON rejection — PASS

`strict_loads` (test lines 30–56) wires `object_pairs_hook` (duplicate-key rejection), `parse_constant` (NaN/Infinity/-Infinity), and `parse_float` (`1e999` overflow to inf rejected). Both real pins are loaded strictly in `setUpClass` (lines 139–140). Negative tests are meaningful: `test_json_pins_reject_duplicate_keys` (lines 169–173) builds the duplicate key from the *real* `defer_text` bytes (prepends `{"schema":"first",` to the actual file body), proving the hook fires on the real document shape, not a toy input; `test_json_pins_reject_non_finite_numbers` (lines 175–179) covers NaN, ±Infinity, and the overflow literal.

### 2. Exact one-record semantics — PASS

`_matching_path_records` (lines 63–73) recursively collects every dict whose `path` equals the packet path in each pin; `_validate_context` requires exactly one occurrence in each of the defer JSON and the audit JSON (lines 92–95) and requires every matched record's `sha256` to equal the pinned packet hash (lines 96–98). `test_duplicate_packet_record_fails_closed` (lines 194–200) demonstrates fail-closure on an added duplicate. (See P3-1 for the audit-only asymmetry of the negative demonstration.)

### 3. Historical false / current true explanation — PASS

The ingest note (lines 14–18) explains the two records precisely: `docs/plan/9-vendor-abi-defer-boundary.json` recorded `tracked=false` as a true observation of the packet's then-untracked status; `validation/coordination/ds-dll-abi-evidence-20260913-01/audit.json` recorded `tracked=true`, which disagreed with live git status at its write time and would become current only if the packet is committed at the unchanged hash — without retroactively changing the earlier record's observation time. The test enforces this with strict identity checks (`is not False` / `is not True`, lines 99–102), so truthy/falsy substitutes (e.g. `0`/`1`) fail closed. Verified against the real pins: defer JSON `host_bounded_gaps.interface_decision_packet.tracked=false` with the packet hash; audit JSON `evidence_sources[decision-packet].tracked=true` with the same hash; both bound to the correct path exactly once.

### 4. No authority/approval/acceptance promotion — PASS

The packet self-declares non-authority (packet line 4: does not decide for the user, no ABI guessing, no budget values). The note (lines 8–10) restricts itself to historical-context/ingest semantics and explicitly grants no approval, budget decision, ABI selection, owner decision, or acceptance/closure authority for #9/#26/#29/#33/#84/Full/G6/Goal. The test enforces this both ways: the boundary sentences are required verbatim (lines 104–114) and `test_authority_or_acceptance_promotion_fails_closed` (lines 202–208) flips "不把它提升为决策依据" and "不授予 #9" and asserts fail-closure with the distinct "lost required boundary" message.

### 5. Superseded unique-reader claim — PASS

The packet's §5.3 claim ("`wksim.display-manifest.v1` 目前唯一的读取方是离线审计器 `tools/audit_29_terrain_evidence.py`", packet line 136) is preserved byte-for-byte and its presence is required (test lines 116–122) — the historical artifact is not silently rewritten. The note (lines 22–24) explicitly supersedes only that statement via the later tracked implementation, without claiming UE consumers or #29 completion. Verified against source: `Simulator/wksim_runtime/display_scene_binding.py` is git-tracked (`git ls-files --error-unmatch` passes, test lines 158–167) and contains `class DisplaySceneBinding` (line 248) with `validate_manifest` (line 275) and `load_manifest` (line 297). The test checks both entrypoints via AST of the tracked source (lines 76–85, 125–128) and fails closed if either disappears (test lines 218–221).

### 6. Distinct #83 boundary — PASS

The note (lines 26–28) states that HEAD `e8defc1d…` ingested the #83 joint-rate diagnostic originals and offline consistency test, that that evidence handles GC latch / group lateness / `RateUnmet`, and that the two evidence groups differ in topic, schema, and acceptance role and cannot substitute for each other. Independently confirmed read-only: `git show --stat HEAD` shows `e8defc1d` = "Bind offline joint rate diagnostic evidence", containing the #83 diagnostic originals and `validation/test_83_diagnostic_evidence_originals.py`. The test requires the commit id and the non-substitution sentence in the note (lines 104–114) and `test_supersession_and_diagnostic_boundaries_fail_closed` (lines 210–216) flips both the supersession sentence and "不能互相替代" with fail-closure. The test itself reads no #83 evidence files — no cross-scope coupling.

### 7. Meaningful negative tests — PASS

Seven fail-closed tests each mutate exactly one input and assert a distinct, specific error message: duplicate keys (real-file-derived), non-finite literals, hash/tracking drift (two sub-cases), duplicate packet record, authority promotion (two sub-cases), supersession/#83 conflation (two sub-cases), missing display entrypoint. Each maps to a fail-closed clause in the note's "依赖与离线测试接缝" items 1–5. No negative test asserts a generic `Exception`; all use `assertRaisesRegex` with discriminative patterns.

## Findings

### P1

None.

### P2

None.

### P3

1. **Duplicate-record negative demonstration covers `audit` only** — `test_duplicate_packet_record_fails_closed` (validation/test_interface_decision_packet_context.py:194-200) injects the duplicate into `audit` only; the exactly-once guarantee for the defer JSON is enforced (:92-95) but never negatively demonstrated. Fail-closure for the defer pin rests on the shared implementation path, which is verified only positively.
2. **"缺失字段" fail-closure promised but not negatively exercised** — the note's seam item 5 (interface-decision-packet-ingest-note-20260914.md:38) lists missing fields among fail-closed conditions, but no dedicated negative test removes a field. Missing `sha256`/`path` fall through the `.get()` drift checks (test :96-102) only implicitly; a missing `tracked` key would raise via the identity checks, but none of these paths is demonstrated by a test.
3. **Defer-boundary Markdown registration is unpinned** — the note (interface-decision-packet-ingest-note-20260914.md:14) attributes the `tracked=false` registration to the defer JSON "及同名 Markdown", but the test seam and the note's own seam item 2 bind only the two JSONs; the Markdown's registration statement is outside every pin. Consistent with the stated JSON-only seam, but the prose sentence is broader than what is enforced.

## Verdict

**PASS** — all three candidates match their declared SHA256 at HEAD `e8defc1d…`; the mandated test command exits 0 with 9/9 ok; strict JSON rejection, exact one-record semantics, the historical-false/current-true explanation, non-promotion boundaries, the superseded unique-reader claim against the tracked `display_scene_binding.py`, and the distinct #83 boundary are all implemented and (except as noted in P3) negatively demonstrated. The P3 findings are test-coverage/prose-precision observations only; none blocks offline admission.

## Scope and non-claims

Scope: inspection of the three candidate files, the two pinned JSONs, the tracked `Simulator/wksim_runtime/display_scene_binding.py`, `git rev-parse`/`git show --stat`/`git ls-files` (read-only), and the single mandated unittest command. Outputs limited to this review directory.

Non-claims:
- This review does not accept or close #9, #26, #29, #33, #84, Full, G6, Goal, or any parent ticket, and does not promote the packet or the note to decision authority.
- Passing the offline test proves admission semantics, identity binding, and explicit supersession only — not UE consumers, not a real UE/WSL/FC/ROS2/DDS closed loop, not budget approval, not vendor ABI availability.
- The audit JSON's `tracked=true` is an expected post-ingest observation; it does not retroactively alter the defer record's earlier `tracked=false` observation.
- No candidate file, protected file, or any file outside this review directory was modified; nothing was staged, committed, or pushed; no native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight or #83 work was executed.
