# Ingest manifest · #59 G6/B5 solve-form decision stability repair

- Manifested HEAD: `0b10f786e808eebe7698e9a277766bf2f68a4d35`
- Scope: context-only, non-acceptance
- Independent verdict: **GO**
- Exact batch: 10 paths

This manifest admits the three stable-evidence repair candidates, three independent-review artifacts, and four manifest artifacts. It records an offline decision/stability packet only. It does not approve B1 budgets, select a solve form, grant physical or G6 acceptance, or close #59, #84, or Full.

## Exact-path and history checks

`exact-paths.txt` is SHA-256 `56e211b23669f861eb34218f09851667f5a0c618b0a571b2c2a350ac8bf7e597`, 809 bytes, 10 unique bytewise-sorted LF-only repository-relative paths.

Anchor `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` is an ancestor of the manifested HEAD. Four source pins are unchanged from the anchor. Three derived pins were absent at the anchor, introduced once by `0785f0e`, and have intro blob == HEAD blob == worktree bytes == recorded pin with no later effective change. The packet's historical observed HEAD is diagnostic only (`head_pinned=false`) and is not required to equal the current HEAD.

The independent adversarial review verified the stronger content-anchor method, a linear 82-commit window, rename/delete/re-add behavior, merge simplification, fail-closed ancestry and overlap cases, and confinement of the packet change to `observed_at`. Its verdict is GO.

## Admission proof

The repo-external read-tree-HEAD temporary index affects exactly the 10 manifest paths:

- 7 path additions for the git-ignored review/manifest artifacts;
- 3 in-place content updates for the tracked packet, test, and plan candidates;
- 0 removals;
- all entries at stage 0/mode 100644;
- every staged blob equal to the corresponding worktree bytes.

This is the honest form of exact-10 confinement. A literal “10 additions” would be false because three candidates already exist in HEAD and are modified in the worktree.

The real index fingerprint and raw SHA-256 remained unchanged (`cf249890d18567a9f62173ff1e8ac717362fe531ecea02a545a72ee185319a32`), as did HEAD. Scoped `git diff --check` is clean. The only full-tree warnings remain pre-existing whitespace in protected `docs/Prometheus.gitmodules.reference`.

## Test evidence

The independent review ran:

- normal: 36 tests, OK, 2 exact-index tests skipped by design;
- repo-external exact-three: 36 tests, OK, no skips, exact candidate set and staged blobs verified.

The manifest writer did not rerun the suite; it carried those results with attribution and independently performed the exact-10 admission proof.

Claude Code wrote `exact-paths.txt` and the complete machine-readable `review.json`, then its upstream provider returned HTTP 403 before this markdown and `SHA256SUMS` were written. The main session resumed only those terminal outputs and rechecked the manifest bytes and index classification.

No model, MATLAB, ROS, flight-controller, Unreal, build, native, #83, or GitHub mutation was performed.
