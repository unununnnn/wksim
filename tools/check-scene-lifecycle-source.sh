#!/usr/bin/env bash
# Explicit isolated ROS source checks; no FC, Agent or UE process is started.
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
cd "$repo"
evidence=$(mktemp -d "$repo/validation/scene-lifecycle-checks-XXXXXXXX")
printf 'Evidence: %s\n' "$evidence"
export TASK_HOST_NET=$(readlink /proc/self/ns/net) TASK_HOST_IPC=$(readlink /proc/self/ns/ipc)
export TASK_HOST_MNT=$(readlink /proc/self/ns/mnt) TASK_HOST_SHM=$(stat -c %d /dev/shm)
export PYTHONDONTWRITEBYTECODE=1
unshare --net --ipc --mount --propagation private bash -c '
set -eo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
export PYTHONPATH="$PWD/ros2/src/prometheus_control:$PWD:$PYTHONPATH"
export ROS_DOMAIN_ID=81 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export WK_SCENE_ROS_TESTS=1 WK_TASK_SCENE_ROS_TESTS=1 WK_PRIVATE_TMP_TESTS=1
python3 -B -m unittest validation.test_scene_lease validation.test_prometheus_native \
  validation.test_control_operation_clock validation.test_task_scene_pause \
  validation.test_task_identity validation.test_scene_clock validation.test_joint_pause_probe \
  validation.test_task_airborne_recovery validation.test_private_tmp_isolation validation.test_joint_kinematics_audit -v
' > "$evidence/tests.log" 2>&1
printf 'Source checks passed: %s\n' "$evidence"
