#!/usr/bin/env bash
# Unit/RMW checks only. Does not launch FC, Agent, physics, UE or MATLAB.
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"
evidence=$(mktemp -d "$repo/validation/session-product-checks-XXXXXXXX")
printf 'Evidence: %s\n' "$evidence"
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1
export WK_SESSION_HOST_SHM_DEV=$(stat -c %d /dev/shm)
unshare --net --ipc --mount --propagation private bash -c '
set -eo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
export ROS_DOMAIN_ID=79 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export WKSIM_CONTROL_PROFILE_LIVE_RESOURCES=1
tests=()
for path in validation/test_*.py; do
  [[ $path == validation/test_wksim_preflight.py ]] && continue
  # Windows operator host has its own real Windows test matrix.
  [[ $path == validation/test_wksim_console_*.py ]] && continue
  module=${path%.py}
  tests+=("${module//\//.}")
done
exec python3 -B -m unittest "${tests[@]}" -v
' > "$evidence/session-tests.log" 2>&1
bash -c '
set -e
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-0viK3f/install/local_setup.bash
export WKSIM_PREFLIGHT_LIVE_RESOURCES=1
exec python3 -B -m unittest validation.test_wksim_preflight -v
' > "$evidence/legacy-preflight-tests.log" 2>&1
printf 'Both test matrices passed. Logs: %s\n' "$evidence"
