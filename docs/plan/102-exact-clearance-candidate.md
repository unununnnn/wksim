# #102 exact-clearance candidate certificate (G3-EXACT-1)

Status: **candidate, not wired, not the default.** This note specifies
`Simulator/wksim_planning/ego_exact_clearance.py`, which is verified by
`validation/test_ego_exact_clearance.py`. Nothing imports it from the committed
runtime: `Simulator/wksim_planning/ego_scene_admission.py`,
`Simulator/wksim_runtime/planner_transport_pump.py`, the adapter and the session
are unchanged and keep deciding admission. **Promoting this predicate to the
default strict gate is an explicit owner decision** and is *not* taken here.

This document is a candidate contract, not an acceptance of #102, #39 or G3.

## Why the candidate exists

The independent audit `validation/coordination/deepseek-g3-strict-gate-20260914-01/`
measured the committed strict predicate (per-interval control-window AABB vs the
obstacle AABB) on one exactly fixed geometric curve and on the committed
recorded planner payload:

| measurement (audited, unchanged here) | value |
| --- | --- |
| same curve, maximum representation deviation | `<= 2.2e-15 m` |
| committed verdict at 9 / 13 / 21 control points | reject / reject / reject |
| committed verdict at 33 / 65 control points | admit / admit |
| same curve, true net clearance at every density | `0.8696328198877233 m` (2.90x required) |
| committed certificate, recorded payload | net `0.37725020658857944 m`, gap `0.7272502065885794 m` |
| recorded payload, true dense net clearance | `0.9971917383329542 m` |
| phantom slack (true - certified), worst measured | `1.2196328193797388 m` = 4.07x required |
| minimum `required_clearance` that would admit the 9/13-control witnesses | `-0.35 / -0.15 m` (negative) |

The committed predicate is therefore a function of the control-point
representation and cannot be repaired by any positive threshold change.

## What the candidate certifies

For every active knot interval `[u_j, u_{j+1}]` of the exact evaluation domain
`[u_p, u_{m-p}]`:

```
obstacle_lower_j  <=  min_{t in [u_j,u_{j+1}]} dist(gamma(t), obstacle_AABB)  <=  obstacle_upper_j
inset_lower_j     <=  min_{t in [u_j,u_{j+1}]} g(gamma(t))                     <=  inset_upper_j
```

with `g(x) = min_i min(x_i - low_i, high_i - x_i)` the smallest signed distance to
a map face. `gamma` is the continuous cubic curve; **no chord, segment or time
grid is used anywhere**.

Soundness (Lipschitz subdivision, not sampling):

1. Per span, a certified speed bound `V` comes from the B-spline derivative
   identity `Q_i = p (P_{i+1} - P_i) / (U_{i+p+1} - U_{i+1})` with the derivative's
   knot vector `U[1:-1]`. The derivative has degree `p-1`, so on a span it is a
   convex combination of its active control points; the implementation takes the
   largest norm over a **superset** of that window, which can only loosen the
   bound. A test (`SpeedBoundTests`) checks the bound against a dense
   absolute-parameter `position.derivative().evaluate(u)` evaluation on the
   fixed critic set and on random geometry.
2. `dist(., B)` is 1-Lipschitz in the Euclidean norm and `g` is 1-Lipschitz in
   the L-infinity norm. For a sub-interval `[c, d]` with midpoint `m`:
   `min f >= f(m) - V (d-c)/2` (certified lower) and `min f <= f(m)` (valid
   upper).    The midpoint is one exact evaluation at the **absolute knot
   coordinate** `u` via `position.evaluate(u)`, not curve-time `position_at`.
   The constructed float `u` may sit up to `ulp(u)/2` away from the exact
   midpoint. That parameter displacement is charged as `V * ulp(u)/2` and must
   stay inside the declared `FLOAT_GUARD_M` envelope. Fail-closed **before**
   `evaluate()`, with `evaluations = 0`, empty `spans` and `bounds_scope = null`:

   1. any active span whose required interior midpoint is not a representable
      strict-interior float -- `rejected` / `certificate_structure_invalid`;
   2. else any span whose speed-scaled ULP exceeds `FLOAT_GUARD_M` --
      `indeterminate` / `parameter_roundoff_exceeds_envelope`;
   3. else any span whose requested n-partition is unrepresentable, outside
      the open interval, or non-unique -- `rejected` /
      `certificate_structure_invalid`.

   (1) beats (2) beats (3). A `SpanBracket` is a certified bracket and is
   emitted only after a valid interior sample exists; unrepresentable
   partitions never fabricate per-span bounds or `conclusive` pointers.
   Ordinary knot translations that stay inside the envelope (`+1` / `+4`
   seconds on map-scale EGO knots) keep the same verdict; **arbitrary
   translation invariance outside the envelope is not claimed**.
