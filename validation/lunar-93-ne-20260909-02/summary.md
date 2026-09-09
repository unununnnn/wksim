# Issue #93 — fixed Prometheus NE algorithm

Completed the pure algorithm slice only. Parent #35/#37 acceptance and runtime selection remain separate. The split-ticket guide permits source-only slices before unrelated whole-flight acceptance; the user explicitly assigned this source/test slice. No files outside #93's three source paths and its new evidence directories were changed.

## Delivered

- `Simulator/wksim_control/position_ne.py`: NEConfig, immutable NEMemory/NEOutput and PositionNE; existing ENU/FLU PIDState/PIDReference data contract reused, with no PID algorithm invocation or fallback.
- `validation/test_position_ne.py`: 12 pure tests, including cold reset, initial position, filter history, old-integral order, discarded LLF output, threshold/saturation, inactive/invalid cycles, nonfinite inputs and intermediate overflow.
- `tools/check_position_ne_source.py`: compile and call unchanged upstream C++ with real Eigen; persist inputs, raw outputs, 37-channel comparisons, pins, compiler/argv/return codes and any failure traceback in a new directory.

## Source and algorithm boundaries

Upstream `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`; NE raw SHA256 `759e3296ea32eb34050ed8764c75e4bd88f6ba8cdb52da82c5e10b745f45fe7f`. Eight original header pins are in `result.json` and the checker. Each original header was checked against its upstream git blob after CRLF normalization; originals were not edited. Python/checker/test/dependency hashes are in `source-sha256.json`.

Codebase Memory native CLI index_status was ready (50,865 nodes / 165,157 edges); search_graph NE located original init 91–137 and update 144–263. Actual source, filter headers and controller dispatcher were then read. No new Python graph coverage is claimed.

Preserved: LPF velocity plus HPF(initial-position) noise estimator; nominal PD+feedforward+noise; LLF history advances then its contribution is explicitly zeroed upstream; disturbance uses old integral; integral update only when absolute position error <100; int_max limits disturbance, not the integral. Vertical vector rescaling, independent XY tilt clipping, current-yaw force rotation and current body-Z projection are retained.

Explicit differences: construction and reset fully clear nine filters and both integrals. Original init resets integrals but only sets filter constants, so calling it again retains filter history; oracle reset reconstructs the original object. Initial-position changes require full reset. Float-valid state/reference and explicit positive mass/time constants are required; nonpositive/nonfinite dt, inactive control, zero vertical force, and nonfinite intermediate/output values reject without committing history. Original has no mode gate; callers must reset on loss/release/new epoch/time discontinuity. No ROS tracking-error print history is ported because it does not enter the equations. Python uses double; it accepts actual dt while original casts reciprocal controller_hz to float. Oracle explicitly supplies that same float32 dt to isolate algorithm equivalence.

NativeThrustConfig is reused only in the oracle with explicitly synthetic hover values; these are not real model calibrations. NE selection, session lifecycle wiring, timing admission, calibration, runtime, flight, and performance remain for subsequent tickets. No FC/model/ROS/UE process was launched. R1, RateUnmet, physical budgets and default manifests remain unchanged.

## Exact commands and results

From `C:/Users/PC/Documents/odid编译/wksim`:

```powershell
wsl -d Ubuntu-22.04 -- python3 tools/check_position_ne_source.py --evidence validation/lunar-93-ne-20260909-01
wsl -d Ubuntu-22.04 -- python3 tools/check_position_ne_source.py --evidence validation/lunar-93-ne-20260909-02
python -m unittest validation.test_position_ne validation.test_position_pid -v
git diff --check
```

Both oracle runs exit 0. Final run: 655 fixed rational cases × 2 parameter sets = 1,310 original C++ updates × 37 channels = 48,470 comparisons, all passed. Inputs include thresholds, 400 stateful samples, 240 changing trajectory/reset samples, three periods and force limiting. Absolute tolerance 2e-6 / relative tolerance 2e-7 was declared before compilation and unchanged; maximum absolute error 5.557479489937123e-7 N. Filter/integral/noise/nominal/disturbance channel errors were zero in this fixture. Compiler version, complete argv and raw stdout/stderr are retained. C++ visibility is opened only after standard dependencies are parsed; mathematical function bodies are unchanged.

Windows and WSL each passed 24 tests (12 NE + 12 existing PID), zero skipped. First run is retained. Review then added rejection for force-rescaling overflow before tilt clipping could hide it, plus a corresponding negative case; the second run verifies the final source. No tolerance or original fixture was relaxed.

The current task's latest local turn_context metadata was read from rollout `01a0856d-88b0-7d22-a5bf-aaea2d5f3fc1`: model `gpt-6-astra`, effort `low`. No subagents were used.

This evidence proves the fixed-source pure comparison and declared failure/reset boundaries, not flight or performance acceptance.

Staged source-only `git diff --cached --check -- Simulator/wksim_control/position_ne.py tools/check_position_ne_source.py validation/test_position_ne.py` passes. The full staged check reports trailing spaces in untouched captured C++ stdout and the compiler version's blank final line; raw evidence is intentionally preserved byte-for-byte. The compiler also emits the existing upstream math_utils.h sign_function missing-return warning; compilation exits 0, and that helper is not called by the NE algorithm.
