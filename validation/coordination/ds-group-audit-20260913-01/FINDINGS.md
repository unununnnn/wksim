# Independent group work-timing audit — joint-public-flight-rfw9nmbb

Diagnostic-only audit of one archived flight. This document reports what the
archived raw rows prove, what they merely declare, and what they cannot show.
It makes **no acceptance claim** and **no causal attribution**.

- Archive (read-only, WSL Ubuntu-22.04):
  `/root/wksim-release-acceptance-fe3/validation/joint-public-flight-rfw9nmbb`
- Flight status in `result.json`: `failed`, `RateUnmet('rate_unmet/resource_insufficient')`,
  `source_unchanged: true`
- Epoch: `9b18d3d1322749db8e7dfccd7891b885` (identical in `rate.jsonl`, every
  report, and `result.json`)

## 1. Method and independence

`ds_group_audit.py` is a stdlib-only CLI that re-reads the raw rows and
re-derives every number:

| Input | sha256 | bytes |
| --- | --- | --- |
| `group-work-timing.jsonl` | `8f2d60a4adefdf0b96f5d3df19061a4f866bdede54267fcc39821be8e1e59c50` | 57 384 |
| `rate.jsonl` | `7aa7e3f4624a5128d1301e6ca1f7d4baaa239357d920154a185546a496202d01` | 19 234 460 |
| `result.json` | `9e2caf5c58a7011642a3580341b999c21ac53bd52f0718b3cd8ed4e2a6dc4c27` | 131 621 |

`tools/group_work_timing.GroupWorkTiming` is **not imported, called, or used as
an oracle**. The only formulas re-implemented are the archived ones, quoted from
the archived sources shipped inside the same evidence directory:

- `Simulator/wksim_runtime/joint_rate.py` — `period_ns = int(4_000_000/rate)`,
  `earliest = max(ideal, previous_actual_start + period)`,
  `lateness = max(0, actual - ideal)`, `LATE_LIMIT_NS = 100_000_000`.
- `Simulator/wksim_core/joint.py` — per-tick diagnostic rows and the three
  stages `health_and_models` / `encode_send` / `native_inputs`.
- `tools/group_work_timing.py` — the census decomposition and report shape
  (read for the contract only; never executed).

Checks performed, all failing closed:

1. **Report structure**: schema/classification/`full_acceptance` declarations,
   census mode, one epoch, segment and tick ordering, four step windows,
   four retained steps, three phases with `samples == 4`.
2. **Exact work identity**: `prefix + 4 step durations + 3 inter-step gaps +
   suffix == work_ns`, with each region recomputed from the recorded windows and
   every region non-negative; `excess_ns == work_ns - period_ns`;
   `work_ns > period_ns`.
3. **Span and containment**: every step window inside
   `[actual_start_ns, actual_end_ns]` from `rate.jsonl`, windows non-overlapping
   in tick order, every native wait inside its own tick's `native_inputs` stage
   (stage start = window start + health + encode), waits ordered and
   non-overlapping per tick, `arducopter` waits carrying `ap_frame`, `px4` waits
   carrying `px4_time_us`.
4. **Original period and actual boundaries**: `period_ns` must equal both the
   rate group's own period and `int(4_000_000/requested_rate)`; every boundary
   field in the report (`ideal_start`, `earliest_start`, `actual_start`,
   `lateness`, `ideal_end`, `actual_end`, end `lateness`) must be byte-equal to
   the real `rate_group_start` / `rate_group_end` rows; the whole flight's
   no-catch-up contiguity law is re-checked over all 24 661 groups.
5. **Over-budget set and cap**: over-budget groups are derived from
   `rate.jsonl` work vs. the declared period, not from the reports; the emitted
   reports must be exactly the leading over-budget groups in stream order and
   must not exceed the declared `report_limit`.
6. **Counters**: all six declared counters are compared against independently
   recomputed values; group accounting is replayed from the closed rate
   boundary pairs.
7. **Ranking**: the measured regions are ranked from the reports; unreported
   over-budget regions are listed separately with only the fields the rate
   boundary actually measures.

