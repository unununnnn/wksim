# #117 / 47-coordinate-module

Implemented the #116 frozen pure resolve/validate_current boundary in exactly:

- Simulator/wksim_control/global_reference.py
- validation/test_global_reference.py

Additional files are confined to this new evidence directory, as allowed by the execution guide section 5. AGENTS.md, the execution guide and concurrent #115 documentation are excluded.

## Result

PX4 spherical MapProjection produces float32 NED, with a separately identified EKF origin and explicit AMSL/home-relative conversion. AP preserves FRAME_GLOBAL_REL_ALT and native truncated e7/cm values; its ENU result is a numeric check, not a local command. Inputs retain their original datum and identities. Invalid datum, bounds, navigation, stale snapshots, replayed commands, changed home/origin/reset identities and regressed clocks reject with stable reasons. Repeated source timestamps cannot renew freshness.

The API has no ROS or clock I/O. Its host must retain the returned validation checkpoint, persist command IDs, build verified native observations, latch clock invalidation, discard a rejected target and invalidate on pause/resume. Those native lifecycle operations remain #118. Datum proof strings are required evidence references, not proof that a caller's sensor datum is correct. AP same-value home reset remains undetectable with the present native tuple; no such capability is claimed.

Final Windows suite: 16 discovered, 15 passed, 1 explicitly skipped (native C++ oracle unavailable in that invocation). Final WSL suite: 16 passed, zero skips. The WSL oracle ran 60 input rows against both stack calculations: PX4 N/E/z maximum absolute error 0 m, AP Location ENU maximum absolute error 0 m, native AP e7/cm exactly equal. AP maximum height roundtrip error 0.009999999999990905 m. Geographic roundtrips meet 1e-9 degrees without quantization and 2e-7 degrees with quantization in the tested envelope. These are numeric results, not flight errors.

Tests include zero coordinates, southern/western hemispheres, both sides of the date line, +/-85 degrees, inside/outside 100 m, distinct nonzero home/origin heights, unsupported datums, NaN/Inf/bools, expiration, duplicate/regressing timestamps, run/epoch/home/origin mismatch and reset counters. Numeric tolerances are unchanged from #116.

## Exact commands (project root)

```powershell
D:/date/miniconda/python.exe validation/test_global_reference.py
wsl -d Ubuntu-22.04 -- bash -lc "g++ -std=c++17 -O0 -ffp-contract=off validation/lunar-117-20260909-coordinate-01/oracle.cpp -o /tmp/wksim-117-oracle && python3 validation/test_global_reference.py --oracle /tmp/wksim-117-oracle"
git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --cached --check
```

Final raw logs: windows-final.log and wsl-verified.log. The latter includes every oracle input and output. identity.txt hashes both deliverable files, oracle, contract and read adapter/task sources. native-identity.log records compiler version, native source hashes and git IDs.

Oracle attribution: PX4 geo.cpp initReference/project at d6f12ad1c4f70ad3230afd7d86e971421e02fef4 (BSD-3-Clause), ArduPilot Location.cpp longitude_scale/diff_longitude/get_distance_NED at 1511f27194f1dcc3728270883047bdf022b3fd53 (GPL-3.0-or-later). Harness uses their method bodies with whitespace formatting and a field/vector/scalar shim; it does not link full firmware. AP definitions.h M_PI/DEG_TO_RAD and Location float scaling were checked directly. Absolute-height and DDS truncation plumbing is explicit harness code, not a flight observation.

## Failed iterations and limits

The initial test assumed spherical 99.9 m was within AP's 100 m Location fence. AP's distinct scaling correctly rejected it. Positive fixtures now use 99.8 m; neither fence nor acceptance tolerance was relaxed. The implementation checks both unquantized and quantized bounds.

wsl-final.log records an intermediate failure because /tmp/wksim-117-oracle was absent in a later WSL invocation. Rebuilding and running within the same command fixed that operational failure; wsl-verified.log is the subsequent successful run. Earlier windows-tests.log/wsl-tests.log are retained. WSL's unrelated localhost warning contains embedded NUL characters in the captured logs; raw bytes are retained. The initial default git whitespace check flagged CRLF logs; the documented repository cr-at-eol check is used, and the identity listing's trailing blank line was removed.

No FC, model, ROS or flight processes started. Compiler and test subprocesses terminated. No real global-waypoint flight, native installation, full-stack acceptance, Full, R1 or RateUnmet success is claimed. #47 and its dependencies remain unchanged; only #117 is eligible for closure.

Model settings: requested gpt-6-astra / low. This tool interface does not independently expose the precise actual model ID or reasoning setting, so those actual settings cannot be verified here. All work performed in this main session; no subagents.
