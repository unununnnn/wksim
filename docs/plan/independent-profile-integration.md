# Independent profile admission integration

`Simulator/wksim_runtime/independent_profile.py` admits the explicit
`runtime_profile="independent_quad_dds_v1"` selector for one quad-X experiment.
It requires `session_v1`, native DDS, and only `native_position_mission`.
Ground control restart remains rejected for this candidate until separately proven.
The two console mission examples now select this profile and the passed resource roots.
Their previous bytes are retained in `*-mission-retained-baseline.json`; historical
flight results and the original default preflight path remain unchanged.

`select_config(config)` validates the ordinary independent contract after removing
the new selector, compares exact roots against `joint-profiles.json`, and returns
`(normalized_config, joint_descriptor)`. It fills an omitted model library with the
pinned path. It does not inspect firmware resources or start processes. AP retains
the required pinned `px4_root` configuration field without inspecting that peer's
firmware tree.

`check_profile(config)` returns `ok`, `reasons`, `children_created=0`, normalized
`config`, `setup_files`, capabilities and the old runtime identity names:
`firmware`, `firmware_commit`, `agent`, `model_library`, and `model_build`.
Candidate `flown` is true only after unchanged current resource checks and exact
historical independent-flight evidence binding both pass. `flight_provenance`
identifies the original result/audit hashes and explicitly reports
`current_admission_code_flown=false`. This is three-waypoint build provenance,
not a claim that edited admission code was flown.

The shared `joint_profile.check_resources(p, stacks=...)` checks the unchanged
catalog descriptor and permits only the original pair or one exact stack tuple.
It reads selected firmware plus Control manifests and checks their source/build
identities using the original helpers. All joint evidence hashes, raw evidence,
model identities, shared message packages and overlays remain checked. Only the
selected firmware executable and DDS agent are required. Original `check_profile`
still validates both configurations and invokes the default two-stack check.

Main integration must route the explicit selector from preflight, retain socket
ownership/mode and telemetry decoder checks, source the report's setup files, and
compare runtime firmware against the admitted firmware identity. Source identity
records should include this module. Both selected builds completed the real cases
`validation/independent-mission-px4-20260907-run1` and
`validation/independent-mission-ap-20260907-run1`. Admission and mocked unit reports
are not flight evidence.

Run the bounded contract/regression checks from the project root:

```sh
python3 -m unittest validation.test_joint_profile validation.test_independent_profile validation.test_independent_profile_audit
```

These checks start no FC, UE, MATLAB, compiler or vendor program. They cover strict
selector/root/capability rejection, report compatibility, unchanged rejection
propagation, and exclusion of the unselected firmware manifest. Real source walks
and flights belong to the integration validation.

## Retained evidence and 2026-09-07 promotion

`validation/independent-admission-20260907/flight-audit.json` verifies each original
flight: three independent physical dwell windows, eight public requests, six
accepted native ACKs, safe landing and retirement. Position streaming has public
acceptance and physical completion; six ACKs do not mean per-waypoint native ACKs.
Process maps are contemporaneous identity snapshots, not a whole-flight loader trace.

`flown-source/manifest.json` binds 21 original runtime/driver files per flight to
original report/result hashes. Their exact bytes were copied and verified before
admission edits. The audit's explicit `--source-archive` mode validates those bytes;
its default current-checkout mode continues to reject changed flown dependencies.
The evidence catalog pins that audit, all audited raw inputs, and retained bytes.
Current selected firmware/model/agent/messages must equal the flown identities;
Control is bound by the exact manifest already checked by the shared resource
checker. No source/build or overlay check is bypassed.

Read-only WSL Ubuntu tests passed: 15 tests, including mutations of original public
envelopes, physical truth, FC image maps and selected firmware identity in temporary
copies. Windows has an existing joint-test symlink privilege limitation; the same
suite passed under WSL. These tests start no flight, UE, MATLAB or compiler.
No G1, G5, Full, loss-recovery, hardware or dynamics-equivalence closure is claimed.