Reproduce with `python run_audit.py` (writes `evidence/`), tests with
`python test_ds_group_audit.py` (67 tests: valid fixture plus surgical
malformed-input mutations; the real-archive integration test is opt-in via
`WKSIM_GROUP_AUDIT_ARCHIVE`).

Sensitivity was also probed once against a **copy** of the real archive in WSL:
incrementing a single `suffix_ns` by 1 in the first report turned the audit into
`verdict: fail` (exit 1) with `report-suffix` and `report-identity` findings,
while the untouched copy passes. The archive itself was not written to.

## 2. Result of the audit

> **Revision status — 2026-09-13: repairs complete and verified; v2 evidence is current.**
> An independent review (`validation/coordination/claude-ds-audit-review-20260913-01/`)
> confirmed five stream/admission defects that the first revision of this audit did
> not catch. All five are repaired in `ds_group_audit.py`, plus one more found by
> this verification pass:
>
> 1. **missing exact emit minimum** — the audit did not require
>    `reports_emitted == min(over_budget_groups, report_limit)`, so a truncated or
>    empty report stream with adjusted counters passed. Now checked twice
>    (`result-emit-minimum`, `report-cap-minimum`).
> 2. **unfinished group** — a `rate_group_start` without its `rate_group_end` was
>    invisible. Now reported (`rate-orphan-start`, `rate-stream-unbalanced`).
> 3. **duplicate end** — a second `rate_group_end` for one group was counted as a
>    completed group. Now reported (`rate-duplicate-end`); duplicate starts too
>    (`rate-duplicate-start`).
> 4. **global order / one-open-group** — pairwise "an end follows its own start" is
>    *not sufficient*: moving every end behind every start satisfies it and was
>    still admitted. The stream now holds **at most one open group**: a start while
>    another group is open is `rate-group-overlap`, an end with no matching open
>    group is `rate-end-without-open-group` / `rate-end-group-mismatch`, an unclosed
>    open group at end of stream is `rate-open-group-unclosed`, and the event-order
>    reconciliation is `rate-open-group-reconciliation`. Unrelated rate events
>    (`rate_request`, `rate_bootstrap`, `rate_anchor`, `rate_unmet`,
>    `rate_boundary_check`, `rate_segment_end`) may appear between the start and the
>    end freely. The pairwise `rate-stream-order` check is retained as a complement.
> 5. **tick binding** — row ticks were never compared with the group boundaries.
>    Now `rate-start-row-tick` / `rate-end-row-tick` bind them, matching the frozen
>    consumer rule.
>
> Also corrected: §7's gap categorisation (all 48 retained gaps are intra-group and
> join steps P+1..P+4 of one group; the earlier "macro boundary" label was wrong).
>
> Verified against the reviewer's own byte-pinned counterexamples with
> `python verify_counterexamples.py` — **7/7 cases** behave as required
> (`evidence/verification-v2.json`): the raw baseline passes with zero findings;
> `rate-e1` (missing end), `rate-e2` (duplicated end), `rate-e3` (tick binding),
> `rate-e4` (globally reordered ends), `reports-e5a` (10-report shortage) and
> `reports-e5b` (0-report shortage) are all rejected with the expected codes; every
> reviewer input's sha256 was unchanged across the run. The full suite (92 methods)
> passes, including both opt-in archive integration tests against the raw
> `/root/wksim-release-acceptance-fe3/.../joint-public-flight-rfw9nmbb` archive,
> which still passes with 0 errors and `over_budget_groups = 18`, `emitted = 16`,
> `dropped = 2`.
>
> **Superseded snapshot.** `evidence/joint-public-flight-rfw9nmbb-audit.json` and
> `evidence/joint-public-flight-rfw9nmbb-gap-map.json` are the **pre-repair**
> artifacts and are preserved unchanged, explicitly superseded by the `-v2` files
> below. The gap-map snapshot in particular still carries the wrong
> `gaps_macro_boundary: 16`; the v2 artifact carries `gaps_intra_group: 48` /
> `gaps_crossing_rate_boundary: 0`.

