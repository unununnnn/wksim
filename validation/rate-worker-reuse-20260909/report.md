# Worker response serialization reuse

Parent explicitly assigned this bounded pure fix after reviewing the diagnosis and patch in `validation/rate-blocker-review-20260909/`. Only `Simulator/wksim_core/worker.py:model_worker`, new `validation/test_worker_serialization_reuse.py`, and this evidence directory changed. No Hex/PID, transport/callsite, timing budget, diagnostic default, issue, commit or push change was made.

Each accepted worker step now serializes its120-value response once, reusing that JSON text for both the full trace record and RPC stdout. The trace suffix still contains the exact commands, original input line and parsed request. Field order, JSON numeric representation, newlines, log-before-response ordering, response validation/size guard, snapshots and single-lifetime guard remain intact. No evidence is dropped or batched.

## Verification

- Original source: new7-test suite produced one deliberate red regression, full-state serialization count3 instead of2 for initial snapshot + step + snapshot. All other checks passed. `red-tests.log` preserves this.
- Updated source: same7 tests all pass (`green-tests.log`). Exact stdout/trace bytes are independently constructed from the protocol; test state includes negative zero and very small/large finite numbers.
- Error paths: trace write failure, extras encoding failure and nonfinite encoding publish no response; invalid-length state retains the trace before validation fails; output-size rejection still happens after trace and before stdout; a second worker lifetime remains rejected.
- WSL combined run: **13/13 passed, no skips** (`wsl-protocol-transport-tests.log`), comprising the7 new tests, existing2 protocol tests and4 transport-only child tests. RealModelTests were not selected and no native library was supplied. Fake transport children were reclaimed by the existing harness; its temporary evidence roots/PIDs are in the retained log.
- `git diff --check` passed. Exact source/test/log hashes are in `hashes.json`.

Command:

```text
wsl.exe -d Ubuntu-22.04 --cd /mnt/c/Users/PC/Documents/odid编译/wksim --exec python3 -B -m unittest validation.test_worker_serialization_reuse validation.test_joint_model_worker.ProtocolTests validation.test_joint_model_worker.TransportTests -v
```

No FC, UE, ROS or generated native model was started. The earlier isolated256-record byte-equivalence/microbenchmark evidence is unchanged and is not rerun or promoted into a1× claim. #20/#62 remain open; scheduling tails,60s windows and three-epoch acceptance still need separate evidence. The frozen #61 candidate contains the old worker source hash, so it must be explicitly replaced/reviewed before any later performance run, not bypassed.
