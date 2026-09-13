# Cross-distribution ROS2 → ROS1 transport: passed

Ubuntu-22.04 publishes Clock, Odometry, UAVControlState, BoundingBoxes and MultiDetectionInfoSub. RflySim-20.04 receives a one-use network FD, retains its own mount/IPC namespaces, and runs the built ROS1 bridge plus ROS1 subscriber. Both endpoints report the same boot and network identity, different IPC identities, unchanged project sources and pass status. All three synthetic timestamps and renamed nested fields arrived; ROS1 simulated time remained frozen during each 120ms wall-time pause. The three Rfly child processes exited zero, and its local `/proc` view contained no remaining process in that network. The Ubuntu publisher wrapper also exited zero.

The failed attempts are retained separately:

- `cross-distro-ros-20260912-01`: default transport discovered all five topics but delivered no samples.
- `cross-distro-ros-20260912-02`: adding UDP-only XML alone did not resolve delivery.
- `cross-distro-ros-20260912-03`: runtime capture confirmed the XML path was present, both endpoints used rmw_fastrtps_cpp, and their endpoint GUIDs differed. Ubuntu loaded Fast DDS 2.6.12; Rfly loaded 2.6.10.

The configuration conflict is explained by [Humble's RMW participant implementation](https://github.com/ros2/rmw_fastrtps/blob/humble/rmw_fastrtps_shared_cpp/src/participant.cpp): after loading XML, `localhost_only` adds a new UDP transport and a shared-memory transport. The successful attempt keeps the same XML but sets `ROS_LOCALHOST_ONLY=0` inside the owned private network. The XML explicitly disables built-in transports and permits only UDPv4 on 127.0.0.1. See the primary [Fast DDS transport configuration](https://fast-dds.docs.eprosima.com/en/2.6.x/fastdds/transport/udp/udp.html) and [profile environment variable](https://fast-dds.docs.eprosima.com/en/2.6.x/fastdds/env_vars/env_vars.html) documentation. No middleware libraries or topic QoS values were changed.

`bridge-runtime.json` records the actual child environment and loaded library paths. `publisher-runtime.json` records the publisher's RMW and endpoint identities; these are retained provenance from the focused reproducer, not production instrumentation. The final script/config snapshots and their SHA256 values are listed in `manifest.json`. Earlier failures retain their original logs/results/source hashes, but no separate source snapshot was captured for those intermediate revisions.

Run `validation/ros1_bridge_cross_distro_probe.py owner|visitor SHARED_DIRECTORY ABSOLUTE_OUTPUT --udp-profile ABSOLUTE_XML`. Owner uses the Ubuntu Rzj3Pf overlay in a fresh network/IPC/mount namespace with loopback up; visitor uses fresh IPC/mount namespaces and joins the owner's network through the handoff. Both mount private `/dev/shm`. The publisher's ROS domain remains 79. `setup.json` records this attempt's shared directory, and all reports are written to persistent storage before exit.

This proves cross-distribution fixture transport, not real FC/planner state, control ownership, cancellation, collision clearance or Full acceptance. It does not change any physics step, trajectory timestamp, freshness budget or rate acceptance limit.