Current (v2) artifacts, from the repaired tools:

```
verdict: pass        errors 0   warnings 0   infos 0
artifact evidence/joint-public-flight-rfw9nmbb-audit-v2.json
         sha256 b7aca7d81eb43bbe4a30a9f41265bc2dc03b7f1ad42e6dd6dd085eee02cc5712
gap map  evidence/joint-public-flight-rfw9nmbb-gap-map-v2.json
         sha256 c32917d75e7fccac47cc329c042572e78d4bb9c8d4ce10fea514f711c3323ce3
verify   evidence/verification-v2.json
tool     ds_group_audit.py sha256 6264bdbdfb0cd6d910518755e5fb4ad2b016a9796b5fb2adf8affe7d58a26d9c
tool     gap_map.py        sha256 36ba344f35258ca321b8bbe35b32597667a383d605e59c746efd83510e3a62bd
```

```
verdict: pass        errors 0   warnings 0   infos 0
artifact evidence/joint-public-flight-rfw9nmbb-audit.json   (PRE-REPAIR, superseded)
        sha256 ba8c28340dc4fc5c4fd084f3f7b24c10af6f16dcece0256cc05310e88b32cb6f
tool    ds_group_audit.py sha256 9d6fca1e22d73496f2df17d4718a7756dc0474262a56bd83e5e516eacfb26825
```

Those are the hashes recorded by the generation run; the authoritative current
pair is whatever `evidence/joint-public-flight-rfw9nmbb-audit.manifest.json`
records, and `python run_audit.py` rewrites both the artifact and the manifest
(including the follow-on gap-map artifact and its hashes) together.

All 16 emitted reports are internally exact and agree with the real rate
boundaries:

- every report's `prefix + steps + gaps + suffix` closes to its `work_ns`
  **and** to `actual_end_ns - actual_start_ns` from `rate.jsonl`;
- every boundary field equals the corresponding rate row exactly;
- phase wall/CPU totals equal the summed four step windows;
- all 80 native waits sit inside their tick's `native_inputs` stage and inside
  the group span; 72 of 80 record `thread_cpu_ns > wall_ns` (see §6).

Counters, declared vs. independently recomputed:

| counter | declared | recomputed |
| --- | --- | --- |
| `groups_complete` | 24 661 | 24 661 |
| `groups_incomplete` | 0 | 0 |
| `over_budget_groups` | 18 | 18 |
| `reports_emitted` | 16 | 16 |
| `reports_dropped` | 2 | 2 |
| `diagnostic_errors` | 0 | 0 |

`rate.jsonl` contains exactly 24 661 `rate_group_start` / `rate_group_end`
pairs, all contiguous (tick gap 0 across all 24 660 transitions), all
satisfying the no-catch-up equation, all at rate 0.5 with period 8 000 000 ns,
in one segment, ending in the single latched `rate_unmet` at tick 98 684
(`lateness_ns = 100 019 970`, i.e. 20 µs past the frozen 100 ms limit,
`completed_groups = 24 661`).

The group tally is recomputed from the rate boundaries; a diagnostic-row
rejection *inside* a group is not observable in `rate.jsonl`, so that specific
declared zero is not independently recoverable from these three artifacts (the
16 reports nevertheless contain no rejected or malformed row signal).

## 3. Over-budget accounting

Eighteen four-tick groups exceeded their 8 ms period; the report cap emitted the
first sixteen in stream order and dropped the last two.

```
over-budget total work   175.677 ms   (18 groups)
  measured (16 reports)  155.753 ms
  unreported (2 groups)   19.924 ms
over-budget total excess  31.677 ms
  measured                27.753 ms
  unreported               3.924 ms
```

## 4. Ranked measured regions (from the 16 actual reports)

Ranked by measured `work_ns`; shares are of that region's work. `bare span` is
work not covered by any phase, gap or prefix/suffix — it is 0 for all 16.

