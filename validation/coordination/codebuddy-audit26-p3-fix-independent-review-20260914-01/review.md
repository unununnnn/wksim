# Independent Review — #26 P3-fix patch (candidate: validation/test_audit_26_current_source_plan.py)

- Reviewer: CodeBuddy (independent), 2026-09-14
- Checkout/HEAD at review time: `1884ea64c1fe99502ec7063f00f2f09a17b43ea5` (verified `git rev-parse HEAD`)
- Candidate: `validation/test_audit_26_current_source_plan.py` (working-tree diff vs HEAD; `M`, uncommitted)
- Candidate SHA256 (current): `b348f282c2dc55372796ca34cc14c2bbde73a05bd52fa26603e4f378b7fe2730` — matches dispatch expectation exactly.
- Diff size: 92 lines (80 insertions, 12 deletions), one file.

## Scope

Review of the working-tree diff only, per dispatch:

1. AST helper `checker_expected_staged_sources()` robustness and fail-closed behavior.
2. Skip guards for private generation / MATLAB prerequisites; must skip clearly and must not mask malformed existing data.
3. Strict-JSON tests: correct distinction between parse-time rejection (duplicate keys, NaN/Infinity literals) and downstream finite-number rejection (1e999).
4. Run only `python -B -m unittest validation.test_audit_26_current_source_plan -v` plus TEMP-only pure negatives.

