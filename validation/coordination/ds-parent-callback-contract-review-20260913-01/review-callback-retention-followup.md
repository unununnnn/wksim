# Follow-up: F2 withdrawal, health-callback conclusion corrected, v1 defect proved, v2 fix verified (2026-09-13)

Owner: `validation/coordination/ds-parent-callback-contract-review-20260913-01` (only
directory written). Pure offline Python; the reviewed modules and B's directory were read
only. No native, model, ROS, build or MATLAB. Supersedes the earlier **no-blocker**
verdict in `review-parent-callback-contract.md`, which is withdrawn.

## 0. Verdict

**No-blocker withdrawn, and a second conclusion of mine corrected.**

1. **F2 was false.** The parent's loop-health branch is reachable; the real artifact
   `uy9ov56b/reordered-archive/rate.jsonl` shows `loop_health_calls = 1` on **21 289 of
   22 524** groups (`0` on 1 235). My old harness never reached it.
2. **My "the callback cannot cross the release edge" conclusion was also wrong.** It
   rested on reconstructing the callback's window from the record's **aggregate** fields
   (`initial_health_end_ns`, `sleep_elapsed_ns`, `loop_health_ns`) — but the real
   callback's duration is unknown to those aggregates, and a long callback can start with
   more than 1 ms remaining and still finish after the release edge. With the callback's
   duration in the fixture, the crossing reproduces and B's reported crossing case holds.
3. **The v1 mixed/reversed-pair defect is real and is fixed in v2.**

## 1. Crossing fixture: the loop-health callback itself crosses the release edge

`test_callback_retention_followup.py` part 1b. Real parent class; the clock advances only
by the predetermined script — 100 ns per read, plus exactly **3 ms added by that one
health invocation itself** (`long_health_on=(2, 1)`), not by adjusting the read step or
the inter-group gap alone.

Geometry: the second group is entered 3.4 ms before its release edge, so the initial
health call is instantaneous and the parent takes the sleep branch; one 2 ms-capped sleep
returns the clock to ~1.4 ms before the edge; the next loop iteration reaches the health
point, and **that first loop-health callback takes 3 ms**.

Recorded from the run (not reconstructed):

| Quantity | Value |
| --- | --- |
| second-group health invocations | 2 (1 initial + 1 loop) |
| retained `loop_health_calls` | 1 |
| target call | first **loop-health** call (`loop_index = 1`), long advance applied = True |
| callback before → after | 1 005 401 600 → 1 008 401 600 ns |
| callback duration | **3 000 000 ns** |
| release instant R | 1 008 000 500 ns |
| remaining when called | **2 598 900 ns** (> 1 ms: **True**) |
| overrun past R | **401 100 ns** |
| **crosses the release edge** | **True** |

This is the case B's report describes: more than 1 ms remained when the callback was
invoked, and the callback still ended 0.4 ms after the release edge.

## 2. F2 corrected: reachability

Part 1, clock at 100 ns per read with the sleep advancing only the requested duration,
three groups, second group entered 1 ms after the first: **all three revisions reach the
loop-health branch** (2 of 3 groups, up to 3 loop-health calls inside one group). Real
artifact counts: `{1: 21289, 0: 1235}` over 22 524 timing samples. The mechanism is the
parent's `min((remaining-1ms)/1e9, .002)` sleep cap over an 8 ms period.

## 3. Limit: the uy9 aggregates cannot decide the window

The retained uy9 record keeps per-callback **totals**, not per-callback instants. Its
`initial_health_end_ns + sleep_elapsed_ns … + loop_health_ns` reconstruction places
`reconstruction` windows 780 551 … 1 755 206 ns before `earliest_start_ns`, but that
window is a **modelling artefact**, not the observed callback interval: `loop_health_ns`
is the summed duration of *all* loop-health calls, and the sleep/user-code interleaving is
unknown. Therefore:

* the uy9 record **cannot** establish whether any real loop-health callback crossed the
  release edge, in either direction;
* my earlier statement that crossing is structurally impossible is **withdrawn**;
* the fixture above is the evidence for the crossing case, and it is a fixture, not a
  measurement of the retained run.

The retained record *can* establish reachability (the call count is a direct observation),
which is what part 1 uses.

## 4. v1 defect proved: successful sleep then failed sleep in one attempt

Part 2/3: two groups with the second entered 1 ms after the first, 100 ns per read, and
the **second sleep raising a scripted sentinel without advancing the clock**.

| Revision | `sleep_requests` | retained | verdict |
| --- | --- | --- | --- |
| **v1** (rejected) | `[2000000, 2000000]` | `before=1003001800`, `after=1003001300` | **reversed pair**, triple inconsistent |
| **v2** (fix) | `[2000000, 2000000]` | `before=1001001200`, `after=1003001300` | consistent, monotone, one completed call |

Cause: v1 writes `last_sleep_requested_ns` and `last_sleep_before_ns` **before**
`self._raw_sleep(seconds)`; the later failed sleep therefore leaves its own
before/request beside a stale after from the completed call. v2 moves **all three
assignments** after the successful after-read (`joint_rate_probe-candidate-v2.py.txt`
lines 144–149), which is the right minimal fix.

## 5. Exception object identity

Both revisions propagate the **same object** the scripted sleep raised
(`exception_is_sentinel_object = True`), so the added retention fields change neither
exception type/message nor identity. The probe's `finally` still emits its sample.

## 6. Pins and source SHA, before and after

| Artifact | SHA-256 |
| --- | --- |
| old parent `Simulator/wksim_runtime/joint_rate_probe.py` | `a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653` |
| v1 (rejected, kept under `rejected-v1/`) | `e1dd28558e36f40ea9ec87cddcbe517339f6196198dec0a28b164fecafe75a70` |
| v2 (fix) | `7855409d1f28e955dc9fcafc2d90f94e13ef5ab35eb1a0d239b61a4c919a4be1` |
| `Simulator/wksim_runtime/joint_rate.py` (unchanged) | `0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4` |

v2 vs the old parent: 27 inserted lines, 1 replaced line that is a **comment**. No
executable parent statement altered.

## 7. v2 review conclusion

**v2 is accepted for the retention contract, with no blocking finding.** Specifically:

* the atomic three-assignment placement removes the mixed/reversed-pair defect that v1
  exhibits under a successful-then-failed sleep;
* the five added keys are the only difference in emitted records, the old side contains
  none of them, and clock-read/sleep-request/callback/exception traces are identical
  between revisions in the earlier multi-group comparison;
* the loop-health retention semantics are consistent: values appear only for a loop-health
  call that completed, and the crossing case is now demonstrated rather than assumed;
* exception object identity is preserved.

Two non-blocking notes remain as before: the initial-health call is not itself retained by
`last_health_*` (it keeps its own aggregate field), and the retained-callback window cannot
be recovered from the uy9 aggregates, so any future assertion about the real distribution
of callback windows needs per-callback instants in the record, not new analysis of totals.

## 8. Reproduce

```
cd C:/Users/PC/Documents/odid编译/wksim
python -B validation/coordination/ds-parent-callback-contract-review-20260913-01/test_callback_retention_followup.py
```

Evidence: `evidence/callback-retention-followup.json`. The earlier
`evidence/parent-callback-contract-review.json` remains as the withdrawn no-blocker record
and must not be cited as the current verdict.