| # | tick | work ms | excess ms | exc % | health | encode | native | gaps | pre+suf | largest step | largest gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 10 524 | 12.273 | 4.273 | 53.4 | 52.7 % | 3.6 % | 15.0 % | 26.5 % | 2.2 % | 5.195 ms @10526 | 1.743 ms |
| 2 | 10 516 | 12.179 | 4.179 | 52.2 | 22.7 % | 3.5 % | 44.9 % | 24.5 % | 4.5 % | 4.257 ms @10520 | 1.805 ms |
| 3 | 20 684 | 10.954 | 2.954 | 36.9 | 20.0 % | 2.6 % | **64.6 %** | 9.7 % | 3.1 % | 6.774 ms @20688 | 0.426 ms |
| 4 | 18 812 | 10.535 | 2.535 | 31.7 | 25.3 % | 3.6 % | 13.2 % | **56.1 %** | 1.8 % | 1.428 ms @18816 | **4.988 ms** |
| 5 | 45 208 | 10.361 | 2.361 | 29.5 | **71.9 %** | 5.2 % | 11.9 % | 9.0 % | 2.0 % | 5.962 ms @45211 | 0.446 ms |
| 6 | 5 500 | 10.046 | 2.046 | 25.6 | 18.8 % | 3.4 % | 66.4 % | 8.7 % | 2.7 % | 6.638 ms @5504 | 0.467 ms |
| 7 | 1 996 | 9.641 | 1.641 | 20.5 | 18.4 % | 3.0 % | 68.9 % | 7.5 % | 2.2 % | 6.617 ms @2000 | 0.284 ms |
| 8 | 10 500 | 9.606 | 1.606 | 20.1 | 34.1 % | 4.8 % | 17.7 % | 29.8 % | 13.6 % | 1.605 ms @10501 | 1.271 ms |
| 9 | 10 540 | 9.581 | 1.581 | 19.8 | 54.4 % | 4.6 % | 20.3 % | 18.3 % | 2.5 % | 3.416 ms @10542 | 1.184 ms |
| 10 | 32 096 | 9.001 | 1.001 | 12.5 | 26.4 % | **28.8 %** | 34.3 % | 7.5 % | 3.0 % | 5.198 ms @32100 | 0.330 ms |
| 11 | 10 560 | 8.933 | 0.933 | 11.7 | 41.5 % | 5.6 % | 20.8 % | 29.4 % | 2.7 % | 2.107 ms @10562 | 1.229 ms |
| 12 | 10 460 | 8.889 | 0.889 | 11.1 | 41.3 % | 7.3 % | 15.2 % | 33.0 % | 3.2 % | 1.726 ms @10461 | 1.954 ms |
| 13 | 62 400 | 8.842 | 0.842 | 10.5 | 47.7 % | 7.5 % | 23.9 % | 14.0 % | 7.0 % | 2.564 ms @62403 | 0.515 ms |
| 14 | 53 156 | 8.602 | 0.602 | 7.5 | 36.1 % | 5.8 % | 31.0 % | 24.9 % | 2.2 % | 2.451 ms @53159 | 1.510 ms |
| 15 | 53 200 | 8.171 | 0.171 | 2.1 | 32.1 % | 11.1 % | 24.0 % | 12.7 % | **20.2 %** | 2.598 ms @53204 | 0.436 ms |
| 16 | 10 348 | 8.138 | 0.138 | 1.7 | 34.5 % | 6.3 % | 31.2 % | 21.9 % | 6.0 % | 2.132 ms @10352 | 0.787 ms |

Aggregate over the 16 measured regions:

| region kind | total | share of measured work |
| --- | --- | --- |
| `health_and_models` | 56.190 ms | 36.1 % |
| `encode_send` | 9.922 ms | 6.4 % |
| `native_inputs` | 49.544 ms | 31.8 % |
| inter-step gaps | 32.788 ms | 21.1 % |
| prefix + suffix | 7.309 ms | 4.7 % |
| visible native waits (inside `native_inputs`) | 45.487 ms (AP 25.401, PX4 20.086) | 29.2 % |

