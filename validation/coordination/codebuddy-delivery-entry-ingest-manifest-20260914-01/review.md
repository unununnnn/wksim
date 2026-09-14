# Delivery-entry offline contract ingest manifest — codebuddy-delivery-entry-ingest-manifest-20260914-01

Generated 2026-09-14. Work class: review/ingest-manifest. Candidates untouched; existing files untouched; no git commit/push; no GitHub changes; no native/WSL/ROS/DDS/SITL/FC/UE/MATLAB/models/builds/flights/user-process actions.

## Preconditions verified

- Branch: `main`; HEAD: `5370b2324672c9036d41239cb93e21fc5eb42897` (exact match).
- Architecture ancestor: `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` exit 0.

## Exact commit batch

`exact-paths.txt` contains exactly the seven candidate paths, LF-terminated, no duplicates:

1. `validation/test_delivery_entry_contract.py` (untracked; proposed for `git add`; no git action performed here)
2. `validation/coordination/cursor-next-frontier-contract-audit-20260914-01/review.md`
3. `validation/coordination/cursor-next-frontier-contract-audit-20260914-01/review.json`
4. `validation/coordination/cursor-next-frontier-contract-audit-20260914-01/SHA256SUMS`
5. `validation/coordination/codebuddy-delivery-entry-contract-review-20260914-01/review.md`
6. `validation/coordination/codebuddy-delivery-entry-contract-review-20260914-01/review.json`
7. `validation/coordination/codebuddy-delivery-entry-contract-review-20260914-01/SHA256SUMS`

## Current SHA256 bindings

| File | SHA256 |
|---|---|
| validation/test_delivery_entry_contract.py | 390f9061ec74dae1df07067a73ed2ea5433f75485682bee47d1e789a99364075 |
| .../cursor-next-frontier-contract-audit-20260914-01/review.md | 9c9c346bd8477751fe0110e4bba0115bbcff1d346b39d9ea822b5461dd83066f |
| .../cursor-next-frontier-contract-audit-20260914-01/review.json | 9046382ce129211c3cf65917eca9873bf513402f92ce8050e230ecdc96585686 |
| .../cursor-next-frontier-contract-audit-20260914-01/SHA256SUMS | 0430d936d5c1f50dec1f4f38da06d670a1fbd67a3063f4451f747c0ed0f945bd |
| .../codebuddy-delivery-entry-contract-review-20260914-01/review.md | a5cfcfe84d2c38a84b715cd9b8920e5f07e4291626a534582cd967749a7875e7 |
| .../codebuddy-delivery-entry-contract-review-20260914-01/review.json | 26104558ff2d1a27313f82d3707876bd4fc5d252c354ea7cb808570b2cf22f40 |
| .../codebuddy-delivery-entry-contract-review-20260914-01/SHA256SUMS | 1b162d38cdc6162d03879b7a8084cb0d8d2ae66a136169c6c8f1b7d2eff8fb82 |

## Delivery hash history — explicit distinction

- Historical audited delivery hash (pre-repair): **682f3b20b29a1312becad6ec519fdb8434ff09270af118e55c23e3986cdcc808**
- Current delivery hash: **390f9061ec74dae1df07067a73ed2ea5433f75485682bee47d1e789a99364075**
- These differ. The historical audit receipt's FAIL and its four delivery P2 findings apply to the 682f3b20 pre-repair candidate only and are **not** transferred to the current file. The historical old SHA remains explicit in this manifest as required. The current PASS applies only to 390f9061.

## SUMS validation

- `cursor-next-frontier-contract-audit-20260914-01/SHA256SUMS`: 2 entries, **CRLF** line terminators. Validated by CRLF-tolerant in-memory parsing: review.md OK, review.json OK — ALL OK. History not rewritten. (Strict `sha256sum -c` formatting would reject CRLF; that is a byte property of preserved historical evidence, not a hash mismatch.)
- `codebuddy-delivery-entry-contract-review-20260914-01/SHA256SUMS`: 2 entries, LF. review.md OK, review.json OK — ALL OK.

## JSON strict parse

Both review.json receipts parsed with duplicate-key rejection (object_pairs_hook) and NaN/Infinity rejection (parse_constant):

- historical: OK (overall=FAIL)
- current: OK (overall=PASS)

## Test run

Command (exactly as required): `python -B -m unittest validation.test_delivery_entry_contract`

- Ran 20 tests — OK (skipped=1), 0 failures, 0 errors, exit code 0.
- Stderr argparse usage text is expected output from CLI rejection-path tests.
- Skip behavior: 1 test skipped. The non-verbose run does not identify which test skipped. The suite has exactly two conditional skip sites: line 419 (frozen-manifest identity) and line 463 (fe3 sibling) of `validation/test_delivery_entry_contract.py`. The current receipt's run recorded the frozen-manifest identity test as the skip with `counts_as_coverage: false`. The skip is **not** counted or called coverage here.

## Receipt statuses

- Historical (`cursor-next-frontier-contract-audit-20260914-01`): overall **FAIL**; P1=0, P2=4 (all delivery: string-only assertions, external fixed-hash-as-evidence, fail-open sibling continue, fe3 treated as current entry), P3=5.
- Current (`codebuddy-delivery-entry-contract-review-20260914-01`): overall **PASS**; P1=0, P2=0, P3=5 (P3-1..P3-5 recorded, none blocks ingest).

## Limitations

- The single skip in this manifest's own run is not attributed to a specific test (non-verbose output); two candidate skip sites exist in source.
- No frozen Linux manifest was byte/hash-verified on this machine in this run.
- WSL reachability is intermittent on this host; skip-vs-pass of sibling/frozen-manifest tests can flip between runs without repo changes.
- admit() success paths are intentionally not exercised by the suite; only early rejection is covered.
- Auditor `--output` overwrite refusal (`tools/audit_pv_trajectory.py:881-888`) is not pinned by the suite.
- Source `FINAL_*` constants are not cross-checked against doc-published freeze constants by the suite.
- Historical SUMS is CRLF; validated via CRLF-tolerant in-memory parsing without rewriting history.
- No subagent was dispatched: the interface cannot select or verify the policy-required subagent settings, so per policy the work was performed in the main agent; this limitation is reported rather than substituting settings.

## Acceptance not claimed

`#26`, `#33`, `#84`, `Full`, `G6`, and the short-cycle `Goal` are **not** accepted or claimed by this manifest. This manifest only binds hashes, records receipt statuses, and defines the exact ingest batch.

## Manifest files

`SHA256SUMS` in this directory covers `exact-paths.txt`, `review.md`, and `review.json` (this manifest's own files).
