#!/usr/bin/env bash
# Unit decisions plus a real ROS callback in private namespaces; no FC/Agent.
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
cd "$repo"
export PYTHONDONTWRITEBYTECODE=1
unshare --net --ipc --mount --propagation private bash -c '
set -eo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
export PYTHONPATH="/root/wksim-joint-control-JlC29M/install/prometheus_control/local/lib/python3.10/dist-packages:$PWD:$PYTHONPATH"
export ROS_DOMAIN_ID=83 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp WK_TRACE_ROS=1
python3 -B -m unittest validation.test_native_state_trace -v
'
