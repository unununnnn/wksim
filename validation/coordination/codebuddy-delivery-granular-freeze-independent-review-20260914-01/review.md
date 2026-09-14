# Independent review — delivery granular-freeze patch

- review_id: `codebuddy-delivery-granular-freeze-independent-review-20260914-01`
- date: 2026-09-14, cwd: `C:/Users/PC/Documents/odid编译/wksim`
- HEAD verified: `1884ea64c1fe99502ec7063f00f2f09a17b43ea5`
- scope: working-tree diff of `validation/test_delivery_entry_contract.py` only
- boundaries honored: no source edits, no git add/commit/push/stage, no GitHub,
  no WSL command, no native/ROS/DDS/SITL/FC/UE/MATLAB/model/build/flight run

## Candidate binding

| item | value |
| --- | --- |
| HEAD blob | `2b9bb906` |
| current blob | `2e237ab7` |
| HEAD SHA256 | `390f9061ec74dae1df07067a73ed2ea5433f75485682bee47d1e789a99364075` |
| current SHA256 | `bae759e19d121b2e9b62920aa636203042ab5230dfb72f92330d4d2256dfb350` |
| expected SHA256 | `bae759e19d121b2e9b62920aa636203042ab5230dfb72f92330d4d2256dfb350` — match |
| diff stat | 1 file changed, +37/−13 |
| test methods | 20 (HEAD) → 21 (current), +1 new regression |

The patch replaces HEAD's `_require_frozen` (resolve all, one `skipTest` for the
whole test if any manifest is missing) with `_resolve_frozen`
(validation/test_delivery_entry_contract.py:409-411) plus a per-`subTest` skip
and per-item byte/SHA256/`checked_json` checks
(validation/test_delivery_entry_contract.py:413-422), and adds
`test_missing_first_manifest_does_not_block_later_reachable_verification`
(validation/test_delivery_entry_contract.py:424-453).

## Contract verification (proven behavior)

1. **Independent per-item checking** — verified. Each `FROZEN_MANIFESTS` entry
   gets its own `subTest`; `skipTest` fires only when that item's path is `None`;
   otherwise `len(raw)>0`, `sha256(raw)==digest`, and `checked_json` must return
   a dict. Live run: subtest `posix='/root/wksim-ap-mixed-fhuf05l9/mixed-build.json'`
   skipped, the other two subtests passed (default `TextTestResult` prints
   nothing for passing subtests; the summary `skipped=1` proves exactly one skip).
2. **Regression fails under prior implementation** — verified by execution.
   Probe B loaded the HEAD module verbatim from `git show` (SHA256 `390f9061…`)
   and ran the new regression method verbatim against it: 1 run, 1 error,
   `wasSuccessful=false`,
   `AttributeError: 'FrozenManifestIdentityTests' object has no attribute 'params'`
   — HEAD skips at test level, so no subtest params can exist.
3. **No falsification of live coverage** — verified.
   - The regression patches `linux_file`/`FROZEN_MANIFESTS` only inside its own
     context, on a fresh case instance, against TEMP files; the live test still
     runs unmocked against the real `FROZEN_MANIFESTS`.
   - Probe A (read-only, using the module's own `linux_file`): manifests
     `/root/wksim-joint-control-c2IXOr/build.json` and
     `/root/wksim-ros2-Rzj3Pf/message-build.json` resolve via `\\wsl$\Ubuntu-22.04`
     and their bytes SHA256-match the frozen constants; manifest 1 is genuinely
     absent, so its skip is genuine rather than masking.
   - Probe C (negative): wrong digest on the second mocked entry → exactly that
     subtest fails, run unsuccessful — the granular design does not hide a bad item.
   - Probe D (negative): all three mocked entries missing → three granular
     subtest skips, zero failures/errors — no crash, no all-or-nothing behavior.

## Test results

- command: `python -B -m unittest validation.test_delivery_entry_contract -v`
- exit 0 — `Ran 21 tests` — `OK (skipped=1)` — 0 failures, 0 errors
- the single skip: subtest `posix='/root/wksim-ap-mixed-fhuf05l9/mixed-build.json'`,
  reason `frozen Linux manifest not reachable`
- TEMP-only pure negatives (probes A–D, writes confined to
  `%TEMP%/cb-freeze-review-probe/` and `TemporaryDirectory` under
  `tempfile.gettempdir()`): outcomes as listed above

## Findings

- P1: none
- P2: none
- P3: skip reason text is now a generic per-item string; HEAD's aggregated
  missing-list message is gone. The per-posix identity is still carried by the
  `subTest` params in the printed skip line — cosmetic, no change requested.

## Limitations

- Manifest 1 is absent in this environment: its byte/SHA256/`checked_json` match
  is **not** live-covered here; only its per-item skip path is proven. Coverage of
  that item depends on an environment where it is reachable.
- Reachability of the two manifests is a host-side UNC file-read fact only; no
  WSL command was issued and no claim is made about the WSL side beyond bytes read.
- Frozen digests were compared only to the `FROZEN_*` constants in the test file;
  no cross-check against published identity documents (out of scope).
- Only the scoped file was reviewed; other modified/untracked files in the
  worktree were not read in depth.
- Probe B is an exec-based reconstruction of the HEAD module in a synthetic
  namespace with the real repo path as `__file__`; module-level behavior is
  identical, but it is not a checkout switch.

## Verdict

**PASS (scoped).** The granular-freeze patch satisfies the stated contract: each
reachable frozen manifest is independently byte/SHA256/`checked_json` checked even
when another is missing; the deterministic regression is proven to fail under the
prior all-or-nothing implementation; live coverage is not falsified. No P1/P2
findings.

This review makes no acceptance claims: a green run here is not #84/#33/#26
acceptance, not Full/G6, and not official MIXED/entry promotion.
