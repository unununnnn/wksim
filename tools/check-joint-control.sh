#!/usr/bin/env bash
# Candidate identity + private ROS/RMW tests. Never starts a flight controller.
set -euo pipefail
[[ $# == 2 ]] || { echo 'Usage: check-joint-control.sh MANIFEST SHA256' >&2; exit 2; }
repo=$(realpath -e -- "$(dirname "$0")/..")
manifest=$(realpath -e -- "$1")
candidate=$(dirname "$manifest")
cd "$repo"
python3 -B -c 'import sys; from tools.joint_control_candidate import check; check(sys.argv[1],sys.argv[2])' "$manifest" "$2"
export TASK_HOST_NET=$(readlink /proc/self/ns/net) TASK_HOST_IPC=$(readlink /proc/self/ns/ipc)
export TASK_HOST_MNT=$(readlink /proc/self/ns/mnt) TASK_HOST_SHM=$(stat -c %d /dev/shm)
export WKSIM_JOINT_CONTROL_CANDIDATE="$candidate"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}"
evidence=$(mktemp -d "$repo/validation/joint-control-checks-XXXXXXXX")
printf 'Evidence: %s\n' "$evidence"
unshare --net --ipc --mount --propagation private bash -c '
set -eo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
export PYTHONPATH="$WKSIM_JOINT_CONTROL_CANDIDATE/install/prometheus_control/local/lib/python3.10/dist-packages:$PYTHONPATH"
export AMENT_PREFIX_PATH="$WKSIM_JOINT_CONTROL_CANDIDATE/install/prometheus_control:$AMENT_PREFIX_PATH"
export ROS_DOMAIN_ID=79 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export WKSIM_TASK_IDENTITY_ROS=1 WKSIM_JOINT_CONTROL_TESTS=1
exec python3 -B -m unittest validation.test_control_operation_clock validation.test_prometheus_native \
  validation.test_task_identity validation.test_wksim_mission_task validation.test_wksim_runtime \
  validation.test_joint_evidence validation.test_joint_control_candidate validation.test_control_shutdown \
  validation.test_joint_lifecycle_deadline validation.test_joint_retirement -v
' > "$evidence/tests.log" 2>&1
printf 'Candidate tests passed: %s\n' "$evidence"