Findings that hold for the measured set:

- **No single dominant stage across the whole set.** `health_and_models`
  dominates rank 5 (71.9 % of 10.361 ms) and rank 9 (54.4 %), while
  `native_inputs` dominates ranks 3/6/7 (64.6 %, 66.4 %, 68.9 %). The two stages
  together are 68 % of measured work.
- **The most expensive region is not dominated by the native wait at all.**
  Rank 1 (tick 10 524, +53.4 % over period) spends 52.7 % in
  `health_and_models`, has only 1.657 ms of visible native wait, and its excess
  is spread across one long step (5.195 ms) plus 3.257 ms of inter-step gaps.
- **Inter-step gaps are the second-largest single cost and are concentrated.**
  32.788 ms of the 155.753 ms measured work sits *between* steps. The largest
  single gap in the whole evidence is 4.988 ms at tick 18 812 (rank 4), whose
  four steps total only 4.438 ms — i.e. that group's overrun is mostly not
  inside its steps.
- **A tight cluster at ticks 10 348–10 564** contributes 8 of the 16 measured
  regions (7 of them between 10 348 and 10 564), including both of the two most
  expensive. This is a description of where the measured excursions occur, not
  an explanation of why.
- **`encode_send` is small but not invisible**: 6.4 % of measured work overall,
  up to 28.8 % (rank 10, tick 32 096).
- The excess ratio (`excess_ns / period_ns`) ranges 1.7 % (tick 10 348) to
  53.4 % (tick 10 524).

## 5. The two unreported over-budget groups — measured, not explained

The cap is `report_limit = 16`; 18 groups were over budget, so the last two in
stream order were counted as dropped and no report was written for them.

| start tick | work ms | excess ms | exc % | measured from | unknown |
| --- | --- | --- | --- | --- | --- |
| 80 652 | **11.915** | 3.915 | 48.9 % | `rate.jsonl` boundary only | phases, steps, gaps, native waits |
| 98 044 | 8.009 | 0.009 | 0.1 % | `rate.jsonl` boundary only | phases, steps, gaps, native waits |

Both are explicitly **not** decomposed here: `group-work-timing.jsonl` holds no
report for them, `joint-wire.jsonl` retains no diagnostic CPU/native rows (its
kinds are `sensor`, `actuator`, `step`, `barrier`, `gps`, plus two
`diagnostic_gc_timing` rows only), and every other artifact is a boundary or
counter record. Inventing per-phase numbers for them would be fabrication.

Two consequences worth stating plainly:

- **The second-most-expensive over-budget group of the flight was never
  reported.** Tick 80 652 took 11.915 ms of work (+3.915 ms over the 8 ms
  period). Among all 18 over-budget groups that is the second-largest work
  (rank 1, tick 10 524, is 12.273 ms) and the second-largest excess (tick 10 524
  is +4.273 ms). Its internal composition is unknown from this archive: had the
  cap been one report larger, the ranking picture in §4 would look different.
- The dropped pair also contains the **smallest** excursion of the flight
  (tick 98 044, +0.009 ms), which is itself close to the granularity of a
  boundary reading.

Explicit accounting rule used here: the phase/step/native-wait totals in §4 and
the aggregate table cover **only** the 16 measured regions. The 19.924 ms of
unreported work contributes nothing to them *by construction*, not because those
groups had no internal cost.

## 6. Measurement facts and limits

1. **Thread CPU can exceed wall, so wall minus thread CPU is not off-CPU time.**
   72 of 80 recorded native waits show `thread_cpu_ns > wall_ns` (e.g. tick 1 997
   in the first report: wall 201 868 ns vs. thread CPU 202 228 ns), and region
   rank 2 shows a negative wall-minus-thread-CPU of −1 843 ns in
   `native_inputs`. The two readings come from shifted measurement windows, so
   their difference is a *measured difference between the monotonic clock and the
   thread CPU clock with window uncertainty*. It is not exact off-CPU time, and
   it is reported as recorded — not corrected, not treated as an error, and not
   read as evidence about scheduling.
