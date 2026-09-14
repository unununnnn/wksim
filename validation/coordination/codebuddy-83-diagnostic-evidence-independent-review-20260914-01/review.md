# Independent Review: test_83_diagnostic_evidence_originals.py (2026-09-14-01)

Reviewer: independent CodeBuddy review agent. No owner approval or acceptance is
claimed or implied by this document.

## Scope

Candidate under review:

- `validation/test_83_diagnostic_evidence_originals.py`
  - expected SHA256 `ecfebd1a00904d59d800fb3174d33cfaa4b75868d81b2e0ecd2d1ccc438efbc9`
  - observed  SHA256 `ecfebd1a00904d59d800fb3174d33cfaa4b75868d81b2e0ecd2d1ccc438efbc9` (match)

Immutable originals (read-only reference inputs, both hash-verified before review):

- `docs/coordination/ds-7bdfxkb-diagnostic-analysis.json`
  - expected `692a067123126797862edd89c2961634530ae04374e8ba1b4f69fe2b8e12981e`
  - observed  `692a067123126797862edd89c2961634530ae04374e8ba1b4f69fe2b8e12981e` (match)
- `docs/coordination/omp-83-freeze-check-20260912.md`
  - expected `273a99613f707dba2fb9d0c92f18de0887ccdab900e031025963d4464d13f638`
  - observed  `273a99613f707dba2fb9d0c92f18de0887ccdab900e031025963d4464d13f638` (match)

HEAD:

- expected `1884ea64c1fe99502ec7063f00f2f09a17b43ea5`
- observed `1884ea64c1fe99502ec7063f00f2f09a17b43ea5` (match)

Review focus: correctness and fail-closed behavior of (a) strict JSON duplicate /
non-finite rejection, (b) schema and exact numeric types, (c) all required
recorded arithmetic, (d) robust extraction of the three manifest table rows,
(e) candidate pointer existence and git tracking.

## Command and results

Exactly one suite command was run:

```
python -B -m unittest validation.test_83_diagnostic_evidence_originals -v
```

Result: `Ran 20 tests in 0.019s` — `OK` (20/20 passed, 0 failures, 0 errors,
0 skipped). Exit code 0.

In addition, TEMP-only pure negative probes (script written to and executed from
a mktemp directory, deleted afterwards; no repository writes, no repo file
modified) exercised the candidate's `strict_loads` / `_require` helpers and the
arithmetic assertions against mutated in-memory copies:

| Probe | Result |
|---|---|
| duplicate key, top level | rejected (ValueError) |
| duplicate key, nested object | rejected (ValueError) |
| `NaN` / `Infinity` / `-Infinity` constants | rejected (ValueError) each |
| plain `json.loads` accepts what strict rejects | confirmed by suite sanity test |
| bool where int required | rejected (`type(v) is not int` excludes bool) |
| float where int required | rejected (AssertionError) |
| `entry_lateness_total_ns` tampered +1 in a copy | reconciliation `entry+post_entry==total` becomes False (detected); untampered copy True |
| overflow literal `1e400` | **accepted as `inf`** — see finding P3-01 |

## Findings

### P3-01 — strict loader does not reject numeric-overflow non-finites

`strict_loads` (test file lines 64-70) rejects `NaN`/`Infinity`/`-Infinity` via
`parse_constant` and duplicates via `object_pairs_hook`, but Python's JSON
decoder parses an overflow literal such as `1e400` to `float('inf')` without
invoking `parse_constant`. A non-finite value could therefore enter an
un-type-checked float field (e.g. `observed_share.*`, tail-bucket means).

Impact assessment: low. Every numeric field used in the pinned assertions
(`structure`, `latch_reconciliation`, `release_excess_split`,
`dominant_events.rows[].entry_lateness_ns`, `probe_outcomes`,
`sample_count`) is exact-type-checked as `int`, so an `inf`/float there fails
closed. The two originals are also SHA256-pinned by
`TestEvidenceOriginalHashes`, so their bytes cannot change without detection.
No P1/P2 impact.

### P3-02 — two redundant structure fields left unreconciled (informational)

`structure.rate_unmet` (1) is not cross-checked against
`structure.probe_outcomes.rate_unmet` (1), and `structure.rate_timing_probe`
(27435) is not cross-checked against `probe_phases.sample_count` (27435).
Both values are consistent in the pinned original; adding the checks would
widen coverage but is not required by the review scope. No fail-closed gap.

### Correctness observations supporting PASS

- Strict rejection is enforced at module import (`DOCUMENT = strict_load(...)`,
  line 105): a duplicate-key or non-finite constant anywhere in the original
  JSON aborts the whole module, so every test errors — fail-closed.
- `_require` uses `type(value) is not expected_type`, correctly rejecting bool
  masquerading as int and float-as-int.
- All required arithmetic verified against the pinned original:
  - `intervals (27433) == groups (27434) - 1`
  - `recorded_latch_lateness_ns == total_ns == 100050657` (pinned constant)
  - `entry_lateness_total_ns (26515920) + post_entry_excess_total_ns (73534737)
    == 100050657`
  - dominant rows `20749745 + 3057160 + 2634691 = 26441596 <= 26515920`
  - `started (27434) + rate_unmet (1) == sample_count (27435)`
  - `max_group_start_lateness_ns == last_group_start_lateness_ns == 99880816`
    (pinned constant)
  - `last_group_boundary_tick == rate_unmet_tick == 109776` (pinned constant)
- Manifest extraction regex anchors the role as first table column, captures the
  64-hex SHA from the third column, and asserts exactly one match per role in
  the Markdown — ambiguous or missing rows fail closed. All three recorded
  SHAs (`ap`/`control`/`message`) match the OMP freeze-check table.
- Candidate pointer: `candidate_pointer.document` must be a str, must not
  contain a `..` path part, must exist as a file, and must be tracked
  (`git ls-files --error-unmatch`; nonzero exit fails the assertion).
  Independently confirmed: `docs/plan/33-rate-measured-candidate-20260912.md`
  exists (13417 bytes) and is tracked.

## Scope limitations

- Static review of the three files named above only; no other repository file
  was read for judgment beyond `git ls-files` tracking of the pointer target.
- Only the single unittest command above was executed, plus TEMP-only pure
  negative probes of the test's own helpers. No #83 execution, no
  native/build/runtime/WSL/MATLAB/ROS/DDS/SITL/FC/UE/flight commands were run.
- No source, test, or original file was edited; no git staging/commit/push/
  reset/clean was performed.
- Arithmetic was reconciled from recorded values only; no analyzer, dataset, or
  runtime behavior was re-executed or re-measured.
- This review verifies the test's correctness against the two pinned originals;
  it does not validate the diagnostic analysis content itself and claims no
  owner approval or #83 acceptance.

## Verdict

**PASS** — 20/20 tests OK; expected/observed HEAD and all three SHA256 values
match; no P1 or P2 findings (two P3 findings recorded above).
