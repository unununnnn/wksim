# #103 / 40-real-scene — incomplete, needs-triage

2026-09-09. The scene was NOT created, no true UE RGB was acquired, and
calibration is NOT verified. The first completion checkbox remains unmet.

Delivered `docs/plan/40-aruco-live-scene-contract.md` and this evidence directory:
candidate dictionary/ID/dimensions, camera, motion/occlusion sequence, independent
truth audit requirements, pre-run budgets, resource ownership and source gap.
The UE modeling/asset skill informed dimensions, prefixes and the requirement
to verify actual saved assets and rendered results; no asset was saved here.

Exact executed commands (repository cwd):

```powershell
gh issue view 103 --repo unununnnn/wksim --json title,body,state,labels
gh issue view 40 --repo unununnnn/wksim --json body
powershell -NoProfile -ExecutionPolicy Bypass -File validation/40-aruco-live-scene/inspect.ps1
work/dependencies/aruco-python/Scripts/python.exe -B -m unittest validation.test_aruco_consumer -v
```

Inspection exit 0: 30 resource identities, archived inputs 12/12 SHA256 matches,
zero running UnrealEditor processes. See `inspection.json` for exact paths,
bytes, hashes, UTC, branch and starting HEAD. Connected editor query failed;
raw response retained in `editor-query.json`. Installed command-line UE exists;
no claim that it cannot launch. No renderer was launched by this attempt.

Consumer tests exit 0: 12 tests passed, zero skipped, 0.508 seconds. Raw output
in `consumer-tests.log`; these use synthetic images and establish only existing
offline behavior, not scene acceptance.

Concrete gap: current fixture only generates three uniform-color cubes;
native RGB methods are not Python reflected; GameMode TickRgb requires two
same-step JointVehicles. The existing Hex display alone cannot drive that
capture gate. Actual ArUco geometry/motion and same-step manifest integration
need a native scene component and GameMode hook, followed by a new candidate
build. Those source/build locations are outside #103's explicit write scope.
The contract identifies this proposed extension for review; no hidden scope
change, new flight or modified physical budget was made.

Unverified: actual marker material/orientation/size, real RGB, appearance and
occlusion samples, calibration, authority-linked motion, live Reader/Consumer
delivery, and dual-stack tracking. No PID/FC/model/ROS/UE process was created;
there is no owned process to clean up. Parent #40 remains open.

Model metadata: user specified gpt-6-astra/low. This session exposes no independently
verifiable exact model ID/reasoning setting; cannot certify the requested actual
combination. No subagent was dispatched.

Only the contract and this evidence directory are to be committed. Existing
AGENTS.md and progression-guide changes were preserved and excluded. Keep #103
OPEN, remove ready-for-agent, add needs-triage.
