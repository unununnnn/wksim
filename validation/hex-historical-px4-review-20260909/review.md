# AP4.7 and exact historical PX4 source compatibility review

## AP4.7 pre-run decision: GO for one bounded retry

The parent-authorized AP-only parameter revision preserves arming checks and all physical budgets. In the actual admitted AP source `/root/wksim-ap-clock-stop-OXQqdR/src/libraries/AP_Arming/AP_Arming.cpp`, line 201 registers SKIPCHK default 0; lines 228–251 implement 4.7 migration from old CHECK and explicitly map an enabled ALL bit (old CHECK=1) to SKIPCHK=0; line 326 tests `(checks_to_skip & check) == 0`. This is a name/representation migration, not disabled arming checks. The failed run's NOT_SET type=0 response remains correctly rejected regardless of leftover integer storage.

Reviewed new protocol SHA256 `cf9bfe890cc0a5e3c04d72dd0df5d1f9fd5bb18a2c60c588393266c542fac464` differs from the unchanged legacy JSON only in schema and plan identity. AP plan is `27d3b397feace63eb308365aee3d034733ea136f956bce797a0545219600f8fc`; default/PX4 plan remains `319c5cba50eb11b81f70ac3ade707879c2fdba252335aa039674e93b9168e1a0`, with legacy protocol `33748c4374d5f297ae928d1682bc9ef00dde95030249fe5c7ff0dce21363ddcc`. Admission, defaults generation, task, source inventory, audit, and reset protocol selection are stack-specific. AP defaults contain SKIPCHK=0, and the unchanged runtime readback rejects nonzero masks and unavailable parameters. The old failed AP attempt is not retroactively accepted.

Independent command `python -B -m unittest validation.test_hex_ap47 validation.test_hex_flight -q` ran 16 tests, with 15 passing and one expected Windows skip requiring the sealed WSL dialect. The implementer separately reports and retains 24/24 targeted WSL passes. The independent review did not run any real native resource.

## Historical PX4 decision: exact paired compatibility is supportable

Direct comparison used the actual archived `/root/wksim-hex-flight-px4-03/hex-px4-03/run-source/Simulator/wksim_core/px4_mavlink.py`, SHA256 `08b3d5fbf6754822572240ceb6beb289341bd0c6653455a35b60b3fb3d85ab3d`, against current SHA256 `e8c903f2b4c84a261adf6f512c8437c51364143dc048d1ac2cb873e7cfb53260`.

The changes add the optional GnssSample/GnssSendGate path and optional raw-send capture; `Sender.capture` defaults to None. The original nested sensor helper was extracted, with `gnss_gate=None` following the original HIL_SENSOR/HIL_GPS cadence. Both normal and duplicate-actuator branches pass the unchanged `model.ticks`. `actuator_commands` and `gps_arguments` have exactly identical ASTs. The existing Hex wrapper `tools/hex_physics.py` is byte-identical to the archived wrapper, substitutes its own unchanged six-channel actuator decoder, and calls `serve` without the GNSS gate. No Hex fault injection was enabled.

`differential_replay.py` imports the two fixed source versions but never invokes serve, a model, a listener, ROS, FC, or native library. It extracts the original nested sensor function body using AST without rewriting it, binds recording senders, and processes the actual original raw stream. All 7,717 retained HIL_ACTUATOR_CONTROLS packets decode identically through original quad functions and through the identical Hex binding. All 7,731 real four-step group outputs serialize byte-for-byte identical sensor frames at their original ticks. An additional 309 duplicate-send probes use unchanged real states at GPS cadence to exercise repeated sensor output. The new optional gate is never instantiated or enabled.

Command: `python -B validation/hex-historical-px4-review-20260909/differential_replay.py`; exit 0. Exact output is in `replay-result.json`. Original raw SHA256 is `2d93088f3d11945fc582d90f49310e867894f5f52216328ccd3f347afe85d5de`. The first script attempt failed with StopIteration because the archived nested function is inside a with block; AST traversal was corrected to locate the original function. That invocation did not reach packet replay or mutate any original source/evidence.

Recommendation: allow only this explicit historical/current decoder pair for the unchanged PX4 legacy contract, continuing to verify original retained bytes and all actual raw/native/physical evidence. Any future current decoder hash must reject and require new equivalence review. Apply the same paired constraint to the already proposed historical identity-recipe exceptions:

| File | Exact historical SHA256 | Reviewed current SHA256 |
|---|---|---|
| hex_launch_plan.py | `5576dc5326261d9edd5d68352189ac2923d1ff9c2a868f9e28bc6b4be612dd0f` | `9e2a4762033d9e188eff09e469c5e1c526910b5b2b6847975854e1f2122da2cb` |
| hex_candidate.py | `337ed9fb3ff0423c7ec2da9c5e02530e413575c357349615408036830af31bbe` | `ae6e03d5098dae3e258b3c49f3c42eb32036e283ee55a2c389bff45d42e335e5` |
| px4_mavlink.py | `08b3d5fbf6754822572240ceb6beb289341bd0c6653455a35b60b3fb3d85ab3d` | `e8c903f2b4c84a261adf6f512c8437c51364143dc048d1ac2cb873e7cfb53260` |

A historical-only skip that accepts arbitrary future current code is not endorsed. This evidence supports compatibility of the frozen default path and raw audit interpretation; it is not a replacement native flight or proof of optional GNSS behavior. A fresh baseline is not necessary solely for this reviewed additive drift, provided the narrow check is applied and the actual complete PX4-03 strict re-audit passes. At this report's initial delivery, that final re-audit remains pending; the earlier rejection is preserved.

Additional direct recipe check imported the actual archived `hex_launch_plan.py` and `hex_candidate.py` without invoking admission/runtime. The complete archived launch-plan object equals current `launch_plan('px4')`, and all 77 old/current PX4 native parameters equal the actual archived admission's parameters. This independently confirms the two identity-recipe pairs alongside the decoder replay; it does not rely only on the new fixture's default/current equality.
