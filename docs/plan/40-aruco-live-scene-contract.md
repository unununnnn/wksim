# #103 · ArUco UE live scene candidate contract

Status: NOT ACQUIRED / NOT CALIBRATED. Frozen before any new rendering, 2026-09-09.
Scope: #103 / `40-real-scene`; parent #40 remains subject to #30, #32 and #6.
This contract is a reviewable candidate, not evidence of a created scene.

## Scene and budgets

- Dictionary `DICT_6X6_250`, ID 23, one black border cell. Black outer square side
  50 cm; 8 by 8 cells, each 6.25 cm; white margin one cell on every side,
  total board 62.5 cm. Generate bits with the pinned OpenCV dictionary, archive
  the bit matrix and its hash. Generated marker artwork is a material input,
  never a substitute for captured RGB.
- Board front is the UE YZ plane facing -X. Texture top is +Z, right is +Y;
  neither mirrored nor rotated. Proposed new assets use `M_ArUco23`,
  `T_ArUco23_D` and `L_ArUcoCalibration` under an isolated candidate's
  `/Game/Wksim/ArUco/`. Runtime geometry can reuse Engine Cube read-only.
  No collision, no simulation and no impact on the authoritative vehicle model.
- Camera: 640x480, horizontal FOV 90 degrees; K=[320,0,320;0,320,240;0,0,1],
  five zero distortion coefficients. Mount UE [30,20,10] cm, XYZW [0,0,0,1].
  Optical x=UE Y, y=-UE Z, z=UE X; pixel centers index+0.5.
- Initial reference vehicle pose [0,0,0] cm and identity rotation places the
  board center at [230,32,6] cm: optical target [0.12,0.04,2] m.
  During a real run use actual vehicle/camera transforms, not this assumed pose.
  Archive actual board bounds, all four black outer corners, camera transform,
  material parameters and resource identities for each admitted capture.
- Relative to the run's declared first step, hold target through 1 s; move
  world +Y at 0.25 m/s for 1–2 s; hold thereafter through 5 s. From 2–3 s
  an opaque occluder blocks the full target. It lies 25 cm toward the camera
  from the board front, sized 100x100 cm in YZ; actual projections must prove
  complete occlusion. Restore at 3 s. Updates occur on authoritative 1 ms
  steps before capture; never animate using renderer wall time.
- Capture interval 100 authority steps; target age at most 300 steps inclusive;
  max distance 8 m, max world speed 2 m/s, max jump 0.5 m, reprojection RMS
  at most 1 px. Translation error per axis at most 0.035 m; speed diagnostic
  per axis at most 0.12 m/s, evaluated only on consecutive fresh motion frames.
  These are pre-run candidate gates matching the existing consumer fixture
  values; they are not claimed to have passed real rendering.
- Unlit black/white appearance, opaque RGBA; no motion blur, temporal AA,
  distortion blendables or uncontrolled scene postprocessing. Independently
  projected black square corners must agree within 2 pixels per axis.
  Require at least five valid appearance, five movement, five fully occluded
  and five recovery frames; full occlusion must clear the target immediately.
  First recovery velocity must be null. Insufficient samples fail the run.
  Bound the attempt to 120 wall seconds; timeout produces failed evidence.

## Acquisition and independent audit

Bind run/instance/epoch/generation/stream from the authority/View before receiving
frames. Retain original `wksim.rgb.v2` JSON, PNG, ready notification and scene
transform readback for each capture; use existing Reader then Consumer unchanged.
For truth, transform independently measured board corners into the actual
camera frame and project with K, without solvePnP or estimated target pose.
Compare consumer optical/body/world translations against that independent truth.
Record rejected/missing frames and reasons, effective age and count by phase.
Consumer's low reprojection residual alone cannot prove physical side length.
Changed epoch/stream invalidates the old binding; stale or duplicate data must
never be relabelled as fresh. A real UE ground scene would prove rendering and
calibration only; #104 owns the remaining real dual-stack tracking integration.

## Resolved resources and concrete implementation gap

Read-only resource inventory and SHA256 are in
`validation/40-aruco-live-scene/inspection.json`. The project-owned archived
UrbanBlock and material inputs reside under `work/dependencies/ue55/`;
the current candidate is `E:/ue5.5/build/wksim-native-hex-20260909-01`.
The old plugin mount name is documented in `docs/project-isolation.md` and
does not transfer asset ownership to a sibling checkout. Vendor/engine assets
remain local and read-only.

The connected editor query returned `Unreal Editor is unavailable; open the
configured project and retry the tool.` This is a connection failure, not proof
that installed UE cannot run. The installed command-line editor exists.

`WksimRgbFixture.cpp::Configure` accepts only cases 0..3 and constructs three
uniform-color cubes, with no marker or step-based motion interface.
`WksimRgbSensor.h` exposes Configure/RequestCapture/Poll only as native methods,
without UFUNCTION Python reflection. `WksimVisualGameMode.cpp::TickRgb` requires
two current JointVehicles on JointStep; a Hex-only launch does not meet that
predicate. No claimed Hex RGB integration follows from the Hex display contract.

The scoped next implementation is a new native ArUco scene component plus the
GameMode hook applying its motion immediately before RequestCapture, an actual
scene manifest readback, and a fresh isolated candidate build. Those production
source/build locations are outside this ticket's explicit two write locations.
A separate Python-only evidence project could demonstrate UE rendering, but
would still need its acquisition identity/time/calibration integration verified;
it cannot silently replace this native Reader/Consumer requirement.

No production source, binary, existing asset, AGENTS.md or progression guide was
modified. #103 must remain OPEN / needs-triage until that implementation scope is
resolved and actual acquisition plus independent calibration pass. No runnable
scene-creation command is claimed here. The implemented inspection command is:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File validation/40-aruco-live-scene/inspect.ps1
```

The inspector refuses to overwrite existing evidence. It hashes local resources;
it does not launch a scene. Preserve this attempt when implementing a later run.
