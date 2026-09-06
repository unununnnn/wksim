#!/usr/bin/env bash
# Real public-input node checks; no routes or shared DDS transport to host FCs.
set -euo pipefail
[[ $# == 2 || ($# == 3 && $3 == baseline) ]] || exit 2
[[ $1 == px4 || $1 == arducopter ]] || exit 2
prom=$(realpath -e -- "$2")
[[ $(dirname "$prom") == /root && $(basename "$prom") == wksim-ros2-* ]] || exit 2
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1
exec unshare --net --ipc --mount --propagation private bash -c '
set -eo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
if [[ $1 == arducopter ]]; then source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash; fi
source "$2/install/local_setup.bash"
export LD_LIBRARY_PATH="/root/wksim-dds-VxM6Ni/agent-install/lib:${LD_LIBRARY_PATH:-}"
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
if [[ $4 == baseline ]]; then
    extra=()
    if [[ $1 == arducopter ]]; then extra+=(--ap-dds-candidate /root/wksim-ap-dds-yaw-state-4Wr27s); fi
    exec python3 "$3/tools/validate_sitl_physics.py" --stack "$1" \
        --dds-workspace /root/wksim-dds-VxM6Ni --prometheus-workspace "$2" \
        --control-protocol session_v1 "${extra[@]}"
fi
exec python3 "$3/tools/validate_airborne_takeover.py" "$1" "$2"
' wksim "$1" "$prom" "$repo" "${3:-takeover}"
