# Independent review: MIXED PerfStreamCapture wiring in tools/run_joint_flight.py

- Date: 2026-09-13
- Category: new-development / independent code review (read-only)
- Baseline: `main` HEAD `100ef1aafcc19c006d93eeb16b0c41e2352cdee6` ("Wire perf capture into actual MIXED runner")
- Ancestor gate: `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0 (required ancestor present)
- Reviewed diff: commit `100ef1a` only, `tools/run_joint_flight.py` (+120/-1), new `validation/test_run_joint_perf_capture.py` (+207), coordination artifacts. `Simulator/` untouched by the commit (verified via `git diff 33c2b06..HEAD --stat -- Simulator/` → empty).
- Scope limits honored: pure-Python/read-only verification only; no native library, no build, no ROS, no flight controller, no model, no UE, no MATLAB. No existing file modified; no shared ledger touched.

## Verdict

No P0 blocker, no P1 finding. Lifecycle wiring matches the required ordering and fail-closed contract. Four P2 latent-robustness notes below; none blocks the diagnostic wiring.

## Checklist verification (evidence: `tools/run_joint_flight.py` @ 100ef1a)

| Requirement | Result | Evidence |
|---|---|---|
| CLI pair only MIXED | PASS | `main()` rejects incomplete pair and non-MIXED profile via `parser.error` (lines 1246-1250); `perf_capture_request` re-raises `ValueError` at run level (73-82); task subparser has no perf arguments |
| Construction after rate creation, before child processes | PASS | `rate = make_joint_rate(...)` line 861; `PerfStreamCapture(...)` lines 863-866; first child `launch`/`Popen` at lines 899-935 — strictly later |
| start after `physics.connect()`, before main loop | PASS | `physics.connect()` line 960; `start_perf_capture` lines 961-962; main loop `while clock.tick < MAX_TICKS` line 988 |
| stop/fail-closed in outer `finally`, before `cleanup_children` | PASS | `finally:` line 1099; `finalize_perf_capture` lines 1100-1101; `cleanup_children` line 1102 |
| Same owner thread | PASS | construct/start/stop all on the runner main thread; `PerfStreamCapture._check_owner` enforces original pid + native tid on every operation (`Simulator/wksim_runtime/perf_capture.py` 78-80) |
| Window from a complete `JointRate` segment | PASS | window = `last_summary.anchor.wall_ns` → `rate.last_end`; `last_summary` set only by `close_segment('completed')` (line 1081); incomplete/missing/typed-wrong window rejected fail-closed (runner 106-114) |
| raw/meta/window/library/source identity sealed | PASS | outputs carry file/bytes/sha256 for raw, metadata, windows (138-142); library re-digested and compared post-run (130-131); consumer source path + sha256 pinned in marker (471-477); `PERF_CAPTURE_SOURCES` added to pinned source list (509-510); boot_id re-read from host and compared against meta (118-122) |
| No exception escapes cleanup | PASS (with P2-1 caveat) | `finalize_perf_capture` body wrapped in `except BaseException` (147-152); on any failure: marker `status='failed'`, `result['status']='failed'`, existing error preserved via `setdefault`; `cleanup_children` still runs |
| 1ms / 4-tick / no-catch-up / 100ms / complete window unchanged | PASS | commit touches no timing code; the single deletion is the `perf_capture = None` initializer addition. `JointRate` invariants intact: final 1ms monotonic-only release edge (`joint_rate.py` 122-124), strict 4-tick groups (`end_group` 132-134), no-catch-up pacing (`begin_group` earliest = `max(ideal, previous_start+period_ns)` 92-93), `LATE_LIMIT_NS = 100_000_000` (6), complete-window enforcement via `check_boundary`/`reanchor` 4-tick boundary checks |
| Formal gate rejects `perf_switch_capture` | PASS | `Simulator/wksim_runtime/joint_profile.py` 274-276 raises `ValueError('Formal mixed/PV evidence cannot include perf_switch_capture')` for any marker value; marker itself declares `classification='diagnostic_only'`, `formal_evidence=False`, `strict_consumer_passed=False` |

## Pure-test evidence (see test-output.txt)

- `validation/test_run_joint_perf_capture.py`: 9 passed, 6 subtests passed
- `validation/test_run_joint_scheduler_windows.py`: 37 passed, 21 subtests passed
- `validation/test_joint_profile.py -k perf`: 1 passed, 4 subtests passed (gate rejection)
- `validation/test_mixed_profile_admission.py -k perf`: 1 passed, 5 subtests passed (gate rejection, raw reader not called)

## Findings

### P0 — none

### P1 — none

### P2-1: marker lookup sits outside the fail-closed `try`
`finalize_perf_capture` line 98 `marker = result['perf_switch_capture']` executes before the `try` at line 99. If a future edit moved marker creation (currently line 471, before the outer `try` at 526) after the `try`, a missing key would raise `KeyError` that escapes the `finally` and skips `cleanup_children`, leaking child processes. Currently unreachable: marker is set unconditionally whenever `perf_request is not None`, before the outer `try`. Reproduce (latent shape, not current behavior): delete line 471-477 block, run any MIXED perf request → `KeyError` propagates from the `finally`. Recommendation (non-blocking): move the lookup inside the `try` or use `result.get('perf_switch_capture')` with a synthesized marker.

### P2-2: anchor/end pairing is flow-implied, not structurally enforced
The window pairs `last_summary['anchor']['wall_ns']` with `rate.last_end`. `JointRate.reanchor` resets `last_end` and `close_segment` snapshots the current anchor, so in the present runner flow (single segment: `reanchor` only when `anchor is None` at line 969, single `close_segment('completed')` at 1081) the pair always belongs to one segment. A future mid-run reanchor+close cycle could pair segment N's anchor with segment N+1's `last_end` and still pass the type/ordering/inner-span checks. Non-blocking; a cross-check (e.g., window duration vs `last_summary` measured duration) would harden it.

### P2-3: native handle leak on stop failure is by design
If `capture.stop()` raises, the native handle stays live until process exit (`owns_handle_after=True` recorded). `perf_capture.py` documents "No destructor stops it" deliberately. Acceptable for a diagnostic path; noted for completeness.

### P2-4: `except BaseException` also traps `KeyboardInterrupt` raised inside finalize
An interrupt arriving during `capture.stop()` is converted to a failed marker and cleanup continues. Any already-propagating exception is unaffected (finally semantics). Deliberate fail-closed trade-off; child cleanup is prioritized over immediate interrupt propagation.

## Residual native acceptance conditions (not exercisable from this Windows review host)

1. Real run on WSL2 kernel `6.6.87.2-microsoft-standard-WSL2` with the actual `wksim_perf_stream` `.so`: owner-thread start/stop, `enable_after_ns`/`disable_before_ns` inner span covering the complete MIXED rate segment, `captured_bytes` matching raw size.
2. Strict consumer `perf_stream_consumer.py` decoding to `perf-decoded.json` with `require_kernel_counter=True`; `strict_consumer_passed` remains `False` until that native acceptance runs.
3. C-side stop must write meta `boot_id` identical to `host_boot_id()` on the flight host, and owner pid/tid identical to the constructing thread.
4. Library immutability across the run is re-verified by digest at finalize; native acceptance should confirm the digest mismatch path fails closed with the real `.so`.

## Stable SHA

`100ef1aafcc19c006d93eeb16b0c41e2352cdee6` (review baseline; working tree carries unrelated changes from parallel sessions — none touch the reviewed files).
