# UDE runtime acceptance preflight — 2026-09-09

Both real Ubuntu-22.04 candidate preflights passed: exit `0`, `ok=true`, `reasons=[]`. Each selects the exact frozen UDE protocol and `Simulator.wksim_control.position_ude.PositionUDE`. Their repository source hashes matched the preflight candidate. Later fixes require fresh admission and retain these earlier results unchanged.

The first PX4 flight (`ude-px4-acceptance-20260909-01`) failed before controller updates: frozen integer coordinates were passed to ROS float-only fields. `px4-attempt-01/` preserves the result/progress/postflight/revocation records; command and strict rejection reports are beside this README. All children were reaped, cleanup errors were empty, and source/candidate identities remained unchanged. Raw native evidence remains under `/root/wksim-pid-flight-ude-px4-acceptance-20260909-01/`. This is a rejected attempt, not an acceptance pass.

| Stack | Run ID | stdout SHA256 |
| --- | --- | --- |
| px4 | `ude-px4-admission-20260909-01` | `45f7680ed9d2db71c25e54eea70409b78fb1298f8795cbf22bd625da8f2691b6` |
| arducopter | `ude-arducopter-admission-20260909-01` | `18e9f27a1cb369b4fee8bb75025d6cf762644d8a896feb21c9a16bc9fff83020` |

Actual invocation was `wsl -d Ubuntu-22.04 -u root -- bash tools/run-pid-flight.sh --stack <stack> --run-id <ID above> --config Simulator/wksim_runtime/ude-flight-v1.json --preflight` from the repository root. Each `<stack>-preflight.json` retains exact argv, cwd, timing and exit code; stdout retains full admission/configuration/source and installed-resource identities. `preflight.py` is the capture helper.

Both stderr files preserve the same UTF-16LE WSL localhost-proxy/NAT warning. It did not prevent admission; no evidence was rewritten.

Both admissions report `children_created=0`, `ros_nodes_started=false`, `flown=false`, and `production_admitted=false`. These are preflight results only: #91/#92 UDE flights, fresh run calibration, native evidence and fixed physical budgets have not passed. #36 flight acceptance is not claimed.

Offline implementation checks and 1,200 equation comparisons remain in `../ude-runtime-implementation-20260909/`. The exact flight and audit commands are in `../../docs/plan/36-ude-runtime-contract.md`; audit commands include `/root/wksim-attitude-audit-deps-g_2y8olg` on PYTHONPATH.
