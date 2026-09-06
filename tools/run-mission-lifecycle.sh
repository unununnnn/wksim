#!/usr/bin/env bash
# Labelled operator requests; real formal MissionTask/installed node/FC/physics.
set -euo pipefail
[[ $# == 2 && ($1 == px4 || $1 == arducopter) ]] || exit 2
[[ $2 == pause_resume || $2 == external_resume || $2 == pause_cancel ]] || exit 2
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1
exec unshare --net --ipc --mount --propagation private bash -c '
set -eo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
if [[ $1 == arducopter ]]; then source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash; fi
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
export LD_LIBRARY_PATH="/root/wksim-dds-VxM6Ni/agent-install/lib:${LD_LIBRARY_PATH:-}"
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
exec python3 "$3/tools/validate_mission_lifecycle.py" "$1" "$2"
' wksim "$1" "$2" "$repo"
