# #29/#102 planner scene binding contract

Status: offline geometry slice only. This document records the boundary for
the next #29/#102 increment. It does not close either issue and does not claim
UE, SITL, ROS, a planner, or physical force response.

## Authority and identity

`Simulator/wksim_planning/scene_profile.py` is the sole geometry source for
`ego-single-box-v1`. The new
`Simulator/wksim_runtime/planner_scene_binding.py` derives the collision AABB
and the ordered voxel-centre point cloud from that profile object. It does not
copy obstacle, map, voxel, vehicle, or clearance constants.

The binding manifest is `wksim.planner-scene-binding.v1`. Its hash is computed
from hash-free canonical JSON using UTF-8, ASCII JSON escaping, sorted keys,
compact separators, and `allow_nan=false`. The generated identity is:

| Field | Value |
| --- | --- |
| `scene_id` | `ego-single-box-v1` |
| `scene_hash` | `40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba` |
| `profile_hash` | `49da4cccaf3c172c510daa3cc3bd0ddad521669c4d64f3c8bc1a7fe71d9730f7` |
| `collision_hash` | `08b88651775ae2181e5082f124d16c6a434597703fdf2ff08bfc0bd59205c07c` |
| `voxel_hash` | `3602530733cf10fd0960212dc413b157e56e662d330b4b314a71f4c21abae638` |
| `point_cloud_hash` | `d14d6311a45e3e7d1c323afdb67205510c5370eed2959d23bff70cd1ac04f2ad` |
| point count | `11000` |
| frame and units | `map` / `ENU` / metres |
| query version | `planner-aabb-point-contact-v1` |
| physics authority | `WSL` |

`point_cloud_hash` covers the ordered centre coordinates plus the profile's
voxel order and centre convention. `voxel_hash` remains the hash already
frozen by the profile. Both are retained so an evidence writer can distinguish
the index set from the emitted point coordinates.

Construction accepts only an exact `SceneProfile` instance whose canonical
field content recomputes the committed profile, collision, voxel, point-cloud,
and scene hashes above. The binding stores primitive profile/AABB/hash/identity
snapshots at construction; later reassignment, profile method drift, or module
constant changes cannot alter validation or query output. Manifest properties
return deep copies and point-cloud properties return immutable tuples.

This is a consistency and misuse boundary for the ordinary in-process paths
covered by the tests: instance storage writes, normal class or instance
assignment/deletion, subclassing, and post-capture profile/module monkeypatches.
It is not a security boundary against a caller that already has arbitrary
Python reflection or code-execution authority in the same process. Runtime
integrity is established by the surrounding evidence/release checks pinning
the profile and binding source hashes, together with a controlled process
boundary; this module does not add a second reflection layer for that case.

The existing #29 fixture remains independent:

```text
scene_id   = static-plane-box-v1
scene_hash = 60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514
```

The binding rejects either legacy identity. The generated-model probe hash
`4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300` is also
not a UE display identity and is not substituted here.

## Query boundary

The pure query accepts an exact identity envelope containing `scene_id`, all
four geometry hashes, `query_version`, a lowercase 32-character `epoch`, a
non-negative integer `step`, `sim_time_ns == step * 1_000_000`, a non-empty
`body_id`, the exact planner `geometry_id`, a finite ENU point, and the fixed
binding source identity. Unknown fields, wrong path/source identity, wrong
hash, frame, unit, epoch, time, geometry, or non-finite value fail closed.

The result is point-versus-AABB contact geometry with an epoch and one-step
validity interval. Boundary points are accepted as contact and have zero
penetration. A point outside the obstacle is `no_contact`. The profile's
ground and ceiling values remain profile metadata; this slice does not turn
the obstacle into a terrain heightfield.

The manifest declares `physics_authority: WSL`, while `forces`, `impulses`,
and `terrain_response` are all false. No force, impulse, damping, state
correction, terrain feedback, or model step is produced.

## Verification boundary

`validation/test_planner_scene_binding.py` verifies canonical bytes on Windows
and WSL, profile-derived AABB and 11000-point ordering, fixed hashes, boundary
and outside queries, regular-file path rejection including file and parent
symlink/resolve aliases, duplicate-JSON-key rejection, non-finite rejection,
identity mismatch, the no-instance-state and ordinary mutation guards,
subclass/method spoofing, and the full epoch/step/time/body/geometry/query-
version boundary. The tests document the supported consistency boundary; they
do not claim to defend against arbitrary reflection or code execution inside
the Python process.

These are pure Python tests only. They do not start `JointPhysics`, a model
worker, ROS/DDS, SITL, UE, or a flight. Runtime observer integration requires
an accepted contact/solver contract first; swapping this AABB into the current
terrain-height API would incorrectly treat a vertical obstacle as terrain
support.
