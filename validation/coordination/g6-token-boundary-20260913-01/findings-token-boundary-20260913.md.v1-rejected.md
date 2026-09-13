# Rejected v1 claims, function-token boundary module (2026-09-13)

Owner: `validation/coordination/g6-token-boundary-20260913-01`.
Status: **REJECTED**. This record preserves the claims of the first draft of the
token-boundary report, states why each is wrong, and points at the corrected evidence.

Preservation note, stated honestly: the v1 report file was overwritten by the corrected
report in the same working session, no version control operation was performed, and the
verbatim v1 text could not be recovered from the session's retained output (searched
`%TEMP%\dsh-*` spill and subprocess directories for its distinctive sentences, no
match). Rather than reconstruct prose that would itself be a new claim, this record
tabulates the rejected claims exactly as they were made and what replaced them. Any
consumer holding the v1 text should treat it as withdrawn in full.

## Rejected claims and their corrections

| # | v1 claim (as written) | Why it is wrong | Corrected evidence |
| --- | --- | --- | --- |
| 1 | The decisive fixture was `HEAD + DECL + WRAPPER_DEF + DEF + CALL` | That fixture contains **four** occurrences of the audited name, and the old helper classifies the real definition as a **second definition**, so it rejects the input on the occurrence-count rule. It never reaches the type/boundary question and therefore cannot demonstrate any boundary gap. | Four-occurrence fixture kept only as a regression guard: `test_both_reject_a_second_genuine_definition`. The decisive fixtures now have exactly three occurrences: `HEAD + DECL + WRAPPER_DEF + CALL` and `HEAD + DECL + DEF + PREFIXED_CALL`. |
| 2 | "The real definition becomes the call" | Unsupported by the actual `_classify_occurrence` in the git baseline. In the four-occurrence fixture the real definition is classified as a definition (a second one), not as a call. | `old_vs_new_evidence.py` prints the real classification list per occurrence: declaration / definition / call for the three-occurrence fixtures, and declaration / second-definition / call / call for the four-occurrence one. |
| 3 | The tests demonstrated the old gap | They asserted the four-occurrence count and then only exercised the **new** code, so the old behaviour was asserted nowhere. | `OldVersusNewBoundaryTests` now loads the pinned baseline and asserts, per fixture, that the **old** helper accepts and the **new** helper rejects, with exact classifications, exact insertion offsets, and byte-exact removal. |
| 4 | The comparison used an approximate mirror of the old helper | A hand-written mirror cannot support a claim about the old code. | The old side is the immutable baseline pinned by commit `5165781dc3607d08179c26f11b9af13f152fbf17` (`git cat-file blob <ref>:tools/…`, never `HEAD`), sha256 `0f3a79a4b5bf7d96a71f3337ee6f2e3b3c0ac767e59d8a2cd7aab7d742e3e3bd`, loaded in an isolated namespace with `__file__` set to the real tool path — no scratch file in `tools/`. |
| 7 | The baseline was addressed as `git show HEAD:…` | After the fix is committed, `HEAD` resolves to the NEW implementation and the old-side evidence would silently change to a tautology. | All old-side access uses the pinned commit id; `BaselinePinTests` asserts the ref is not `HEAD`, the 40-hex form, the sha256 and the blob id, and the evidence script refuses to print if the hash does not match. |
| 5 | A real vendor/source mispatch was being defended against | No vendor mispatch was ever observed. The fixture is synthetic. | Scope restated: the frozen archive/source SHA is the **primary** boundary; the identifier-boundary check is a secondary fail-closed structural guard. No vendor mispatch is claimed. |
| 6 | The docstring's "a same-name token in a comment, string literal or longer identifier never counts" | There is no C++ lexer; comment and string text is not interpreted, and is refused only when it changes the occurrence count or the recognized signature shape. | Docstring rewritten to say exactly that. |

## What survived from v1 (and is unchanged)

* The minimal boundary check itself (`_at_identifier_boundary` plus the
  `_IDENT_CHARS`/`chr()` comparison fix) and the exact `ValueError` message.
* The original `INSERTION` bytes, the pinned source SHA guard, the exact
  declaration/definition/call classification rule, and the candidate identity.
* The pinned-source and retained-identity tests, which were already correct.

## Pointer

Corrected report: `findings-token-boundary-20260913.md`.
Raw before/after evidence: `old_vs_new_evidence.py` (stdout is the record).
Hashes: `sha-receipt-20260913-03.json`.
