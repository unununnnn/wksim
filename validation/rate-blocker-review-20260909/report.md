# #62 / #20 rate blocker: measured failure and bounded encoding candidate

No production source changed. No new FC, native model, ROS, UE, socket or serial resource was started. Only this new evidence directory was written. Task settings remain the verified Astra/low session; no nested agent. Issue #62/#20/#61 bodies/comments, frozen docs, actual rate/wire/model logs and their exact named sources were read directly. No unknown structural graph exploration was needed.

## What actually failed in #62

The cpuset0–7 experiment `rate61-cpu8-20260909-e1-e2561e27` did not reach its air window. Ground readiness failed because the actual rate supervisor latched `resource_insufficient` at tick19608. This is not a new missing-flow root cause: flow.json was absent downstream of the rate failure. The original audit's unsupported `--mode steady` is a separate invocation defect, already correctly diagnosed in #62.

`analyze.py` independently reconstructs the last raw lateness **exactly to the nanosecond** from all4,892 timed groups. Anchor tick40 to tick19608 covers19.568 simulated seconds in19.673497865 wall seconds, measured0.9946375644×. The100ms phase cap is nevertheless exceeded, correctly: **105,497,865ns**. A mean rate near1× does not satisfy the separate phase cap.

| Exact phase accumulation component | ns |
|---|---:|
| First release lateness | 16,079 |
| Previous group work above4ms, summed | 57,175,054 |
| Residual release delay beyond those work overruns | 39,652,826 |
| Last group's work minus4ms | 8,653,906 |
| Total | **105,497,865** |

Median group work2.611334ms, mean2.681923ms, p99 3.972081ms; only45 of4,892 groups exceed4ms. The largest group is12.653906ms. Thus persistent average physics-compute overload is not demonstrated: rare overruns and accumulated release delays exhaust the phase budget despite ordinary groups having headroom.

The arithmetic follows `JointRate.begin_group`: release cannot precede `max(ideal, previous_start+period)`. Positive release delay is carried forward; short subsequent groups do not erase it. This is the existing no-shortened-interval policy, not a request to alter anchors/minimum spacing or the100ms/10s/60s contract.

Actual wire localization (`analysis.json`) shows mixed long-tail sites:

- Tick1926 AP sensor record→AP actuator record:7.776755ms, inside the11.502613ms group starting1924.
- Final group, step19607→AP sensor19608:5.583491ms (health/model/encoding region); AP actuator19608→PX4 actuator19608:3.385707ms.
- Another AP sensor→actuator gap at8590 is4.914685ms; AP→PX4 response at2000 is5.316448ms.

These are observed elapsed gaps, not proof of whether an FC thread, supervisor, worker, kernel or host was descheduled. Prior #61 CPU diagnostics similarly separate a5.128973ms health/model stage from only0.293791ms supervisor CPU. Neither evidence identifies Windows interrupt handling or a specific model arithmetic routine as the causal bottleneck. A speculative C++ rewrite or another unmeasured CPU-affinity choice is not supported.

## One small independently measurable implementation candidate

`Simulator/wksim_core/worker.py:model_worker` serializes the same120-value response twice on every accepted tick: once inside its complete trace record and again for RPC stdout. This is definite redundant work. Current and #62 archived worker files are byte-identical, SHA256 `5b442144ba33c35aef24198ea21578739058341f37010d7d3b064da2175255bc`.

`worker-response-reuse.patch` is a minimal proposed change: encode response once, append separately encoded commands/input/request fields to form the same full JSON trace record, reuse the response for stdout. Existing field order, newline framing, response limits, validation, logging-before-response ordering, all120 values and lifetime semantics remain unchanged. No batching, omitted evidence, new dependency, timing policy, or physical step change is proposed.

Evidence:

- `serialization_probe.py`:256 actual AP/PX4 ground trace records, exact trace and response bytes equal. Six alternating original/candidate runs in Windows CPython3.13: median7.512700ms→4.610950ms for the256-record encoding workload, **38.6% less elapsed time in this isolated encoding workload**, roughly11.33µs per record. This is not a full worker, WSL, IPC or1× performance result.
- Initial Windows `thread_time_ns` sampling was quantized at15.625ms, so its apparent100% saving is invalid; `serialization-coarse-clock-result.json` is retained only as a failed measurement. The final probe uses high-resolution perf_counter and makes no thread-CPU claim.
- `worker_probe.py`: executes the actual original/proposed worker function with one prerecorded fake Model step plus one snapshot and in-memory stdin/stdout. Trace and response bytes are identical. Original performs3 full-state encodes versus proposed2; the explicit work-count regression is red for original and green for proposed. No generated model/native library is loaded. First probe used an invalid snapshot fixture key and correctly rejected; corrected fixture uses the real `snapshot:true` request.

This supports removing duplicate serialization as a bounded efficiency fix. It does **not** prove this work caused the captured long tails or that removing it will supply60s×3. Typical groups already fit4ms; much saved ordinary work may simply become pacing idle time. No1× success or estimated completion duration should be promised from the microbenchmark.

## Precise next ownership and verification

If parent assigns the pure change, own only `Simulator/wksim_core/worker.py:model_worker`, its targeted worker protocol tests, and new evidence. Apply the reviewed small patch, use fake-worker tests to cover step/snapshot, numeric and framing rejection, serialization/log failure and single-lifetime behavior, then run existing worker transport tests. A full retained-data differential can broaden the256-record sample without starting native resources.

Before another native performance experiment, the genuinely unresolved causal probe should split worker-local wall/thread-CPU time around model.step, full-record encoding/write, response encoding/write and supervisor RPC receipt; correlate by unchanged epoch/tick. Existing supervisor health/model timing alone cannot distinguish the worker's CPU from IPC/scheduling waits. Diagnostic timing must remain opt-in and excluded from final acceptance, as the frozen candidate already requires. Parent must allocate any later instrumented runtime; this task has not launched one.

If profiling later justifies runtime changes, separate ownership would be `worker.py` timing evidence and `joint.py`/`joint_runtime.py` diagnostic correlation; keep `joint_rate.py` and all budgets unchanged. The already reverted timer-loop micro-optimization showed no benefit and should not be repeated.

The failed #62 epoch, all previous RateUnmet outcomes and #20/#62 acceptance status remain unchanged. The new evidence establishes exact failure decomposition and a small byte-preserving encoding opportunity, not a complete rate fix.
