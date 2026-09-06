#!/usr/bin/env bash
# Build only an independent control candidate; keep the fixed message overlays.
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
work=$(mktemp -d /root/wksim-joint-control-XXXXXX)
printf 'Control candidate: %s\n' "$work"
mkdir "$work/src"
cp -a "$repo/ros2/src/prometheus_control" "$work/src/"
set +u
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
set -u
export CMAKE_BUILD_PARALLEL_LEVEL=4 MAKEFLAGS=-j4
colcon --log-base "$work/colcon-log" build --base-paths "$work/src" \
  --packages-select prometheus_control --build-base "$work/build" --install-base "$work/install" \
  --executor sequential --cmake-args -DCMAKE_BUILD_TYPE=Release > "$work/build.log" 2>&1
python3 -B "$repo/tools/joint_control_candidate.py" seal "$work"
