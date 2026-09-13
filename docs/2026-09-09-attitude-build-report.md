# #34 isolated native and message build

2026-09-09. Build and offline codec checks passed. This is not runtime admission, a loaded-binary claim, a native guard test, or flight acceptance. No controller source/profile, installed baseline, SITL, ROS node, model, or GCS was changed or started.

The main agent verified this delegation session `01a083e5-fd81-79f2-8747-24b440c1b363` as `gpt-6-astra/low` before RELEASE. No nested agents were used. The ponytail skill guided reuse of existing preparation and source snapshot helpers.

## Build identity

- Native candidate: `/root/wksim-ap-attitude-hejigg76`; build shell PID 588, completed with exit 0.
- New messages overlay: `/root/wksim-ap-attitude-msgs-qOmnF9fT`, separate source/build/install/log directories.
- Source manifest SHA256: `e6760402ba7e1e7bd86ef3777ecd44d98c711748b22dd1be7a5a1262cd8f52ef`.
- Final `attitude-build.json` SHA256: `bd8257094e6ab21034e7e6982835d833441d22582c0324b22fe8aa13fa0a4fe4`.
- Native `build/sitl/bin/arducopter` SHA256: `c1a38947d65aafa7a9051a850df46d9fd67c8f0723833bf3508245c81ab7b1c0`.

`tools/build-ap-attitude-candidate.sh` ran full sealed mixed-source/binary validation through the existing preparation helper, copied to the new candidate, and applied the staged 0006 patch. No patch corrections were needed. Configure used `--board sitl --enable-DDS --out <candidate>/build --extra-hwdef <candidate>/attitude-extra.hwdef`; the generated `build/sitl/hwdef.h` confirms `AP_DDS_WKSIM_ATTITUDE_ENABLED 1`. DDS generator PATH came from `/root/wksim-dds-VxM6Ni/src/Micro-XRCE-DDS-Gen/scripts`.

`waf copter -j4` completed successfully in 1m52.926s. Humble `colcon` built the copied `Tools/ros2/ardupilot_msgs` package in 7.47s. Configure/build/message logs and explicit zero-exit sentinels remain in the candidate. There were no failed build or codec attempts. All compilation processes finished before handoff.

## Offline verification

`tools/verify_ap_attitude_candidate.py` checked the complete post-build source snapshot against the prepared source manifest, plus patch and extra-hwdef hashes. It imported `ardupilot_msgs` from the new overlay and ran this actual codec path:

1. ROS `WksimAttitudeTarget` serialization with stamp `(123,456789)`, frame `map`, quaternion XYZW `(0.5,-0.5,0.5,0.5)`, and finite normalized thrust `0.375`.
2. A compiled C program using the candidate's generated `WksimAttitudeTarget`, Header, Time, Quaternion serializers and its Micro-CDR sources decoded and asserted every field, then serialized the message again.
3. ROS deserialization of the native bytes matched the original message exactly. Existing `WksimState` also passed a ROS serialization roundtrip.

The codec executable, source, compiler log, and both CDR byte streams remain under `<candidate>/codec`. The final manifest seals their hashes, native binary/logs/patch/hwdef/build wrapper, all generated DDS files, all message-overlay files, and verifier identity. This validates finite-value wire compatibility, not native handler rejection behavior for malformed input.

A final independent call to `prepare_ap_attitude_candidate.baseline()` passed after verification: sealed `/root/wksim-ap-mixed-fhuf05l9` source and binary were unchanged. The original messages workspace was only used for its installed generator.

## Reproduction

Run the build wrapper in WSL Ubuntu-22.04 as root. It prints the newly prepared candidate and overlay paths. Then source `/opt/ros/humble/setup.bash` and the new overlay's `install/local_setup.bash`, and run `python3 -B tools/verify_ap_attitude_candidate.py <candidate>` from this repository. Verification intentionally creates a fresh `codec` directory and will not overwrite an earlier attempt.

Remaining work belongs to the main task: control patch review/application in its own overlay, native guard/runtime tests, exact loaded identity, regression checks, calibration, and bounded flight acceptance. No issue or commit operations were performed here.
