# Rfly ROS1 processes in an owned joint network

`Simulator/wksim_runtime/netns_handoff.py` provides a one-use Linux FD handoff over a pathname Unix socket in a caller-owned mode-0700 `/mnt/wsl/wksim-netns-*` directory. Export must run inside the already-created private network. A single-threaded Rfly process can join that network, then exec its ROS1/bridge program while keeping its own filesystem and IPC namespace. No PID-namespace correspondence is inferred.

The exporter verifies its network is private relative to the distribution init process, publishes a completed mode-0600 grant atomically, authenticates one same-UID peer and sends the actual network FD. The receiver validates the grant and response identity, descriptor type and dev/inode before setns, and checks that mount/IPC membership did not change. Every received FD is closed; owned endpoint files are removed on completion or failure. The CLI supports `export DIRECTORY RUN_ID` and `enter DIRECTORY RUN_ID -- PROGRAM ARGUMENTS...`.

The real Ubuntu-to-Rfly loopback fixture and malformed-capsule checks are recorded in `validation/netns-handoff-20260912-03/`. Results must be written to persistent storage before processes exit: `/mnt/wsl` is temporary and was observed to disappear across a WSL reboot.

Next integration must export only during a real scene's pre-physics setup, supervise the Rfly actor as part of that scene, and verify ROS/DDS traffic across the distinct IPC namespaces. Existing SessionState/clock/identity/freshness gates remain authoritative; a transferred namespace FD does not grant flight control. No real FC/planner attachment is claimed by the loopback fixture.

Cross-distribution ROS/DDS fixture transport is now verified in
`validation/cross-distro-ros-20260912-04/`. With separate `/dev/shm`, use the
explicit `cross_namespace_dds.xml` loopback UDP profile and set
`ROS_LOCALHOST_ONLY=0` only inside the already-verified private network.
Humble RMW otherwise appends SHM after XML loading. Default transport and XML
alone failed; the successful configuration delivered all five message types
at three timestamps without sharing IPC or changing message QoS. Real scene
state sources and actor supervision still need integration.
