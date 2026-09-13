# Independent read-only review: perf_capture.py ctypes adapter (2026-09-13)

Reviewer wrote only this file and `review.json`. No source, test, receipt or capture file was
edited, loaded, built or re-run natively. Class: new-development acceptance review.

**Revision 2 (2026-09-13, read-only continuation).** Main added the isolated collision case
(`run_collision2.py` / `collision2-receipt.json`). The single evidence blocker in Revision 1 is now
resolved; see [Revision 2](#revision-2-isolated-eexist-evidence). The adapter and test SHAs are
unchanged (`c196616f…` / `f4d95ae4…`). The earlier `collision-receipt.json` and `run_collision.py`
are kept as the failed main-script artifact and are not superseded evidence.

- cwd `C:/Users/PC/Documents/odid编译/wksim`; branch `main`; HEAD `0857cd95ed54bb976ef541bbb8462bde29c456e5`;
  `git merge-base --is-ancestor f333316e… HEAD` exit 0.
- Re-read: `AGENTS.md`, `docs/architecture-implementation-20260912.md`,
  `docs/coordination/architecture-continuation-20260913.md`, `docs/coordination/module-delivery-policy-20260912.md`,
  `docs/coordination/perf-stream-contract-20260913.md`, `docs/2026-09-13-perf-kernel-loss-counter.md`,
  and the accepted header/C in `validation/coordination/ds-perf-stream-recorder-20260913-01`
  (`ef1eabf2…`/`aa807f3b…`, both re-hashed and matching).

## Stable artifacts reviewed (re-hashed here)

| Artifact | SHA256 |
| --- | --- |
| `Simulator/wksim_runtime/perf_capture.py` | `c196616fe8324eed2d8b294ef52aaec1f982eb5330abbeb7ee17094399f32e0f` |
| `validation/test_perf_capture.py` | `f4d95ae49478729e2f4c3a508f9ef452d3f6b5acffd0c8a3301bc72155d4f3c3` |
| main `build.py` / `run.py` | `54f118ae11abcabc…` / `df9db9a7bb8c6ac6…` |
| `libwksim_perf_stream.so` (WSL, main-owned) | `37d9651282bce0da059828056796683b94e780461f7918e60c3e1e77e2130020` |
| consumer used by `run.py` | `dee9a3b5c3cafb42e69836758ccaebd4dbd78e8fa569d203c7ca1d36a03179bc` |

The library file still exists on the tested WSL and its live hash equals the build receipt's
pin, so the admission evidence was not produced against a replaced artifact.

## Verification performed (read-only, pure)

- `python -B -m unittest validation.test_perf_capture -v` on this Windows checkout: **9/9 pass**
  (matches the recorded Linux run). The suite patches `ctypes.CDLL`, so no `.so` is loaded.
- Re-parsed the captured raw files myself: `normal` 384 B = 12 × 32-byte type-14 SWITCH; `wrong-owner`
  128 B = 4 × 32-byte type-14 SWITCH; both trailing-byte clean, matching `switch_records`/`complete_pairs`
  (6 and 2) in the metadata. Re-hashed metadata/raw and matched `inputs.*_sha256` inside `decoded.json`
  and the receipt blobs.
- Both `decoded.json` show `stream_completeness_proven: true` from `--require-kernel-counter`
  (`kernel_lost_count: 0`), and `run-receipt.commands` records that exact flag for both invocations.

## Five acceptance concerns: findings

1. **ctypes binding** — correct. `POINTER(c_void_p)` accepts a real `byref(c_void_p)` in-place write
   (proved by the tests, which pass a genuine `ctypes.byref` through the real ctypes layer and still see
   `handle_value == 1234`); `stop` adds the exact `[pointer, c_char_p, c_char_p]`; `restype` is `c_int`
   for both and `c_char_p` for `last_error`. The test compares the exact types, not just names.
2. **PID + native TID ownership** — correct and pre-native. `_owner()` is `os.getpid()` +
   `threading.get_native_id()` (Linux: real kernel TID), captured in `__init__` and re-checked in
   `start()`/`stop()` **before** any native call; the test proves both a foreign PID and a foreign TID
   leave `wksim_perf_start`/`wksim_perf_stop` uncalled.
3. **Failed start retaining a handle** — correct. A non-NULL retained pointer is kept, the raise text
   carries `retained=True`, the owner may call `stop()` once for cleanup, and `stop_completed` then stays
   `False` (cleanup is not a capture success). A consumed failed start cannot be restarted (`_attempted`).
4. **Stop nonzero with handle already cleared** — correct. The return code is tested before the handle
   state, so `-1` with a NULL handle still raises (`retained=False`), and `0` with a live handle is also
   rejected; the code and `last_error` text are never discarded.
5. **No destructor; completeness is not self-certified** — confirmed. The class defines no `__del__`,
   context manager, `atexit` or callback; `owns_handle` is the explicit state for the launcher's `finally`
   path, and `stop_completed` is a local flag only. Completeness stays with the independent consumer
   requiring `--require-kernel-counter`, which is exactly how the two passing cases were judged.

## Real blocker — **resolved in Revision 2**

- **The `existing-output` case does not attribute its failure to `EEXIST`.** The recorded primary error is
  `stop: no complete switch in/out pair was captured: no_switch_pair`, not `output_exists`. In that run the
  owner thread produced no complete pair inside the window, and the C implementation decides semantic
  failures *before* attempting the exclusive creates; the `O_EXCL` `EEXIST` error can therefore only be a
  later entry. No metadata file exists for that case (C writes none on failure), so its
  `collector_errors` list cannot be inspected from the delivered artifacts. The preserved 17-byte
  `capture/existing-output/switch.raw` (`b'preserve original'`) and the `-1`/handle-released result do prove
  non-overwrite and cleanup, but not that a live capture is rejected by `EEXIST` alone. Main's planned
  isolated EEXIST counter-example (sufficient switch pairs, pre-existing raw, then stop) is the right fix;
  until then the EEXIST path is unisolated. **This limitation of the original `run.py` case stays recorded;
  it is now covered by the separate collision case in Revision 2.**

## Verification limits and smaller gaps (not blockers)

- **I did not and cannot re-run the native capture** here: the `.so` loads only on the tested WSL kernel and
  under main's precheck discipline. `decoded.json`, metadata and receipt hashes are consistent, but the
  capture itself is main-owned evidence. The build receipt's `boot_id` (`fbdc0c24…`) differs from the run
  receipt's (`50bfcbdf…`) because the machine rebooted between build and run; that is not a boot mismatch
  *during* a run. Each run is same-boot with its own prechecks, and each re-hashed the library SHA against
  the build pin (`37d96512…`, re-verified live here) on the same kernel `6.6.87.2-microsoft-standard-WSL2`.
- The main-thread owner (`owner_pid == owner_tid == 765`) is the only owner sample in these artifacts.
- `run.py` per-case owner assertion is weak: it checks `meta['owner_pid'] == meta['owner_tid'] == cases[0]['owner_pid']`,
  i.e. only `cases[0]` and only because pid == tid == 765 (main thread). The `wrong-owner` case's own
  metadata is not compared to its own row, and a capture on a non-main thread (pid != tid) would break the
  assertion. Consider per-case `(owner_pid, owner_tid)` comparison.
- The wrong-owner evidence is adapter-level only: the Python guard rejects the foreign thread before C, so
  the C-side `EPERM` wrong-owner path is not exercised natively. That matches "reject before C", but it is
  not native coverage of the C refusal.
- `owner_pid`/`owner_tid` are this adapter's own values and are never compared to the metadata C writes,
  and no test drives a non-main-thread owner, so the native-TID semantics of the owner recording are not
  independently exercised.

## Revision 2: isolated EEXIST evidence

Reviewed read-only: `run_collision2.py` (`40156a23a6fa8021…`) and `collision2-receipt.json`
(`1d472fc8ec78a1b4…`), plus the run directory it names.

- The receipt's `adapter_sha256` equals the stable adapter `c196616f…`, and the run-dir `perf_capture.py`
  re-hashes to the same value; `library_sha256` equals the build pin `37d96512…`, re-verified live now.
- Recorded primary error is exactly `stop: create raw: output_exists (errno 17: File exists)` with
  `stop=-1`, `retained=False`, `stop_completed=False`; the driver asserts that text (not merely a nonzero
  return), so a different error path could not have satisfied it.
- The 17-byte pre-existing raw is byte-identical afterwards (`96fe617d939b0f7b…`, `b'preserve original'`)
  and no metadata file was created — correct, because C source line 1156 only opens meta after a successful
  raw open, so a missing meta here is expected behaviour, not a defect.
- `fds 4 → 4`, `threads 1 → 1`, `pgid_empty: true`, `boot_id == boot_after`
  (`2c6d203d-6f09-415d-82d6-58a6d33233ef`), which is also this host's current boot; both prechecks report
  `found=[]` on the same boot. The framework driver's own assertions are a reproduction of the delivered
  `driver.py` (byte-identical, `6970cc832a03e075…`).
- The pair check precedes the exclusive creates, so reaching `create raw` implies a complete switch pair
  existed. The case makes no claim about the kernel counter value (`counter_inspected: false`); that is
  correct — no metadata was produced, and completeness for a capture remains the independent
  `--require-kernel-counter` consumer's claim.
- `collision-receipt.json` (`020b350475e48627…`, exit 1) is the retained failure of the earlier main script,
  which wrongly expected a metadata file; it is preserved as a historical artifact and shows no adapter
  defect.

This resolves Revision 1's only evidence blocker. Remaining limits are the coverage items below: C-side
`EPERM` is still pre-empted by the Python guard, the owner sample is main-thread only, and completeness is
never asserted by this adapter.

## Verdict

Adapter, test suite and admission receipts are internally consistent and cover the five required behaviors;
I found no correctness defect in the adapter at the stable SHA. The single Revision 1 evidence blocker
(isolated `EEXIST`) is resolved by `collision2-receipt.json`; only the non-blocking coverage limits above
remain. Nothing beyond this line was written; no source was modified.
