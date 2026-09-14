# Delivery granular-freeze offline ingest manifest — codebuddy-delivery-granular-freeze-ingest-manifest-20260914-01

Generated 2026-09-14. Work class: review/ingest-manifest. Candidates untouched; existing files untouched; no git add/commit/push/stage/reset/clean; no GitHub changes; no native/WSL/ROS/DDS/SITL/FC/UE/MATLAB/models/builds/flights/user-process actions; unrelated dirty/untracked files preserved.

## Preconditions verified

- Branch: `main`; HEAD: `1884ea64c1fe99502ec7063f00f2f09a17b43ea5` (exact match).
- Architecture ancestor: `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` exit 0.

## Final commit batch — exactly 8 paths

`exact-paths.txt` contains exactly the 4 candidate paths (LF-terminated, no duplicates, no self-reference). The final commit batch is exactly those 4 candidates plus this ingest manifest's own 4 files (`exact-paths.txt`, `review.md`, `review.json`, `SHA256SUMS`) = 8 paths, no duplicates.

1. `validation/test_delivery_entry_contract.py` — tracked, modified (` M`); hash-bound below.
2. `validation/coordination/codebuddy-delivery-granular-freeze-independent-review-20260914-01/review.md`
3. `validation/coordination/codebuddy-delivery-granular-freeze-independent-review-20260914-01/review.json`
4. `validation/coordination/codebuddy-delivery-granular-freeze-independent-review-20260914-01/SHA256SUMS`
5. `validation/coordination/codebuddy-delivery-granular-freeze-ingest-manifest-20260914-01/exact-paths.txt`
6. `validation/coordination/codebuddy-delivery-granular-freeze-ingest-manifest-20260914-01/review.md`
7. `validation/coordination/codebuddy-delivery-granular-freeze-ingest-manifest-20260914-01/review.json`
8. `validation/coordination/codebuddy-delivery-granular-freeze-ingest-manifest-20260914-01/SHA256SUMS`

Note: `/validation/*/` (`.gitignore:53`) currently ignores new subdirectories of `validation/`, so paths 2–8 are untracked-and-ignored; the batch owner would need `git add -f` (or an ignore negation) at commit time. No git action was performed by this manifest.

## Candidate SHA256 bindings (verified, expected match)

| File | Size (bytes) | Status | SHA256 |
|---|---|---|---|
| validation/test_delivery_entry_contract.py | 23233 | tracked, modified | bae759e19d121b2e9b62920aa636203042ab5230dfb72f92330d4d2256dfb350 |
| .../codebuddy-delivery-granular-freeze-independent-review-20260914-01/review.md | 5448 | untracked (ignored) | fb8c6d463f8d823029d9956f79d4da2c22f62348a5d34c117d44f8a79c5a2fd6 |
| .../codebuddy-delivery-granular-freeze-independent-review-20260914-01/review.json | 8450 | untracked (ignored) | 865e361105a8d830748ef181354082f996eedb3a9f407c8b875256dea0e8ec6c |
| .../codebuddy-delivery-granular-freeze-independent-review-20260914-01/SHA256SUMS | 154 | untracked (ignored) | 4e25f44ccfa8cab269ff7baa851e630d82bdb71c475a3fd058bf1983a7048501 |

All four computed SHA256 values match the expected values from the dispatch exactly.

## Receipt validation

- `review.json` strict parse: OK (duplicate-key rejection via `object_pairs_hook`, NaN/Infinity rejection via `parse_constant`).
- `SHA256SUMS` of the independent review: 2 entries, LF line terminators; `sha256sum -c` passes — `review.md: OK`, `review.json: OK` (the SUMS file correctly excludes itself).
- Review content: schema `wksim.delivery-granular-freeze-independent-review.v1`; verdict **PASS (scoped)**; findings P1=0, P2=0, P3=1 ("skip reason text generalized; aggregated missing list no longer shown" — cosmetic, no change requested).
- Candidate diff scope: working-tree change of `validation/test_delivery_entry_contract.py` only (+37/−13; 20 → 21 test methods).

## Test run

Command (exactly as required): `python -B -m unittest validation.test_delivery_entry_contract -v`

- Ran **21** tests — **OK (skipped=1)**, 0 failures, 0 errors, exit code 0, ~2.2s.
- Exactly one skip, the expected granular AP-manifest subtest:
  `FrozenManifestIdentityTests.test_frozen_external_manifests_read_bytes_match_sha256_and_unique_keys (posix='/root/wksim-ap-mixed-fhuf05l9/mixed-build.json') ... skipped 'frozen Linux manifest not reachable'`.
- Stderr argparse usage text on some tests is expected output from CLI rejection paths. The skip is not counted as coverage.

## P3 and limitations

- **Missing AP bytes remain unverified.** The frozen manifest `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json` is absent in this environment; its byte/SHA256/`checked_json` match is NOT live-covered here — only its per-item granular skip path is proven. Coverage of that item depends on an environment where it is reachable.
- The other two reachable frozen manifests (`/root/wksim-joint-control-c2IXOr/build.json`, `/root/wksim-ros2-Rzj3Pf/message-build.json`) were checked **independently** by the reviewed test (per-item byte/SHA256/`checked_json`) and cross-confirmed in the review's read-only probe A; the new regression is proven to fail under the prior all-or-nothing implementation (review probe B), and live coverage is not falsified (probes C/D).
- Reachability of the two manifests is a host-side `\\wsl$\Ubuntu-22.04` UNC file-read fact only; no WSL command was issued.
- Frozen digests were compared only to the `FROZEN_*` constants in the test file; no cross-check against published identity documents.
- Only the scoped candidate was reviewed upstream; other modified/untracked worktree files were not read in depth and are preserved untouched.
- All 8 batch paths except the modified test file are currently ignored by `.gitignore:53`; committing requires force-add by the batch owner. No git action performed here.
- No subagent was dispatched: the interface cannot select or verify the policy-required subagent settings, so per policy the work was performed in the main agent; this limitation is reported rather than substituting settings.

## Acceptance not claimed

This PASS covers only offline delivery-contract ingest (hash binding, receipt validation, and the required offline unit-test run). No issue acceptance (#26, #33, #84), no Full/G6/Goal acceptance, and no owner approval is claimed, granted, or transferred by this manifest. A green run here does not promote MIXED/entry or transfer any frozen-manifest PASS beyond items actually reachable in this environment.

## Manifest files

`SHA256SUMS` in this directory covers `exact-paths.txt`, `review.md`, and `review.json` (this manifest's own files; it does not cover itself and does not reference the candidates, which are bound in this document and in `review.json`).
