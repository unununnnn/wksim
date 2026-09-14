# Ingest manifest: interface decision packet context batch (2026-09-14-01)

- Role: CodeBuddy ingest-manifest owner (offline, no runtime work)
- Authoritative HEAD: `e8defc1d8317892e022ee24de086b026c1317e5a` (verified via `git rev-parse HEAD`; `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` exit 0)
- Scope: exactly the six batch inputs listed below plus the four manifest outputs in this directory; no input edited; nothing outside this manifest directory modified; nothing staged/committed/pushed; no native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight or #83 work executed.

## Inputs and verification performed

| Input | SHA256 (verified this session) |
| --- | --- |
| `docs/coordination/ds-interface-decision-packet-20260912.md` | `a7cfe224f2528a5651c6037eae7cf1547ae57e1dfe210c7792308ad247d5e382` |
| `docs/coordination/interface-decision-packet-ingest-note-20260914.md` | `e1e8171fc6ab46dba28b94ac550eca1893e9d844ddf22b46252f382742302632` |
| `validation/test_interface_decision_packet_context.py` | `89e96db007bb822a2d24ac25b2d07069046ee88e98b07ac84d4dbcd3cc3bf363` |
| `validation/coordination/codebuddy-interface-decision-context-independent-review-20260914-01/review.md` | `5a6ad3cb8d6cfffa43ccc3934c96758034005aa058ddbfa04f4f6f9ab96e01ee` |
| `validation/coordination/codebuddy-interface-decision-context-independent-review-20260914-01/review.json` | `f092644a592d10130da838d9427c0d829d31e2a5b268334b5836e82624e845c4` |
| `validation/coordination/codebuddy-interface-decision-context-independent-review-20260914-01/SHA256SUMS` | `1fa2b1edd923237b2aff743aaff3b5afc07e8f914aa96ec329e52cf061f00b74` |

Verification steps and results:

1. HEAD equals `e8defc1d8317892e022ee24de086b026c1317e5a`; the architecture ancestor commit is an ancestor of HEAD.
2. All six input files re-hashed this session; the three candidate hashes match the review's `candidate_sha256` exactly.
3. `review.json` strict-parsed with duplicate-key and non-finite-constant rejection: schema `wksim.codebuddy-independent-review.v1`, `reviewed_head` = `e8defc1d8317892e022ee24de086b026c1317e5a`, verdict `PASS`, findings P1=0, P2=0, P3=3 (all non-blocking, `blocks=false`).
4. The three candidate paths and hashes in `review.json` match this session's computed hashes exactly.
5. Mandated test re-run: `python -B -m unittest validation.test_interface_decision_packet_context -v` — exit code 0, `Ran 9 tests ... OK` (9/9, 0 failures, 0 errors, 0 skipped).
6. The review directory's `SHA256SUMS` verified with `sha256sum -c` relative to its own directory: `review.md: OK`, `review.json: OK` (exit 0; the sums file pins only `review.md` and `review.json`, excluding itself).

## Findings carried forward

The independent review's verdict is PASS with three P3 findings (P3-1 duplicate-record negative demonstration covers the audit pin only; P3-2 missing-field fail-closure promised but not negatively exercised; P3-3 defer-boundary Markdown registration unpinned). All three are non-blocking test-coverage/prose-precision observations. No P1 or P2 findings exist.

## Outputs (this directory)

- `exact-paths.txt` — exactly 10 repository-relative batch paths (six inputs + four manifest outputs) in sorted ordinal (byte-wise) order.
- `review.md` — this manifest report.
- `review.json` — strict JSON, schema `wksim.ingest-manifest.v1`, binding `reviewed_head`, `exact_paths_sha256`, all six input hashes, review verdict/findings counts, and the scope statement.
- `SHA256SUMS` — lowercase SHA256 for `exact-paths.txt`, `review.md`, `review.json` only, relative to this directory (the sums file excludes itself).

## Non-authority / non-acceptance scope

This manifest is an offline ingest-identity record only. It does not promote the decision packet, the ingest note, the offline test, or the independent review to decision authority; it does not approve budgets, select interfaces, or decide vendor ABI questions; and it does not accept or close #9, #26, #29, #33, #84, Full, G6, Goal, or any other ticket. Passing the offline admission test proves admission semantics, identity binding, and explicit supersession only — not UE consumers, not a real UE/WSL/FC/ROS2/DDS closed loop, not budget approval, and not vendor ABI availability. The packet's superseded "unique reader" statement and the #83 diagnostic-evidence boundary remain as recorded in the ingest note.
