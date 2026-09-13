# Function-token boundary review and fix, solve-candidate builder (2026-09-13)

Owner: `validation/coordination/g6-token-boundary-20260913-01`.
Read-only source inspection plus pure-Python checks: no compile, model, MATLAB, ROS,
UE, native run, or WSL workload. No vendor publication, no vendor body printed. The
frozen comparator and its test were not touched.

Supersedes the rejected first draft, whose claims (four-occurrence fixture, "the real
definition becomes the call", tests that only exercised the new code, an approximate
old-helper mirror, an implied vendor mispatch) are itemised with corrections in
`findings-token-boundary-20260913.md.v1-rejected.md`. The verbatim v1 text was
overwritten in-session and is not recoverable; that record says so explicitly.

## 1. Method: the old side is an immutable pinned baseline

Every "old" behaviour below comes from executing the pre-fix implementation pinned by
commit `5165781dc3607d08179c26f11b9af13f152fbf17`, whose blob for
`tools/build_first_step_solve_candidate.py` is `df15d795856583eae101e3d1f549ecfc29f4e2e7`
with sha256 `0f3a79a4b5bf7d96a71f3337ee6f2e3b3c0ac767e59d8a2cd7aab7d742e3e3bd`:

```
git cat-file blob 5165781dc3607d08179c26f11b9af13f152fbf17:tools/build_first_step_solve_candidate.py
```

The ref is the **commit id, never `HEAD`**, so the old side cannot silently become the
new implementation once this fix is committed; `BaselinePinTests` asserts the sha256 and
the blob id on every run, and `old_vs_new_evidence.py` refuses to print evidence if the
hash does not match. The baseline bytes are compiled into an isolated module namespace
with `__file__` set to the real tool path, so the baseline's
`Path(__file__).with_name('build_first_step_trace.py')` lookup resolves **without
writing any scratch file into `tools/`**. The "new" side is the working-tree tool.
`old_vs_new_evidence.py` prints both, side by side, and `test_token_boundary.py`
asserts the same comparison.

## 2. Fixtures: exactly three occurrences each

`NAME` = `rt_mrdivide_U1d1x3_U2d_9vOrDY9Z`. All three fixtures contain exactly three
occurrences; the mutations replace one anchor with a prefixed name that keeps the
canonical parameter list, so nothing relies on a lone-insert defect.

| Fixture | Bytes of `NAME` | Preceding byte per occurrence | Old result | New result |
| --- | --- | --- | --- | --- |
| POSITIVE `HEAD+DECL+DEF+CALL` | 3 | `' '`, `' '`, `' '` | classify = declaration / definition(422) / call; **accepted**, insertion at 422 (real definition) | identical: declaration / definition(422) / call; **accepted**, insertion at 422 |
| REPLACED-DEF `HEAD+DECL+WRAPPER_DEF+CALL` | 3 | `' '`, **`'_'`**, `' '` | classify = declaration / **definition(428)** / call; **accepted**, insertion at 428 | classify = declaration / **rejected** / call; **rejected** |
| REPLACED-CALL `HEAD+DECL+DEF+PREFIXED_CALL` | 3 | `' '`, `' '`, **`'_'`** | classify = declaration / definition(422) / **call**; **accepted**, insertion at 422 | classify = declaration / definition(422) / **rejected**; **rejected** |

Two different failure modes, both real:

* **REPLACED-DEF**: the old helper treats the prefixed wrapper's `outer_` + canonical
  signature + `{` as *the definition* and inserts the branch **inside the wrapper**.
  In that fixture there is no genuine definition at all, so the old helper silently
  patches a different function.
* **REPLACED-CALL**: the old helper treats the prefixed call as *the call site*, so the
  unique-occurrence count is satisfied and the branch is inserted at the real
  definition while the fixture's call is to a different function.

The earlier claim that "the real definition becomes the call" was wrong. In the
combined four-occurrence fixture the real definition is classified as a **second
definition**, and the old helper rejects the input on the count rule before any type
question arises. That four-occurrence case is therefore **not** part of the fixed gap
and is kept only as a regression guard (`test_both_reject_a_second_genuine_definition`).

## 3. The fix and its honest scope