2. **Native waits bracket only the supervisor call.** Each wait covers the
   `wait_ap` / `wait_px4` call alone; `acknowledge_ap`, `barrier` /
   `repair_input` and every record write stay in the combined `native_inputs`
   stage. The 80 visible waits total 45.487 ms against a `native_inputs` phase
   total of 49.544 ms; the 4.057 ms difference is stage time not covered by a
   retained wait, not unexplained work.
3. **Measured wall-minus-thread-CPU differences, no cause.** Across the 16
   measured regions that recorded difference is 16.993 ms in
   `health_and_models` (56.190 ms wall vs. 39.196 ms thread CPU), 0.046 ms in
   `encode_send`, and 14.681 ms in `native_inputs` (49.544 ms wall vs. 34.864 ms
   thread CPU). Given point 1 these are *differences with window uncertainty*,
   not off-CPU spans. These artifacts cannot identify whether they came from the
   OS scheduler, the host, the native flight controller, Windows, RPC/IO, or a
   combination, and no such attribution is made here.
4. **Census coverage is per measured group only.** Census mode guarantees four
   CPU rows for the sixteen reported groups; it says nothing about the other
   24 645 complete groups, 24 627 of which were within budget and were counted in
   memory without any diagnostic row being written.
5. **Scope.** Every identity above is checked inside this single archived
   flight. Nothing here transfers to other flights, other profiles, or other
   sources.
6. **Raw data untouched.** The archive was read through WSL; no file in it was
   created, modified, or deleted by this audit.

## 7. Inter-step gap map (follow-on task)

`gap_map.py` / `evidence/joint-public-flight-rfw9nmbb-gap-map.json` map the
recorded inter-step gaps onto the executed source, using this audit's artifact
for the gap numbers and the archived runner/joint/rate sources for the code
citations (each region carries the source's sha256 and resolved line span).
No wksim module is imported. Verdict `pass`, 0 findings.

**What a recorded gap is.** `gap[i] = step_window[i+1].wall_start_ns −
step_window[i].wall_end_ns`, both marks read by `time.monotonic_ns` in the
runner process: mark #1 at `JointPhysics.advance()` entry
(`Simulator/wksim_core/joint.py:181`), mark #3 after `finish_inputs()`
(`joint.py:219`, the last clock read of that step). So a gap is exactly *the
interval between the last mark of one step and the first mark of the next* — it
contains the tail of the closing step and the head of the opening step, and it
excludes both step bodies, the model round trip, the sensor emit and every
native wait.

**48 gaps, 32 787 583 ns total** across the 16 measured groups. Every retained gap
joins the marks of steps **P+1..P+4 of one group** — index 0 is P+1→P+2, index 1
is P+2→P+3, index 2 is P+3→P+4 — so **all 48 are intra-group and none of them
crosses a rate boundary**. An earlier revision of this section mis-categorised
index 2 as a "macro boundary"; that was wrong and is corrected here. The
group's `rate.end_group` is recorded *after* the P+4 step mark and the next
group's `rate.begin_group` *before* the P+5 mark (the archived runner gates both
on `clock.tick % 4` checks in `advance()`, ahead of and behind the measured
steps), so neither is inside any of these gaps.

