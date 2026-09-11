# ROS 1 message overlay build, 2026-09-12

This is the retained build record for the ROS 1 half of the #102 EGO
trajectory transport.  Both attempts used repository commit
`f627d19b763d6fdfc9f6b34bc17fa2edfb452548` and the installed ROS 1 Noetic
environment in the `RflySim-20.04` WSL distribution.  No package was installed
and no network access, ROS master, planner, DDS peer, SITL, UE, or MATLAB process
was used.

The first, deliberately unmodified, `catkin_make` invocation used a new
`/root/wksim-msg-overlay-20260912-01` workspace and returned 2.  All ROS message
generation completed before the failure.  The failure belongs to the optional
`traj_utils` C++ library target: its forced C++11 mode is incompatible with the
Jammy log4cxx headers, and its Eigen source also fails against the installed
Eigen 3.4 API.  The 50,790-byte raw log remains at
`/root/wksim-msg-overlay-20260912-01/build.log`, SHA-256
`a083142e17bf808590ebf361ed029b14f11437b2f6fb5eeb4c2888bb368a8a91`.
This failure is retained and was not rerun or reclassified as a full build
pass.

The second attempt used another new workspace,
`/root/wksim-msg-overlay-20260912-msgonly-01`, and invoked only the two message
targets:

```text
catkin_make -DCMAKE_BUILD_TYPE=Release \
  prometheus_msgs_generate_messages traj_utils_generate_messages
```

It returned 0.  The log contains both exact terminal target records:

```text
[100%] Built target prometheus_msgs_generate_messages
[100%] Built target traj_utils_generate_messages
```

The 40,219-byte raw log remains at
`/root/wksim-msg-overlay-20260912-msgonly-01/build.log`, SHA-256
`a483164a04dd3c7a43b02ed649f58cd1fe610efbb5edff0bd003175d5eb922ed`.
The two source `Bspline.msg` files are byte-identical at SHA-256
`08ab59c600038eaff054bab381c48f3bf16c693a34007c64b8ba98b8a44ee706`.

The message-only workspace generated 59 `prometheus_msgs` C++ headers and 3
`traj_utils` C++ headers.  The four transport-critical products are pinned in
`validation/102-ros1-message-overlay-20260912/summary.json`.  After sourcing the
workspace, `rospack find` resolved both packages and Python imported and
instantiated both `Bspline` types with matching `drone_id`, `order`, `traj_id`,
and `knots`.  A final exact-name process check found no `make`, `cc1plus`,
`catkin_make`, or `roscore` process.

This proves only that the ROS 1 custom messages needed by the committed relay
can be generated and loaded in the selected Noetic environment.  It does not
provide `ros1_bridge`, a ROS 1 to ROS 2 transfer, a shared simulation clock, a
running EGO planner, a ControlNode acknowledgement, obstacle avoidance, or a
flight result.  The default `traj_utils` C++ library remains incompatible with
this Jammy environment until that separate source issue is resolved.