`_at_identifier_boundary(src, pos)` rejects an occurrence whose preceding or following
byte is an identifier character. `_classify_occurrence` applies it first and raises
`ValueError('rt_mrdivide occurrence is part of a longer identifier, not this
function')`. The `_IDENT_CHARS` set is a set of single characters compared against
`chr(src[pos-1])`, because comparing a one-byte `bytes` slice against a set of ints
silently never matches.

Scope of the defense, stated plainly:

* The **primary boundary is the frozen archive/source SHA**: `builder.instrument`
  refuses any generated cpp whose bytes do not hash to the pin, so this tool only ever
  patches the reviewed artifact. The identifier-boundary check is a secondary,
  fail-closed structural guard, not a claim about an observed vendor mispatch, and no
  such mispatch is asserted anywhere.
* There is **no C++ lexer**. Comments and string literals are not interpreted; text
  inside them is refused only because it changes the occurrence counts or the
  recognized signature shape. The docstring now says exactly that instead of claiming
  such tokens "never count".
* Positive POSITIVE fixture, the pinned source, the `INSERTION` bytes and the candidate
  identity are all unchanged by the rule.

## 4. Tests, corrected

`test_token_boundary.py` (13 tests, all passing):

* `BaselinePinTests` asserts the old side is pinned to the commit id (not `HEAD`), that
  its bytes hash to `0f3a79a4…`, and that its git blob is `df15d795…`.
* `OldVersusNewBoundaryTests` loads that pinned baseline and asserts, on each fixture,
  that **the old helper accepts and the new helper rejects**, with the exact
  classification lists and insertion offsets; POSITIVE is asserted accepted and
  byte-identical under both implementations first.
* `BoundaryRuleTests` covers the boundary helper itself, the comment/string
  over-counting rejections (labelled as counting, not parsing), and missing anchors.
* `PinnedSourceTests` re-asserts the three whole-identifier occurrences on the pinned
  source and that the prepared candidate still hashes to the retained identity.

| Suite | Result |
| --- | --- |
| `test_token_boundary.py` (focused, this module) | **13 passed** |
| `validation/test_first_step_solve_candidate.py` (existing builder test) | **18 passed** |
| `verify_preparation_identity.py` (pure candidate identity) | **17/17 checks passed** |

Only these three were rerun after the correction. The frozen comparator suite and the
unrelated audit suite were not rerun and were not touched.

## 5. Retained-source production identity

`verify_preparation_identity.py`, local retained material only:

* pinned generated source `a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019`;
* instrumented source `3e271d64f46191a1e5dd41c92ae215ea5321ec42ece31dd1ada389be3ece9182`;
* **candidate source `0107001b1a4aeef4591b2516ffad338866e4645a59c519c3c3e367073acac001`**,
  byte-identical to the retained `candidate-command.json` `instrumented_cpp_sha256`;
* frozen input `721c88bf…`, recorder `b422c6f9…`, shared builder `8a07c8ca…`, archive
  `d528b5d2…` unchanged; `diagnostic_only: true`, `production_replacement: false`;
* the full `build()` path runs against the pinned archive writing only into a temp
  directory, and its recorded metadata matches the written files.

Filename note preserved: the retained `prepare.py` wrote
`Exp1_MinModelTemp.candidate.cpp`; this tool writes `Exp1_MinModelTemp.cpp`. Identity is
by content.

## 6. Limitations

* The boundary test prevents mis-anchoring; it does not make the classifier a parser.
  A comment or string containing a whole-`NAME` token with a canonical signature and
  `{` would still be classified structurally, and only the count rule or the pinned SHA
  stands in its way.
* The numeric branch, its arithmetic, and the trace builder were not modified; the
  previously recorded finding that the branch is 1 ULP less accurate than correctly
  rounded division is unaffected.

## 7. Commands and hashes

```
cd C:/Users/PC/Documents/odid编译/wksim
python -B validation/coordination/g6-token-boundary-20260913-01/old_vs_new_evidence.py
python -B -m pytest validation/coordination/g6-token-boundary-20260913-01/test_token_boundary.py -q
python -B -m pytest validation/test_first_step_solve_candidate.py -q
python -B validation/coordination/g6-token-boundary-20260913-01/verify_preparation_identity.py
```

Hashes are in `sha-receipt-20260913-03.json`. Non-claims: no model, MATLAB, native,
build or ROS execution; no threshold, gate, budget, stage-mapping, numeric-branch or
production change; no edit to retained evidence or to the frozen comparator.
