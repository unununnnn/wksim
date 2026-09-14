# Delivery entry contract review (2026-09-14-01)

Work class: review/triage (read-only on candidate, source, and existing receipts).
cwd / branch / HEAD: `C:/Users/PC/Documents/odid编译/wksim`, `main`, `5370b2324672c9036d41239cb93e21fc5eb42897`.
Architecture ancestor `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`: `git merge-base --is-ancestor … HEAD` exit 0.
Module: `validation/test_delivery_entry_contract.py`. Exclusive writes: the three files in this directory only.
Not executed: native / ROS / DDS / SITL / FC / UE / MATLAB / models / builds / flights / user-process actions.
Not done: add / commit / push, ticket closure, owner approval.

Subagent policy note: dispatcher is not `gpt-6-astra`, so policy requires `gpt-5.6-luna` xhigh + Fast for any dispatch; this interface cannot select or verify those settings, so per policy the review was performed in the main agent and the limitation is reported instead of substituting settings.

## Candidate identity

| candidate | status | expected SHA256 | observed |
| --- | --- | --- | --- |
| `validation/test_delivery_entry_contract.py` | untracked (`??`) | `390f9061ec74dae1df07067a73ed2ea5433f75485682bee47d1e789a99364075` | match |

## Historical receipt status

`validation/coordination/cursor-next-frontier-contract-audit-20260914-01/` was read as **historical evidence only**. Its audited delivery hash `682f3b20b29a1312becad6ec519fdb8434ff09270af118e55c23e3986cdcc808` is the **repaired-away version** and does not match the current file. Its four delivery P2s were used as the repair checklist, not re-asserted against the current file, and its overall FAIL is not transferred to the current candidate:

1. string-only assertions → repaired: real `runner.main(argv)` with `run` patched, real `mixed.admit()` with `verify` patched to prove reject-before-verify, real `check()` and `checked_json` on temp files
2. external fixed-hash-as-evidence → repaired: real byte read + SHA256 + `checked_json` per manifest when reachable, with temp negatives
3. fail-open sibling `continue` → repaired: `skipTest` in `_require_frozen` and the sibling test
4. fe3 treated as current entry → repaired: fe3 modelled as separate-or-skip, equality not required, MAIN verified independently

## Seam verification (real, read in source)

- MAIN parser: `tools/run_joint_flight.py:1163-1211`; task-profile choices at 1193 are `('position', PV_PROFILE, MIXED_PROFILE)`; rejection paths observed as `SystemExit(2)`.
- Timing-probe run gate `run_joint_flight.py:423-425` (allowed set PV/MIXED; stale "candidate/PV" wording is message text only); async gate 426-428, 1210-1211; `check_isolation` import at 29, called at 432 — tests patch the module attribute and prove gate ordering.
- `mixed.admit()` early rejections `tools/ap_mixed_candidate.py:100-116`: incomplete pair, exact-final-manifests, unsupported task, explicit-final-message gates are all real.
- `joint_control_candidate.check` 145-153 and `joint_message_candidate.check` 106-114: real `fullmatch` + `SHA256 differs`.
- `checked_json` `tools/verify_ap_pv_candidate.py:14-25`: real SHA256 check plus `_unique_object` (`Simulator/wksim_runtime/config.py:118-124`) raising `ConfigError` on duplicate keys.
- Auditor CLIs: `audit_pv_trajectory.py:874-880`, `audit_26_closure_readiness.py:1736-1740`; `DEFAULT_MANIFEST` (`docs/plan/26-closure-readiness-manifest.json`) exists.
- `cpu_timing` predicate `Simulator/wksim_core/joint.py:54` evaluated from the real assignment via AST; timing-probe three-state/identity `Simulator/wksim_runtime/joint_rate_probe.py:14,23-38`.

Delivery policy: freeze constants in the test match `docs/coordination/short-cycle-goal.md:36` (`1e6250ef…`, `6fe8c0b3…`, `29969da0…`). The continuation contract (`docs/coordination/architecture-continuation-20260913.md`) is respected: fe3 is historical, its PASS does not transfer, MAIN is verified independently. The suite is pure Python; process work in `run()`/`admit()`/`verify()` is patched at module seams.

## Test run (pure Python)

```text
python -B -m unittest validation.test_delivery_entry_contract -v
Ran 20 tests in 1.632s
OK (skipped=1)
passed=19 failed=0 errors=0 skipped=1
```

Skip, recorded precisely:

- `FrozenManifestIdentityTests.test_frozen_external_manifests_read_bytes_match_sha256_and_unique_keys` — `skipTest('frozen Linux manifests not reachable: /root/wksim-ap-mixed-fhuf05l9/mixed-build.json')`. Only the AP path was absent at test time; control/message resolved during the run but received **no** byte or SHA256 verification because the shared test skips as a whole when any member of the frozen triple is missing. **This skip is not coverage.**

Reachability observations (not treated as stable evidence): the fe3 sibling test executed fully (not skipped) at run time, asserting the sibling is distinct from MAIN; direct `is_file()` probes immediately before and after the run returned False for all four WSL paths (AP, control, message, fe3), so WSL reachability on this host is intermittent. The MAIN runner SHA256 prefix `c8577093a62e4993` was independently recomputed and matches the historical receipt's recorded value.

## Verdict

**overall = PASS** (admit-next-batch allowed). P1 = 0, P2 = 0, P3 = 5.

- P3-1: test name overpromises — `test_main_entry_is_verified_even_if_sibling_lookup_returns_none` (L217-222) never forces the None branch; MAIN verification is real, the "even if" clause is decorative.
- P3-2: source `FINAL_*` (`ap_mixed_candidate.py:22-24`) are not cross-checked against the doc-published freeze constants used at L50-57.
- P3-3: auditor `--output` overwrite-refusal semantics (`audit_pv_trajectory.py:881-888`) unpinned.
- P3-4: `build_cli_parser` AST-exec helper (L90-111) couples auditor parser tests to `main()` statement shapes.
- P3-5: all-or-nothing skip granularity for the frozen triple (L409-420) left reachable control/message manifests unverified in this run.

Coverage limits (a green run here is not): any frozen-manifest byte identity on this machine this run (skipped, zero coverage); admission success paths (`verify` walk, `admitted_control`, `check_messages`) — only early rejection is covered; auditor overwrite-refusal behavior; a stable statement of WSL-side file existence (flaky reachability).

Not claimed: #84, #33, #26, Full, G6, official MIXED/entry promotion.

Ingest candidate path set for a later manifest, exact: `validation/test_delivery_entry_contract.py` (SHA256 `390f9061ec74dae1df07067a73ed2ea5433f75485682bee47d1e789a99364075`). No other file is proposed.

## Receipt files

Exactly three files in this directory: `review.md`, `review.json`, `SHA256SUMS` (covering the first two, paths relative to this directory).