3. A uniform partition with `n = ceil(V (b-a) / (2 (t - 2 eps)))` sub-intervals
   gives a span bracket of width `<= t` when the envelope holds, where
   `eps = FLOAT_GUARD_M = 1e-9 m` is the declared absolute float guard (added to
   both corners) and the parameter-roundoff envelope. When
   `bounds_scope == "continuous_curve"`, the global bracket is the min of every
   span bound and is no wider than the span that produces it. If only a prefix
   of the spans was evaluated, the four global fields are `null` and
   `bounds_scope == "partial_evaluated_spans"`; per-span evidence is retained.

Because closing the bracket needs only the width, **not the density**, the
decision is a function of the curve: the same geometry in any representation
produces the same bracket and the same verdict.

## Decision semantics (fail closed, declared band)

Clearances are net of `vehicle_radius` (the committed margin convention), so
`required_clearance` (`0.30 m`) is the single threshold for obstacle and map
alike. `status` is one of:

| status | condition | `admitted` |
| --- | --- | --- |
| `admitted` | every span closed and every span's **lower** bound `>= required` | `True` |
| `rejected` | some span's **upper** bound `< required`, the spline structure is unusable, or a requested midpoint / interior partition is not a representable interior float | `False` |
| `indeterminate` | no conclusive rejection, but a bracket did not close (`work_cap_exhausted`), the true minimum lies in the band `(required - t, required + t)` (`clearance_within_tolerance_band`), or a span's speed-scaled ULP exceeds `FLOAT_GUARD_M` (`parameter_roundoff_exceeds_envelope`) | `False` |

`t` is the declared tolerance (default `1e-3 m`, maximum `0.1 m`, must exceed
`4 * FLOAT_GUARD_M`). `admitted` is `True` only for `status == "admitted"`, so an
unclosed or banded certificate can never be mistaken for a pass. Measured band
behaviour on a constant-clearance line parallel to the obstacle face
(`true_net = required + delta`, `t = 1e-3`):

| `delta` | `-3t` | `-0.5t` | `0` | `+0.5t` | `+3t` |
| --- | --- | --- | --- | --- | --- |
| status | rejected | rejected | indeterminate | indeterminate | admitted |
| reason | `obstacle_clearance_below_required` | same | `clearance_within_tolerance_band` | same | `-` |

Consequently: a curve whose true clearance is `>= required + t` is admitted in
*every* representation; one below `required - t` is rejected in every
representation; the only undecided region is the declared `2t`-wide band, where
the certificate fails closed.

## Evidence surface

`certify_exact_clearance(spline, *, binding=EGO_SINGLE_BOX_BINDING, tolerance_m=1e-3,
max_nodes_per_span=65536, max_evaluations=2097152)` returns an immutable
`ExactClearanceCertificate` (`.to_dict()` is JSON-serializable) carrying:
`candidate_only=True`, `status`, `admitted`, `evidence_kind`
(`lipschitz_bracket_certified`), `reason`, `tolerance_m`, `float_guard_m`,
`tolerance_met`, the four certified global bounds (or `null` when
`bounds_scope` is not `continuous_curve`), `bounds_scope`
(`continuous_curve` | `partial_evaluated_spans` | `null`), `binding_object`
(`obstacle` | `map_inset`) with `binding_span_index` and its `u` interval, the
committed scene/profile identity, `span_count`, `evaluated_span_count`, `nodes`,
`evaluations`, both caps, the per-span `SpanBracket` list, and `non_claims`.

`ExactClearanceError` (reason-coded) is raised **only** for caller/protocol
errors: wrong spline/binding type, non-positive/non-finite/oversized tolerance,
or an invalid cap. A geometric shortfall and a structurally unusable spline come
back as a `rejected`/`indeterminate` certificate so an exception path can never
look like an admission. Finite inputs whose derivative norms, products, node
counts, slack, evaluations or distances overflow to a non-finite value are the
same: a fail-closed certificate, no exception, and no extra subdivision work.
Structural reasons: `certificate_structure_invalid`,
`non_monotone_knots`, `degenerate_domain` (defensive only -- with strictly
increasing knots `u_p < u_n` is unavoidable), `no_active_interval`.
Unrepresentable midpoints / collapsed interior partitions use
`certificate_structure_invalid` and never emit a `SpanBracket`. Speed-scaled
parameter ULP above `FLOAT_GUARD_M` on a span whose midpoint *is*
representable uses `parameter_roundoff_exceeds_envelope` and is
indeterminate. Reason priority when more than one pre-sample gate fires:
unrepresentable midpoint, then envelope, then unrepresentable n-partition.
Private-state integers too large to convert to float (`10**400` and similar)
are the same fail-closed certificate path, never an `OverflowError`.

