#!/usr/bin/env bash
# Explicit AP diagnostic; fixed shared-time participants and private resources.
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1
exec unshare --net --ipc --mount --propagation private bash -c '
set -eo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-FVMjak/install/local_setup.bash
export LD_LIBRARY_PATH="/root/wksim-dds-VxM6Ni/agent-install/lib:${LD_LIBRARY_PATH:-}"
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
repo=$1
shift
exec python3 -B "$repo/tools/run_ap_mixed_timeout.py" run "$@"
' wksim "$repo" "$@"
