#!/usr/bin/env bash
# Caller sources the fixed independent profile; isolate all actual ROS/FC resources.
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}"
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
exec unshare --net --ipc --mount --propagation private bash -c '
set -euo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
exec python3 -B -m tools.validate_gcs_handoff "$@"
' gcs-handoff "$@"