**Largest gap: 4 987 926 ns, tick 18 814 → 18 815** (group 18 812, index 1; it is
47.3 % of that group's work). Executed regions, in order
(`tail` = before the next step's mark #1, `head` = after it):

| # | phase | region | citation |
| --- | --- | --- | --- |
| 1 | tail | `finish_inputs()`; mark #3; `diagnostic_step_cpu_timing` record | `Simulator/wksim_core/joint.py:217-223` |
| 2 | tail | `advance()` returns the committed states and the `PX4 actuator startup` guard | `joint.py:225-227` |
| 3 | — | `JointRate.end_group()` | `Simulator/wksim_runtime/joint_rate.py:132-143` — **not inside this gap** (it runs after the P+4 mark) |
| 4 | tail | `publisher.publish(clock)`; `clock_log.write(json.dumps(clock.snapshot()))` | `tools/run_joint_flight.py:1031-1032` |
| 5 | head | `while clock.tick < MAX_TICKS:` loop overhead, `health()`, `advance()` | `tools/run_joint_flight.py:1036-1044` |
| 6 | head | `health()`: `physics_health()` then the non-blocking `child.poll()` sweep | `tools/run_joint_flight.py:651-669` |
| 7 | — | `JointRate.begin_group()` | `joint_rate.py:89-130` — **not inside this gap** (it runs before the next group's P+1 mark) |
| 8 | head | `advance()` prologue: the pre-advance `clock.tick % 4` rate gate, then `physics.advance()` | `tools/run_joint_flight.py:997-1030` |
| 9 | head | `JointPhysics.advance()`: mark #1, then `self.health()` | `joint.py:180-182` |

So every measured gap is: the closing diagnostic records, the states return, the
clock publication + `clock.jsonl` write, the runner loop overhead, the `health()`
poll sweep, the `advance()` gate, and the next step's entry down to mark #1. The
`rate.end_group` / `rate.begin_group` work belongs to the group suffix and the
next group's prefix, not to any gap measured here.

**Representative cluster 10 348–10 564** — 21 gaps totalling 18 193 939 ns:

| group | gap 0 | gap 1 | gap 2 |
| --- | --- | --- | --- |
| 10 348 | 410 148 | 787 258 | 586 163 |
| 10 460 | 543 565 | 1 953 658 | 437 261 |
| 10 500 | 1 160 017 | 1 270 681 | 426 489 |
| 10 516 | 407 040 | 1 804 866 | 773 601 |
| 10 524 | 1 166 374 | 1 743 467 | 347 045 |
| 10 540 | 1 184 284 | 267 657 | 301 471 |
| 10 560 | 1 159 347 | 234 301 | 1 229 246 |

All three columns are intra-group gaps of the same kind; gap 0 and gap 1 here are
the largest intra-group gaps in the whole evidence after tick 18 812.

**Clock handling and its bound.** The only alignment needed is
`S = started` in the wire's `wall = time.monotonic() − started`: both the marks
and every other mapped number come from the same process's monotonic clock, so
no cross-host, cross-namespace or cross-clock offset is assumed. `S` is derived
from the data: each `step` row is written inside its own step's window, so `S`
must satisfy `step_start ≤ wire_wall + S ≤ step_end` for all 64 measured steps.
The intersection is **[52 296 472 837, 52 297 016 008] ns, width 543 171 ns**,
and all 16 measured regions accept the same interval. The width is set by one
binding step (tick 1 999, the shortest window at 543 171 ns), which is why it is
not tighter.

**What the wire can and cannot localise.** Every `step`/`barrier` row is written
*inside* its own step window, and each window closes at or opens after the
adjoining gap boundary, so **no joint-wire row is written after the first instant
of any of the 48 measured gaps** (checked per row, 0 rows inside). The wire
therefore contributes the executed event order and the window cross-check, and
**cannot** sub-divide a gap. The only `diagnostic_gc_timing` rows in the whole
flight are at tick 0 (generations 0 and 2), far outside every measured gap.

**Diagnostic path vs. product path.** The region list above is the diagnostic
run. In the default product path: mark #1/#2/#3, the `diagnostic_*` rows and the
`record()` short-circuit that keeps them off `joint-wire.jsonl`, and the
`gc.callbacks` hook do not exist at all (`joint.py:181`, `216-219`, `279-284`,
`60-72`; `run_joint_flight.py:884-891`). The gap equation itself is a
measurement construction — in the product path there is no mark to close or open
it. The `publisher.publish(clock)` + `clock.jsonl` write and the `health()` poll
sweep **are** product-path code and are part of any real inter-step interval.
Nothing here is labelled dead time or descheduling: the artifacts record no
scheduling state, and the word is deliberately unused.

**Smallest additional measurement needed.** These artifacts cannot split the
measured gap into thread-CPU execution and non-CPU wall time, because the
`diagnostic_step_cpu_timing` row only brackets a step's own body; there is no CPU
reading over the gap, and the harness has no per-tick kernel/`procfs` reading
(and none is proposed). The smallest extension that would narrow it is a
**seam-localised mark pair**: two `(time.monotonic_ns(), time.thread_time_ns())`
reads captured once the closing step's marks are finished and once immediately
before the next step's mark #1, carried on the *existing* census diagnostic row
as `seam_wall_ns` / `seam_thread_cpu_ns`. That is four clock reads per measured
gap, no new file, no syscall, no product-path behaviour change.

It would **not** yield exact off-CPU time, and no such claim is made: the paired
clocks are read at different instants over shifted windows, exactly as the
existing rows are, and 72 of the 80 recorded native waits already show
`thread_cpu_ns > wall_ns`. What it yields is a *tighter measured difference
between the monotonic clock and the thread CPU clock*, which must still be
reported with its window uncertainty and never as off-CPU time, scheduling state
or a cause.

## 8. What this audit does not claim

- No acceptance verdict of any kind. The evidence remains
  `classification = diagnostic_only`, `full_acceptance = false`; the flight
  already terminated `failed / RateUnmet` on the frozen 100 ms late limit, and
  this audit neither re-opens nor upgrades that outcome.
- No causal OS, host, native-FC or Windows attribution for any wall, thread-CPU,
  gap or wall-minus-thread-CPU observation.
- No statement about the two unreported groups' internal composition, and no
  phase, step or native-wait number anywhere that did not come from a written
  report row or a rate boundary.
- No claim that the sixteen reports are representative of the other over-budget
  groups, of the 24 627 in-budget groups, or of the groups leading up to the
  tick-98 684 late limit.
- No label of dead time, idleness or descheduling for any measured gap, and no
  claim that a gap's internal composition is known — §7 states the opposite and
  names the one measurement that would decide it.

## 9. Deliverables in this directory

| file | role |
| --- | --- |
| `ds_group_audit.py` | independent stdlib audit CLI (report + rate + result identities, one-open-group stream law, exact emit minimum, cap, counters, ranking) |
| `test_ds_group_audit.py` | 76 offline tests: valid synthetic fixture, malformed-input mutations, and the five repaired stream/admission defects (`StreamDefectRepairTest`); opt-in real-archive test |
| `gap_map.py` | inter-step gap → executed-source mapper with clock-offset bounds; all 48 gaps intra-group |
| `test_gap_map.py` | 16 offline tests: synthetic source tree + audit artifact, anchor resolution, offset bounds, wire-window reasoning |
| `verify_counterexamples.py` | runs the repaired audit against the reviewer's byte-pinned counterexamples; writes `evidence/verification-v2.json` |
| `run_audit.py` | reproduces the versioned `evidence/` artifacts from the read-only WSL archive (`--version`, default `v2`; older versions are never overwritten) |
| `sync_coordination_scope.py` | copies these deliverables into the assigned coordination scope with a SHA manifest, preserving older snapshots |
| `evidence/joint-public-flight-rfw9nmbb-audit-v2.json` | machine-readable audit report (current, repaired tool) |
| `evidence/joint-public-flight-rfw9nmbb-gap-map-v2.json` | machine-readable gap mapping (current, corrected categorisation) |
| `evidence/joint-public-flight-rfw9nmbb-audit-v2.manifest.json` | archive, tool and artifact hashes, exit code, verdicts |
| `evidence/verification-v2.json` | counterexample verification: 7/7 cases, reviewer input hashes unchanged |
| `evidence/joint-public-flight-rfw9nmbb-{audit,gap-map}.json`, `…-audit.manifest.json` | **pre-repair snapshots, preserved and explicitly superseded** |
| `recon_probe.py`, `recon_probe2.py`, `scratch_offset.py`, `inspect_counterexamples.py`, `README-probes.md` | reconnaissance used to derive the invariants (not part of either tool) |