No candidate or source/receipt edits were made; all writes are confined to this new coordination directory (gitignored via `.gitignore:53` `/validation/*/`) and `%TEMP%\audit26_p3_review_negatives\`.

## Verified behavior (proven by execution)

### 1. AST helper (candidate lines 70–91)

The checker's pin is a single local set literal at `tools/audit_26_closure_readiness.py:1373` inside the build-manifest verifier; the helper walks the checker AST for an `ast.Assign` whose value is an `ast.Set` and whose target is named `expected_staged`, returning the constant elements.

Proven by TEMP-only probes against the real helper (ROOT patched to synthetic trees):

- A1: real checker yields exactly the six pinned sources `{Exp1_MinModelTemp.cpp, Exp1_MinModelTemp.h, rtwtypes.h, model.cpp, rtw_continuous.h, rtw_solver.h}`.
- A2: exactly one `expected_staged` assignment exists in the checker today (count=1), so first-match ambiguity is not live.
- A3: literal absent → `AssertionError("expected_staged set literal not found in tools/audit_26_closure_readiness.py")` — fails closed with the intended diagnostic.
- A4: `expected_staged = some_other_set` (non-literal) → AssertionError — fails closed.
- A5: `expected_staged: frozenset = {...}` (AnnAssign form) → AssertionError — fails closed (helper matches `ast.Assign` only).
- A8: `expected_staged = {}` (parses as Dict, not Set) → AssertionError — fails closed.
- A6: valid literal extracted verbatim.
- A7 (see Observations P3-1): a non-constant element (`{"model.cpp", *extra}`) does **not** raise at extraction; it returns a set containing an AST node (`{'str', 'Name'}`) that can never equal the driver's six-source set, so the downstream `assertEqual` still fails — fail closed, but later and with a confusing diagnostic.

### 2. Skip guards (candidate lines 184–187, 198–201)

Both private trees exist on this machine (`validation/codegen-e0/short-cycle-codegen-01/` and `D:/matlab/install date/simulink/include/`), so the real suite run took no skip on these paths. Proven by TEMP-only probes running the real test methods with the driver defaults patched:

- B1: absent generation tree → `skipTest("private generation evidence tree absent: <path>")`, no failure/error.
- B2: existing but malformed (empty) generation tree → real test failure, **not** a skip — existing malformed data is not masked.
- B3: absent MATLAB include → `skipTest("private MATLAB include tree absent: <path>")`, no failure/error.
- B4: existing but malformed (empty) MATLAB include → real test failure, not a skip.

The guards use `.exists()`, so an existing-but-wrong tree proceeds into the gate and fails loudly; only true absence skips.

### 3. Strict-JSON tests (candidate lines 656–693, CheckerStrictJsonTests)

Verified against the real checker helpers (`_load_json` at checker:140, `_strict_object_pairs` at :127, `_reject_constant` at :136, `_strict_number` at :192):

- C1: duplicate key `{"a": 1, "a": 2}` → `AuditDataError` carrying `duplicate JSON key: a` (wrapped as `"hostile input is malformed JSON: duplicate JSON key: a"`; the test's `assertRaisesRegex` searches, so it matches — proven by the suite pass).
- C2: `NaN` / `Infinity` / `-Infinity` literals → `AuditDataError` `non-finite JSON number: …` via `parse_constant` at parse time.
- C3/C6: `1e999` decodes to `float('inf')`; a spy on `_reject_constant` confirms `parse_constant` is **never invoked** for overflow literals, so the strict loader alone accepts `1e999` (and `-1e999` → `-inf`). The test correctly models this: it asserts loader acceptance, then proves the downstream gate `_strict_number(inf)` raises `AuditDataError` `… must be a finite …`. The checker really does route the relevant manifest numbers through `_strict_number` (checker:1441–1453 for probe fields), so the test's wording is honest.
- The three tests therefore distinguish parse-time rejection (duplicate keys, non-finite literals) from downstream finite rejection (overflow literals) exactly as the dispatch requires.

## Test run (mandated command)

`python -B -m unittest validation.test_audit_26_current_source_plan -v` on Python 3.13.11, Windows:

- Ran **52 tests**: **51 ok, 0 failures, 0 errors, 1 skipped** (0.094s). Exit 0.
- The single skip is the pre-existing, environment-conditional `test_checker_maps_windows_provenance_to_mnt_on_posix_hosts` ("POSIX-specific mapping rule") — not part of this diff and correct on a Windows host.
- The new generation/MATLAB skips did not trigger locally (both trees present); their behavior is proven by the TEMP probes above, not by the suite run.

TEMP-only negative probes: 22/22 pass (`A1–A8, B1–B4, C1–C6`), script at `%TEMP%\audit26_p3_review_negatives\negatives.py`, exit 0.

## Findings

- P1 (blocking): none.
- P2 (should fix before merge): none.
- P3 observations (non-blocking, for the record):
  - P3-1: `checker_expected_staged_sources` builds `{elt.value for elt in node.value.elts}` (candidate line 88). A non-constant element (e.g. a starred unpack) does not raise at extraction; it yields a garbage set (an AST node) that can never equal the driver set, so the suite still fails — fail closed, but only at the downstream `assertEqual` with a confusing repr. A `isinstance(elt, ast.Constant)` guard would localize the failure. Proven: probe A7.
  - P3-2: The helper binds to the first `expected_staged` set literal in `ast.walk` (breadth-first) order. Today exactly one exists (verified); if a second same-named literal were ever introduced earlier in walk order, the helper would silently compare against the wrong one. Acceptable now; a count assertion would harden it.
  - P3-3: The strict-JSON test proves `_strict_number` rejects inf directly, and the checker's probe-field validation does call it (checker:1441–1453), but the test does not itself trace a decoded manifest value into that call site. Scope of proof is stated honestly in the docstring; noting for completeness.

## Boundaries honored

- No edits to the candidate or any source/receipt file; the only new repo content is this directory (gitignored).
- No WSL, native, ROS/DDS, SITL, FC, UE, MATLAB execution, model build, or flight activity.
- No `git add/commit/push`, no GitHub writes.
- The worktree carries other pre-existing modifications unrelated to this review (`docs/Prometheus.gitmodules.reference`, `validation/coordination/short-cycle-dispatches.json`, `validation/test_delivery_entry_contract.py`, and untracked coordination files); none were touched by this review.

## Verdict

**PASS — accept the P3-fix patch.** The AST helper extracts the checker's `expected_staged` literal robustly and fails closed on every malformed form probed; the private-prerequisite skips are clear and do not mask malformed existing data; the strict-JSON tests correctly separate parse-time rejection from downstream finite-number rejection. The mandated suite is green (52 tests, 1 pre-existing environment skip). Observations P3-1..P3-3 are non-blocking hardening notes for the parent ticket.