## Measured results (this checkout, both platforms)

| measurement | value |
| --- | --- |
| fixed curve at 9/13/17/21/33/65 control points | **admitted at all six**; per-density obstacle lower bound in `[0.868633177, 0.868634061]`, upper in `[0.869632821, 0.869632907]`, width `<= 1e-3 m`; all six brackets contain the audited true clearance `0.8696328198877233` |
| exact Boehm refinement from 9 control points (9 -> 14 -> 24 -> 44 -> 84 -> 164 -> 324) | **admitted at every step**, curve deviation `<= 2e-15 m` (the audit's longer sequence to 1284 controls is in the audit receipt) |
| recorded payload | **admitted**, obstacle bracket `[0.996194387, 0.997191746] m`, width `9.9736e-4 m <= t` |
| recorded payload vs the committed certificate | `0.996194` (banded lower) vs `0.377250` committed net: `>= 0.61 m` tighter |
| recorded payload work | 30 spans, 6062 curve evaluations |
| alternating-control-point witness (true net ~0.20 m) | **rejected** (`obstacle_clearance_below_required`); every span is evaluated under the default caps so the global bounds are curve-wide |
| line through the box / on the surface / `required - 0.05` | **rejected** |
| map binding (`y = 5.34`) | admitted, `binding_object = map_inset` |
| map shortfall (`y = 5.36`) | rejected, reason `map_inset_below_margin` |
| `max_nodes_per_span = 1` on a safe curve | indeterminate, `work_cap_exhausted`, `admitted = False` |
| determinism | byte-identical `to_dict()` across repeated calls and fresh equal splines |
| knot-vector translation `+1/+4/+10 s` | same status, reason and net bounds as the unshifted curve (inside the envelope) |
| family-13 shifted `+1e6 s` | **admitted**; `0.5 V ulp(|u|)` stays inside `FLOAT_GUARD_M` |
| family-13 shifted `+1e7` / `+1e12` / `+1e15 s` | **indeterminate** (`parameter_roundoff_exceeds_envelope`), evaluations `0`, no spans |
| adjacent-float witness, starts `1` / `1000` / `1e6` / `1e15`, spacings `1/2/4/8` | **not admitted**; `evaluations = 0`, empty `spans`, `bounds_scope = null`, no binding. 1-ulp: `rejected` / `certificate_structure_invalid`. Wider spacing with a representable midpoint: `indeterminate` / `parameter_roundoff_exceeds_envelope` |
| corner-dip witness shifted `+1 s` | **rejected** (`obstacle_clearance_below_required`); never admitted |
| `±1e308` controls, interval `1e-8`/`1e-12`/`1e-16` | **rejected** (`certificate_structure_invalid`), no exception, evaluations `0` |
| private-state `10**400` knot or control | **rejected** (`certificate_structure_invalid`), no `OverflowError` |
| `max_evaluations = 10` on a safe curve | indeterminate, `work_cap_exhausted`, `bounds_scope = partial_evaluated_spans`, four global bounds `null`, per-span evidence retained |

R1/R2/R3 against the proposed criterion of the G3 audit (R1 representation
determinacy outside the `2t` band, R2 `delta = true - certified <= t`, R3
invariants preserved):

* **R1 -- met on the audited cases.** Six densities and six exact-refinement
  steps of one curve produce one verdict; the committed predicate does not. The
  guarantee is structural, not empirical: the span bracket has width `<= t` and
  contains the true minimum, so a curve with `true >= required + t` has
  `lower >= required` in every representation whose knot parameters stay
  inside the envelope and whose midpoints are representable interior floats;
  one with `true <= required - t` is never admitted (rejected when the
  partition is representable, otherwise fail-closed before sampling).
* **R2 -- met at the declared tolerance.** The reported bracket width is
  `<= t` (`1e-3 m`) whenever the status is `admitted`. An unclosed
  certificate is never admitted: if a certified upper bound already proves
  a clearance violation, the status is conclusive
  `rejected`; otherwise it is `indeterminate`. `tolerance_met` means
  every evaluated span closed to the declared resolution. It is not
  equivalent to `admitted` (a conclusive rejection or a banded outcome
  can still have `tolerance_met = True`; an unclosed rejection has
  `tolerance_met = False`).
* **R3 -- met by construction.** Soundness (only `lower >= required` admits, and
  `lower` is a certified lower bound), fail-closed structure handling, the
  committed reason vocabulary of the existing gate is *not* reused or changed
  (this is a separate module with its own reasons), the legacy sampled path and
  the committed gate are untouched, nothing is wired, and no identifier or wall
  clock is used.

## Measured limits and honest boundaries

* The bounds are **certified brackets at the declared tolerance, not an
  exact-real proof**. The reported gap between `*_lower` and `*_upper` is the
  declared resolution; `FLOAT_GUARD_M` is the declared absolute numerical
  envelope (bracket corners **and** speed-scaled parameter ULP). It is not a
  derived error bound, and it is not a claim of translation invariance at
  arbitrary `|u|`.
* Work scales with `sum_spans V_j h_j / (2t)`, i.e. with the *control-polygon*
  derivative bound, which is deliberately a superset bound and therefore loose
  where the curve momentarily slows. Measured: on the recorded payload the
  bound reaches ratio `1.00` against a dense `||gamma'||` evaluation (30 spans,
  6062 evaluations for a 10.8 s trajectory). The on-disk
  `alternating_witness()` (true net ~`0.20 m`, **unsafe**, rejected) still
  costs 60200 evaluations on a 1 s, 200-span curve: the certified
  control-polygon bound is `V = 120 m/s` against a true derivative
  supremum of `60.0 m/s` (ratio `2.00`). A resonant 1001-point grid
  (`u = 0, 0.001, ..., 1.0`) reports `57.6 m/s` (ratio `2.08`) only
  because it misses span midpoints; that figure is not the dense
  maximum and must not be presented as one. A cap hit is indeterminate
  and **fail-closed**, never a pass; the caps (65536 nodes/span, 2097152
  evaluations total) make the worst case bounded rather than hanging.
* The candidate certifies point-to-AABB and point-to-map-face clearance of the
  continuous curve. It is deliberately **not** the committed sampled/segment
  quantity: a chord between two curve points can pass closer to the obstacle than
  the curve, so the committed sampled gate and this certificate measure different
  objects and their numbers must not be compared as if they were the same test.
* The obstacle is exactly the committed vertical AABB for the whole duration; the
  vehicle extent behind `vehicle_radius` is assumed spherical; Terrain15D is
  never read.
* No dynamics, tracking error, controller lag, force, impulse, sensor, planner,
  socket, UE, SITL, ROS/DDS, flight-controller, native-build or flight-safety
  claim. No map->planner->public-control->flight evidence exists for this
  candidate, and none is implied by it.

## What promotion would require (owner decision, not taken here)

Promotion of the candidate into `ego_scene_admission.py` as the default strict
predicate would need, at minimum: (a) an explicit owner decision that the
committed gate's disclosed conservatism is to be replaced, (b) a compatibility
decision for the `continuous_clearance_unproven` reason/outcome vocabulary
(the pump maps reasons explicitly and raises on an unmapped one), (c) an update
of `docs/plan/102-trajectory-scene-admission-contract.md`, and (d) re-running the
committed suites plus the seal pins, since the seal hashes change. Until then the
candidate is evidence only.

## Verification

```
# Windows (Python 3.13.11)
python -m pytest validation/test_ego_exact_clearance.py -q
python -m unittest validation.test_ego_exact_clearance
python -m pytest validation/test_ego_scene_admission.py validation/test_planner_transport_pump.py validation/test_planner_transport_receiver.py -q

# Ubuntu-22.04 (Python 3.10.12, from the repository root)
python3 -m pytest validation/test_ego_exact_clearance.py -q
python3 -m unittest validation.test_ego_exact_clearance
python3 -m pytest validation/test_ego_scene_admission.py validation/test_planner_transport_pump.py validation/test_planner_transport_receiver.py -q
```

Machine-readable results, exact commands, per-file SHA-256 hashes and platform
tags for the original packet live in
`validation/coordination/deepseek-g3-exact-clearance-20260914-01/receipt.json`.
The P0/P1/P3 repair receipt is
`validation/coordination/cursor-g3-exact-clearance-repair-20260914-01/receipt.md`.
The third repair (unrepresentable midpoints fail closed with empty spans
before `evaluate()`, documented reason priority, removal of the numeric
speed-threshold exception) is
`validation/coordination/cursor-g3-exact-clearance-repair3-20260914-01/`.
This note remains a candidate contract: nothing is wired and promotion is still
an explicit owner decision, not taken here.
