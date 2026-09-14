# Independent Review — Acceptance-Frontier Offline Context Candidate

- Reviewer: CodeBuddy (independent reviewer slice)
- Date: 2026-09-14
- Reviewed HEAD: `e8defc1d8317892e022ee24de086b026c1317e5a` (verified via `git rev-parse HEAD`)
- Scope: two named candidates plus their directly bound plan file; offline only.

## 1. Candidates and hash verification

| File | Status | SHA256 | Match |
|---|---|---|---|
| `docs/coordination/acceptance-frontier.json` | untracked (`??`) | `885ea287c58ee412a1577cff18428a8b9425ff4b70e0c0ed9433bf18d46a16c2` | YES (spec + test constant + defer pin) |
| `validation/test_acceptance_frontier_context.py` | untracked (`??`) | `b8533f49d72f6d4bf5bcfd730d51c96c2be1b7381ba45b80e6f764f7df2036b0` | YES (spec) |

Bound plan file inspected read-only: `docs/plan/9-vendor-abi-defer-boundary.json`
(sha256 `2a7ac0f57d4cd9a981391ac47a5c8471b17f7a8769dfcc09d6852c8c58c43ba1`, git-tracked).
Its `host_bounded_gaps.acceptance_frontier` pin (lines 825-830) records
`path=docs/coordination/acceptance-frontier.json`, the identical SHA256, `tracked: false`,
and a reason containing "untracked" — consistent with the test's binding.

## 2. Test execution (proven behavior)

Command (exactly as mandated):

```
python -B -m unittest validation.test_acceptance_frontier_context -v
```

- Before staging (frontier untracked): **Ran 25 tests, OK, exit 0.**
- After-staging simulation: re-ran the same suite with a temporary `GIT_INDEX_FILE`
  (temp file outside the repo, `git read-tree HEAD` + `update-index --cacheinfo --info-only`
  adding `docs/coordination/acceptance-frontier.json`). **Ran 25 tests, OK, exit 0.**
  The real index was never touched — `git status --porcelain` still shows the frontier `??`.
- Live-tracking semantics confirmed: the suite never calls `git_tracked()` on the frontier
  path; `test_frontier_context_file_is_present` checks only OS existence
  (`validation/test_acceptance_frontier_context.py:285-288`). The historical
  `tracked: false` value stays bound via `TestDeferBoundaryPinBinding` against the
  unchanged defer JSON, while live tracking may change freely. Tests therefore pass
  both before and after the original is staged/committed.
- No file is written by the suite; `git ls-files` is its only subprocess (read-only).

## 3. Semantic checks

### Strict JSON behavior
`strict_loads` (`:69-96`) rejects:
- duplicate object keys, flat and nested (`object_pairs_hook`, tested at `:253-259`);
- `NaN`/`Infinity`/`-Infinity` constants (`parse_constant`, `:261-264`);
- float overflow such as `1e999` (`parse_float` + `math.isfinite`, `:266-268`);
- malformed/truncated/trailing input (`:271-273`).
Integer overflow is not applicable (Python ints are arbitrary precision; non-finite
integers do not exist), so the docstring's "numeric overflow such as 1e999" claim is
exactly what is enforced.

### Exact issue/path/pin semantics
- Version must equal `"1.1"`; `acceptance_frontier` must be a list whose issue IDs equal
  exactly `["#62", "#102", "#83", "#29", "#26"]` in order, with duplicates rejected
  (`validate_frontier`, `:174-188`). Positive tests at `:293-298` pass.
- Referenced repo paths: the bounded prefix regex extracts exactly the six expected paths
  in document order (verified live):
  `tools/run_joint_scheduler_windows.py`, `validation/lunar-29-terrain-reset-c8f05c6e`,
  `docs/plan/29-terrain-closure-report.md`, `docs/plan/26-closure-readiness-manifest.json`,
  `docs/2026-09-10-generated-e0-lifecycle.md`, `validation/codegen-e0-lifecycle-01/audit.json`.
  Each is asserted present in the working tree AND tracked in the git index
  (`require_tracked_present`, `:231-239`); all six verified tracked.
- Pin binding (`bind_defer_pin`, `:191-228`) is fail-closed: exactly one
  `host_bounded_gaps` entry may carry the frontier path; its key must be exactly
  `"acceptance_frontier"`; its `sha256` must equal the live frontier digest; `tracked`
  must be literally `False` (`is not False` rejects both `True` and a missing field);
  the frontier path must occur exactly once anywhere in the defer record.

### Context-only / non-acceptance scope
- No network, no GitHub query, no file writes, no build/runtime/native/ROS/FC/UE
  execution anywhere in the suite.
- `TestRecordedLiveStateOutsideOfflineVerification` (`:331-360`) asserts only recorded
  snapshot fields of the pinned document and the defer record's policy fields
  (`acceptance_claimed=false`, `acceptance_status_recommended="not_ready"`,
  `owner_decision.state="not_made"`, `github_mutated=false`), with explicit docstring
  non-claims. This matches the defer record's own `non_claims` and `scope_limits`.

### Meaningful negative coverage
Six in-memory mutations, none touching files (`:367-410`): hash drift, duplicate issue
entry, pin hash drift, `tracked` promotion to `true`, malformed JSON variants, and a
missing/untracked reference. All pass; each targets a distinct fail-closed branch.

## 4. Findings

### P1 (blocking)
None.

### P2 (must address before relying on this beyond its stated scope)
None.

### P3 (minor / informational)
- **P3-1** — `bind_defer_pin`'s "frontier path occurs exactly once in the defer record"
  check (`validation/test_acceptance_frontier_context.py:219-227`) has no dedicated
  negative test; no mutation demonstrates this branch failing closed.
- **P3-2** — `validate_frontier`'s exact-order/set check has no negative test for
  reordering or removing an issue entry; only duplicate-append is mutated (`:378-384`).
  The code would catch a reorder, but that behavior is not demonstrated by a test.
- **P3-3** — `TestStrictJsonLoader.test_rejects_malformed_json` (`:271-273`) and
  `TestNegativeMutations.test_malformed_json_rejected` (`:398-406`) substantially
  overlap (duplicate key / NaN / overflow / truncation in both). Harmless redundancy.
- **P3-4** — `EXPECTED_REPO_PATHS` equality couples to the first-occurrence order of
  path strings inside the hash-pinned document (`:300-302`). Safe while the document is
  hash-pinned, but any legitimate frontier revision must update the pin constant, the
  defer pin, and this list in lockstep.

## 5. Verdict

**PASS.** Both candidates match their specified SHA256 values; the mandated test command
passes 25/25 (exit 0) before staging and under an isolated after-staging simulation;
strict-JSON, issue/path/pin, and context-only semantics are correctly fail-closed; the
historical `tracked: false` pin remains bound independently of live tracking state.
Findings are limited to P3 negative-test breadth. Passing this offline slice does NOT
claim issue acceptance, owner approval, dependency closure, or any decision about
#9/#26/#29/#62/#83/#102 or any other ticket; recorded `OPEN`/`requires_owner_input`
fields are pinned-document snapshots only.

## 6. Nonclaims

- No candidate file or any existing file was edited; artifacts exist only in this
  review directory (gitignored via `.gitignore:53` `/validation/*/`).
- No stage, commit, or push was performed on the repository; the after-staging check
  used a temporary `GIT_INDEX_FILE` outside the repo and the real index is untouched.
- No native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight runs; no #83 work; no GitHub
  access or mutation.
