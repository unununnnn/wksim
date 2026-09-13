# Current control/message candidate refresh

The final mixed-firmware trials use one current candidate triple:

- AP mixed: `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json`, SHA-256 `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c`.
- control: `/root/wksim-joint-control-rWolCy/build.json`, SHA-256 `a6a17b42f92cf6df4b92fe36b6e1e65f6e4e42f684daac4113091591a1802346`.
- ROS 2 messages: `/root/wksim-ros2-Rzj3Pf/message-build.json`, SHA-256 `29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219`.

The v2 control manifest seals the message manifest path and SHA together with the sealer SHA. Both `full_xyz_pv_yaw_v1` and `xy_velocity_z_position_yaw_v1` now require the exact triple. Omitting the message candidate from the current control path is rejected before candidate verification or child creation. The fixed historical OEvS3W v1 control remains replayable only for the mixed task, at its exact path and SHA, with sealed-v1 verification and no message candidate.

Zero-child admissions passed for both final task profiles after activating the frozen baseline overlays used by resource verification. The WSL focused suite passed 89 tests with six dependency skips. The Windows focused suite passed; the broader Windows run reached the existing symlink-privilege-only limitation. The machine-readable record is `validation/83-control-message-refresh-20260912/summary.json`.

This record establishes candidate readiness. It does not claim a flight result or production admission.
