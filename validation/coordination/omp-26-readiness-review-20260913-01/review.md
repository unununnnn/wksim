# Independent review: uncommitted #26 readiness fix (2026-09-13)

Reviewer: omp main agent. Read-only over `tools/audit_26_closure_readiness.py`,
`validation/test_audit_26_closure_readiness.py`,
`validation/coordination/ds-26-pin-drift-20260913-01/historical-wrapper-identities.json`
and the frozen original it references. No repository files were modified; all
reproductions run in temp directories. Machine-readable twin: `review.json`;
reproductions: `adversarial_repro.py` → `adversarial-output.json`.

## Baseline facts (verified)

- HEAD `72ef95d28eaa87490292e77a81b1de515d606c1e`; `f333316e…` is an ancestor (`git merge-base --is-ancestor` exit 0).
- Uncommitted diff in scope: audit tool +244/−20, test file +280.
- Frozen original `validation/lunar-20-epoch-1/…/Simulator/wksim_core/model.cpp`: sha256 `3f325678…`, 1864 B, tracked at HEAD (commit `4e161e2`), byte-identical to HEAD. Matches the declaration exactly.
- Current canonical wrapper: sha256 `150ddf3b…`, 4070 B. Matches `current_canonical_wrapper`.
- The declaration file itself is **git-ignored** (`.gitignore:53` `/validation/*/`) and **untracked**.
- Existing suite: 42 tests OK, 2 skipped (symlink privilege unavailable).
- Real CLI run: exit 0, status `ready_blocked_by_formal_dependency`, 0 violations, 3 `host_bounded` entries.

## Findings (P0/P1/P2)

### P1-1 — The declaration is a tamperable self-authorization channel

The identity declaration is the *sole* authorization for accepting a superseded
wrapper digest, yet it is git-ignored, untracked, not tracked-checked by the
auditor, and not hash-pinned in the closure manifest — every other evidence
class is pinned. `current_canonical_wrapper.sha256` is format-checked but never
cross-hashed against the live file, so a stale or tampered declaration is
undetectable (repro **A3**: mutated digest + rewritten purpose, audit still
ready). Repro **A2**: declaration left untracked, its identity still honored.
Any actor with working-tree write (archive extraction, dropped file) can
declare new identities without touching a single pinned artifact.

Fix: exempt the declaration from the ignore rule and commit it; require
tracked-at-HEAD in `_load_historical_identities`; pin its sha256 in the closure
manifest; cross-hash `current_canonical_wrapper` against
`Simulator/wksim_core/model.cpp`.

### P1-2 — "Tracked" check is index-level, bypassable via `git add` without commit

`_is_tracked` runs `git ls-files --error-unmatch`, satisfied by any
staged-but-never-committed index entry (repro **A1**: fixture repo with zero
commits passes the "tracked frozen original" gate). The declaration's
durability claim (`archived_repo_path_tracked: true`) is not what the check
proves. Today's real instance *is* sound (verified at HEAD, commit `4e161e2`),
but the check does not enforce it.

Fix: `git cat-file -e HEAD:<path>` plus blob-digest equality
(`git rev-parse HEAD:<path>`), or `git diff --quiet HEAD -- <path>` after
`ls-files`.

### P1-3 — RflySim receipt classification: trailing-payload bypass

`_wsl_precheck_found` decodes only the leading JSON value; everything after is
ignored. A tracked rflysim-named file with a valid empty receipt followed by
arbitrary text — base64-encoded DLL, vendor config, scripts — is classified as
a clean "nothing found" receipt (repro **A4**). Only NUL bytes and a
non-receipt leading document are caught. Type trickery on `found` itself is
handled correctly (control **N2**: `""`, `0`, `{}`, `[null]`, non-empty list
all rejected).

Fix: after `raw_decode`, accept only whitespace or lines matching the
documented `wsl: ` warning form; anything else is an offender. Prefer pure
single-document JSON receipts.

### P2-1 — Host-bounded skips still yield exit 0 / "ready"

On Windows the `cold_library`, cold-probe and build-output byte re-hashes are
skipped as `host_bounded`, yet status is `ready_blocked_by_formal_dependency`
and exit is 0 (evidence **E1**). On Linux the same `/root` products are missing
and the audit fails closed (mechanism control **N3**), so *no* host can
currently produce a fully verified pass — the only passing configuration is the
skipping one. No should-fail path is swallowed (POSIX paths are genuinely
unaddressable on Windows and are never mapped onto the current drive), but the
acceptance signal cannot distinguish "all checks passed" from "three
declared-evidence checks skipped".

Fix: require an empty `host_bounded` list for main acceptance, or emit a
distinct status/exit code when it is non-empty.

### P2-2 — Declaration read lacks the symlink/reparse guard

`_load_historical_identities` reads the declaration without `_secure_file`,
unlike every other evidence file. Low impact (content strictly JSON-validated;
archived path re-secured), but the asymmetry is unjustified.

### P2-3 — Vendor scan coverage note

`_vendor_offenders` only inspects tracked names containing `rflysim` or ending
`.dll`/`.zip`; vendor binaries with other extensions and no `rflysim` substring
are not content-classified. Appears intentional; recorded.

## Defenses confirmed (negative controls)

- **N1**: malformed / duplicate-key declaration → violation → exit 2 (fail-closed).
- **N2**: `found` type trickery rejected.
- **N3**: addressable-but-missing provenance path → violation, never host-bounded.
- Missing declaration → empty identity map → wrapper bound to current source (fail-closed by default).
- Undeclared wrapper digest fails; archived copy missing/drifted/untracked all fail (fixture tests).
- Traversal/backslash/empty segments rejected in `archived_repo_path`; strict JSON loader rejects duplicate keys and non-finite numbers.
- CLI exit 0 iff `ready_blocked_by_formal_dependency`, else 2.

## Decision

**Not approved for main acceptance.** No P0 found — the frozen-original binding
(digest, size, HEAD tracking) is verified sound in the real repository — but
P1-1, P1-2 and P1-3 must be fixed or explicitly adjudicated first. P1-1/P1-2
share one root cause (the authorization layer is weaker than the evidence layer
it governs) and have small, mechanical fixes.
