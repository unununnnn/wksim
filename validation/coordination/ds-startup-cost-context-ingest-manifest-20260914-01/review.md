# ds-startup-cost context ingest manifest (2026-09-14)

Manifested at authoritative HEAD `011818876c1b94875fd67cedaaa73abfac866633`
("Bind OMP delivery diagnostic context offline"). This manifest registers the
DS startup-cost historical-context batch for commit as **context only** and is
itself **non-acceptance**: it confers no authority, approval, acceptance,
closure, review status, or rerun permission on #83 (or #9/#26/#29/#62/#102 or
any ticket). Current-status judgments belong to the current authority
(main agent / main session / human ruling) made against present-day artifacts.

## 1. Commit set — exactly 11 unique sorted paths

- 4 candidates: `docs/coordination/ds-startup-cost-evidence-20260912.json`
  (18778 B), `docs/coordination/ds-startup-cost-evidence-20260912.md` (17495 B),
  `docs/coordination/ds-startup-cost-evidence-ingest-note-20260914.md`
  (12417 B), `validation/test_ds_startup_cost_evidence_context.py` (26826 B).
- 3 independent-review inputs:
  `validation/coordination/codebuddy-ds-startup-cost-independent-review-20260914-01/`
  — review.md (9473 B), review.json (8050 B), SHA256SUMS (154 B).
- 4 manifest outputs: this directory's SHA256SUMS, exact-paths.txt, review.json,
  review.md.

`exact-paths.txt` is byte-exactly this 11-path sorted list (C locale, 902 bytes
expected at write time); any divergence invalidates the registration.

## 2. Head relation

The independent review was performed at `reviewed_head`
`011818876c1b94875fd67cedaaa73abfac866633`, which equals the manifested HEAD.
HEAD equality is recorded as incidental, not required: the manifest requires
only that the binding lineage
(`f333316e6efa6b299b4288a9d91fb2bccedfb9d6`, `76f77470…`, `1c5656ed…`,
`e2ecd62e…`) is ancestral to the running HEAD (`git merge-base --is-ancestor`,
all exit 0, re-verified at this HEAD by the candidate suite and by this owner).
The suite deliberately never asserts HEAD equality, so it stays valid at
descendant commits.

## 3. Independent review — terminal facts carried forward

Review record strict-parsed at this HEAD (`wksim.independent-review.v1`):
**verdict PASS, P1=0, P2=0, P3=3**, hashes/sizes independently recomputed and
matching the candidate set; review SHA256SUMS self-verify from their own
directory (review.md OK, review.json OK, exit 0). The three P3 findings are
carried forward **verbatim in force, without promotion or demotion**:

- **P3-A** — runner pin commit `7cb7e840…` is reachable from no origin ref;
  fresh clones cannot resolve the pin (documented test skip path; out-of-band
  object transfer required). Caveat must travel with every citation of the
  runner pin.
- **P3-B** — the older tracked `docs/coordination/ds-7bdfxkb-diagnostic-analysis.json`
  carries a malformed 63-character hash for the 7bdfxkb_ rate.jsonl; the
  candidate's 64-character pin matches the analyzer-produced triple output and
  is correct. Left for the current authority; not a defect of this batch.
- **P3-C** — the ingest note's four registered P3 corrections (analyzer
  generation `75353c06`/`1c43ac9c` vs `c3ba9de8`; `joint.py:189-193`
  attribution; the "24147 组" typo; the nearest-1000-ns rounding qualifier) are
  verified accurate and must travel with every future citation of the bound
  snapshot.

No P3 here constitutes a rejection; none of the above grants approval.

## 4. Test facts (re-run by this manifest owner at this HEAD)

- Normal: `python -B -m unittest validation.test_ds_startup_cost_evidence_context -v`
  → 19 tests, OK, exit 0; real index untouched.
- Staged lifecycle: temporary `GIT_INDEX_FILE` copied from the real index with
  exactly the 11 proposed paths force-added (`git diff --cached --name-only`
  set-equal to exact-paths.txt); suite re-run under that index → 19 tests, OK,
  exit 0. Temporary index and its directory deleted afterwards; real index
  SHA256 byte-for-byte unchanged across both runs; real staged-diff count 0.
- `git diff --check` over all 11 paths: clean (exit 0).
- The suite is staging-safe by construction: its tracked-status probes cover
  only tracked anchors unaffected by staging these 11 paths; the two
  runner-dependent tests skip with a clear reason if the historical blob is
  absent from a clone.

## 5. Boundaries and nonclaims

- Context-only ingestion; historical context only; non-acceptance.
- No candidate or existing file was edited; writes are confined to this
  manifest directory (4 files).
- No commit, no push, no GitHub query or mutation, no network, no
  native/build/MATLAB/ROS/DDS/SITL/FC/UE/model/flight execution, no #83 rerun.
- Protected files (`docs/Prometheus.gitmodules.reference`,
  `validation/coordination/short-cycle-dispatches.json`) untouched.
- The unexcluded hypotheses (log flush/I/O blocking, thread contention,
  decode/encode CPU variation, host-periodic events, hot-path `physics_health`
  cost, first-time cost after the anchor) remain unexcluded on the current
  tree; M1/M2/M3 remain open suggestions; the C2 disposition remains
  unresolved. This manifest does not adjudicate any of them.
- This manifest is a static artifact; its own hashes/sizes are recorded in
  SHA256SUMS (covering exact-paths.txt, review.md, review.json) for
  tamper-evidence.
