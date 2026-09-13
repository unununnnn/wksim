# G3 continuous-clearance final seal — 2026-09-14

## Verdict

PASS for the pure-Python G3 continuous-clearance slice. The strict default now admits only when both the sampled gate and the continuous B-spline control-hull certificate pass. The pump reports `continuous_clearance_unproven` as `rejected_continuous`, and an unmapped future admission reason raises instead of being silently relabelled.

This seal does not close #102 or #39 and makes no ROS, flight-controller, UE, MATLAB, native-build, dynamics, tracking-error, or flight-safety claim.

## Independent checks

- `python -B validation/coordination/omp-g3-final-seal-20260914-01/probe.py` — 28/28 checks passed.
- `python -B -m unittest validation.test_ego_scene_admission` — 42 tests passed.
- `python -B -m unittest validation.test_planner_transport_pump` — 57 tests passed.
- `python -B -m unittest validation.test_planner_transport_receiver` — 27 tests passed.
- `git diff --check -- <six G3 files>` — passed.

The probe covers final-pass labelling, three ulp-boundary witnesses, the alternating-control-point sampling counterexample, gap-free span coverage, active-control-point hull containment, repeated-knot fail-closed behavior, admission-reason mapping completeness, unknown-reason atomicity and recovery, legacy sampled-mode compatibility, pump two-commit behavior, and documentation alignment.

The delegated turn ended after writing only `probe.py`. Main-session verification found and repaired two defects in that probe: its encoder fixtures used an invalid integer `start_time`, and its second pump frame recreated the encoder at sequence 1. The repaired probe uses the protocol time object and a single monotonically advancing encoder. It also expects the public admission path to reject a repeated-knot payload at the bridge, while the direct certificate path separately proves the `non_monotone_knots` fail-closed result.

## Source identity

- `Simulator/wksim_planning/ego_scene_admission.py`: `f88fa9c67b0410b8d7e65145008b21173959c03b6f0773c841cdb5e7e3ff7eca`
- `Simulator/wksim_runtime/planner_transport_pump.py`: `c9b541b4fb6112b09aacdb405838aa2f3c8935e144a21067f9c420f473279d27`
- `docs/plan/102-planner-transport-pump-contract.md`: `0b28fa3485589f218b8699beef8114eaa566745726c4533dba34f767ddc946ba`
- `docs/plan/102-trajectory-scene-admission-contract.md`: `083557fa419cbf8fab1b3c3f00a6bf0963716226f8c4f04282d49f3428c6ae05`
- `validation/test_ego_scene_admission.py`: `a41b5bce887da374877c09e6fc7922cafeacb3d55c6f1bb1d4f969f445dc00b2`
- `validation/test_planner_transport_pump.py`: `9f5be8631e83552ab6e8a2e995bfb6ead6c3d8cb9d9807b1b389c34af422e1a7`

The stable evidence-file hashes are recorded in `SHA256SUMS`.
