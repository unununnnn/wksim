#!/usr/bin/env bash
# Run the installed product node with no route to a user's FC/Agent.
set -euo pipefail
[[ $# == 3 || $# == 4 || $# == 6 ]] || { echo 'Usage: run-prometheus-validation.sh STACK DDS_WORKSPACE PROMETHEUS_WORKSPACE [AP_STATE_CANDIDATE [AP_BUILD_MANIFEST AP_BUILD_SHA256]]' >&2; exit 2; }
stack=$1
dds=$(realpath -e -- "$2")
prom=$(realpath -e -- "$3")
[[ $(dirname "$dds") == /root && $(basename "$dds") == wksim-dds-* ]] || exit 2
[[ $(dirname "$prom") == /root && $(basename "$prom") == wksim-ros2-* ]] || exit 2
case "$stack" in arducopter) [[ $# == 4 || $# == 6 ]] ;; px4) [[ $# == 3 ]] ;; *) exit 2 ;; esac
if [[ "$(readlink /proc/self/ns/net)" == "$(readlink /proc/1/ns/net)" ||
      "$(readlink /proc/self/ns/ipc)" == "$(readlink /proc/1/ns/ipc)" ||
      "$(readlink /proc/self/ns/mnt)" == "$(readlink /proc/1/ns/mnt)" ]]; then
    exec unshare --net --ipc --mount --propagation private bash "$0" "$@"
fi
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
set +u
source "$dds/ros-install/setup.bash"
set -u
extra=()
if [[ $stack == arducopter ]]; then
    candidate=$(realpath -e -- "$4")
    [[ $(dirname "$candidate") == /root && $(basename "$candidate") == wksim-ap-dds-yaw-* ]] || exit 2
    set +u
    source "$candidate/ros-install/local_setup.bash"
    set -u
    if [[ $# == 6 ]]; then
        extra+=(--ap-build-manifest "$5" --ap-build-sha256 "$6")
        export WKSIM_CONTROL_PROTOCOL=session_v1
    else
        extra+=(--ap-dds-candidate "$candidate")
    fi
fi
set +u
source "$prom/install/local_setup.bash"
set -u
export LD_LIBRARY_PATH="$dds/agent-install/lib:${LD_LIBRARY_PATH:-}"
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1
exec python3 "$(dirname "$0")/validate_sitl_physics.py" --stack "$stack" \
    --dds-workspace "$dds" --prometheus-workspace "$prom" \
    --control-protocol "${WKSIM_CONTROL_PROTOCOL:-legacy_v1}" "${extra[@]}"
