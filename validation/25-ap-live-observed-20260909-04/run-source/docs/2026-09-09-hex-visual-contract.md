# Experimental Hex visual contract — frozen before UE execution

This optional source-template display is not real-aircraft calibration. It does
not assign a new engine `model3DType`: the native model's value 3 does not select
the UE renderer. The default four-rotor and joint display protocols remain intact.
No `.uasset` is created or overwritten, and the production binary manifest is not
changed. Runtime components reuse Engine BasicShapes and existing P450 materials
and CW/CCW rotor meshes read-only.

## Geometry and pose

Launch with `-WksimConfiguration=hex-X -WksimVehicle=1`, a caller-selected
`-WksimRunId`, lowercase 32-hex `-WksimInstance`, and
`-WksimModelIdentity=sha256:<64 lowercase hex>`. The model identity is verified by
the launcher from the selected configuration; it is never learned from state.
Every cold physical reset requires a new run ID and new UE instance.

The Actor is exactly `(100*N,100*E,-100*D)` cm with quaternion XYZW
`(-qx,-qy,qz,qw)` from NED/FRD WXYZ. All geometry has a common local +10 cm Z
offset solely for ground clearance; it never alters the Actor pose. A cylinder
body, six cube arms and four landing legs form the actual hex structure.

| Motor order | FRD/UE XY angle degrees | Radius cm | Spin / UE yaw sign |
|---|---:|---:|---:|
| M1 | 90 | 22.5 | +1 CW |
| M2 | 270 | 22.5 | -1 CCW |
| M3 | 330 | 22.5 | +1 CW |
| M4 | 150 | 22.5 | -1 CCW |
| M5 | 30 | 22.5 | -1 CCW |
| M6 | 210 | 22.5 | +1 CW |

Rotor origins are `(22.5*cos(angle),22.5*sin(angle),10)` cm. Each actual loaded
rotor mesh receives a uniform scale `18 / (2 * max(localBounds.extent.X,
localBounds.extent.Y))`, giving an 18 cm maximum planar diameter; adjacent motor
centres are 22.5 cm apart. The readback reports actual mesh bounds and scale so
the diameter and clearance can be independently checked.

## Strict protocol version 4

Only hex launches accept `kind=hex_state`. The exact 25-field packet contains:
`version`, `kind`, `run_id`, `instance_id`, `model_identity`, `vehicle_id` (1),
`sequence`, `step`, `sim_time_ns`, `sim_time_s`, `source_monotonic_s`,
`source_age_s`, `display_clock` (`windows_utc_bound`), `display_wall_time_s`,
`transport_age_bound_s`, `position_frame` (`NED`), `position_unit` (`m`),
`quaternion_order` (`WXYZ`), `body_frame` (`FRD`), `rotor_unit` (`rpm`),
`configuration` (`hex-X`), `rotor_order` (`M1` through `M6`), `position_ned_m`,
`quaternion_wxyz`, and `rotor_rpm` (six entries).

All numeric values must be JSON numbers, finite and within bounds; booleans and
numeric strings are rejected. Sequence and step strictly increase, simulation
time equals step * 1 ms (1e-8 s tolerance), quaternion squared norm differs from
1 by at most 1e-5, positions are at most 1e6 m in absolute value and RPM is in
[0,100000]. Source monotonic time strictly increases. Integer fields are exactly
representable (<= 2^53-1), and nanosecond time is exactly step * 1,000,000.
The complete datagram is validated before any pose, RPM, phase or acceptance
guard changes. Unknown fields, foreign identities, wrong layouts, nonfinite
numbers, replay, old steps, stale frames and excessive future wall time reject.

For the first accepted frame every unwrapped phase is zero. On subsequent
accepts, phase_i += current_RPM_i * 6 * (current_step - previous_step)/1000 *
spin_i degrees, and component relative yaw is that phase modulo 360. This is
explicit right-endpoint visual integration over accepted source samples, not
an assertion that it integrates all 1 ms physical RPM samples. Tick never advances
hex phases. Long renderer stalls cannot create phase from wall time.

ACK `hex_actor` reports the bound identity, accepted sequence/step/time,
previous accepted step, actual Actor pose, all six actual local/world origins,
RPM, spin signs, component yaws, unwrapped phases, actual local mesh bounds and
uniform component scales. A six-field `hex_actor_query` (version, kind, run_id,
instance_id, model_identity, request_sequence) returns `hex_actor_snapshot` with
request_sequence and the same actual state, without refreshing any clock or
changing any state. ACK is game-thread component readback, not proof of rendering.

## Freshness and evidence

The WSL reader opens only the specified live raw trace, remembers its inode,
starts at EOF, and consumes only subsequently appended complete records. A new
file must present its `start` binding before steps; an existing file's initial
start record is read only to verify the explicit run/model binding, never as
state. Truncation, replacement, binding mismatch and a terminal `end` record
retire the stream. Raw output120 indices are physical native ABI values:
time [2], NED [6:9], WXYZ [12:16], six RPM [16:22]. Linux
`observed_monotonic_ns` supplies source age on the same OS clock.

Windows makes one outstanding stdin pull at a time. The envelope includes the
Linux relay monotonic timestamp. Age bound is Linux source age + the full
Windows monotonic request roundtrip; display_wall_time_s = Windows UTC now -
age bound. Age must remain <= 0.75 s at both bridge and receiver. The receiver
also rejects display timestamps > 0.25 s in the future. Pipe backlog is therefore
charged to transport age, never relabelled fresh. Records are never resent as
new state; ended logs cannot become LIVE. Each received ACK is recorded with
its exact transmitted packet and numerical comparison, separately from rendered
screenshots and from physics/control evidence.

## Predeclared checks

Pure checks cover six geometry positions/spins, independent 1 ms ABI mapping,
identity/array/type/time/freshness rejection, replay and phase nonmutation,
partial tails, old-file exclusion, file replacement/truncation and termination.
Real UE acceptance requires a separate authorized candidate build/run: Actor
position error <= 2e-4 cm, quaternion L2 <= 1e-6 (sign invariant), rotor local origin
error <= 1e-5 cm and world origin error <= 3e-4 cm, RPM/spin exact, phase error <= 1e-6 degrees and yaw modulo
error <= 1e-4 degrees. Both real flight stacks require their own live run and
capture evidence. No test or build alone is described as flight/render proof.

Before the first UE execution, the main review aligned the position budget with
the existing UE5.5 SceneComponent update-suppression bound of 1e-4 cm per axis
(3D norm below 2e-4 cm). World rotor origins additionally propagate the bounded
Actor quaternion error over their approximately 25 cm lever arm. These are
engine-derived bounds already used by the original visual validation, not fits
to Hex observations. The earlier proposed 1e-5 cm Actor/world budget was never
executed as a Hex visual acceptance test.
