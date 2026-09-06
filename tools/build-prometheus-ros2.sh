#!/usr/bin/env bash
# Build the migrated interfaces and command library using installed Humble.
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
cd "$repo"
work=$(mktemp -d /root/wksim-ros2-XXXXXX)
evidence=$(mktemp -d "$repo/validation/prometheus-ros2-XXXXXXXX")
printf 'Workspace: %s\nEvidence: %s\n' "$work" "$evidence"
trap 'code=$?; printf "%s\n" "$code" > "$evidence/exit-code.txt"' EXIT
printf '%s\n' "$work" > "$evidence/workspace.txt"
mkdir "$work/src"
cp -a "$repo/ros2/src/prometheus_msgs" "$work/src/"
cp -a "$repo/ros2/src/wksim_msgs" "$work/src/"
cp -a "$repo/ros2/src/prometheus_control" "$work/src/"
python3 "$repo/tools/migrate_prometheus_interfaces.py" > "$evidence/source-check.json"
python3 -m unittest discover -s "$repo/validation" -p test_prometheus_interfaces.py -v > "$evidence/unit-tests.log" 2>&1
set +u
source /opt/ros/humble/setup.bash
set -u
export CMAKE_BUILD_PARALLEL_LEVEL=4 MAKEFLAGS=-j4
colcon --log-base "$evidence/colcon-log" build --base-paths "$work/src" \
    --packages-select prometheus_msgs wksim_msgs prometheus_control --build-base "$work/build" --install-base "$work/install" \
    --executor sequential --event-handlers console_direct+ --cmake-args -DCMAKE_BUILD_TYPE=Release \
    > "$evidence/build.log" 2>&1
set +u
source "$work/install/setup.bash"
set -u
python3 -m unittest validation.test_prometheus_control -v > "$evidence/control-tests.log" 2>&1
# Fresh namespace: these test commands cannot reach any user's flight controller.
unshare --net bash -c 'ip link set lo up; exec "$@"' _ \
    env ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=78 RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    python3 "$repo/tools/validate_prometheus_ros2.py" "$work" "$evidence" \
    > "$evidence/runtime.log" 2>&1
cat "$evidence/runtime.log"
printf 'Detailed result: %s/result.json\n' "$evidence"
