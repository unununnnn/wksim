#!/usr/bin/env bash
# Build only an independent control candidate; keep the fixed message overlays.
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
work=$(mktemp -d /root/wksim-joint-control-XXXXXX)
printf 'Control candidate: %s\n' "$work"
cp -a "$repo/tools/build-joint-control.sh" "$work/build-joint-control.sh"
mkdir "$work/src"
cp -a "$repo/ros2/src/prometheus_control" "$work/src/"
mkdir -p "$work/Simulator/wksim_runtime" "$work/Simulator/wksim_runtime/message_pins" \
  "$work/Simulator/wksim_planning"
# Keep the installed runtime set explicit.  This is the complete import
# closure for the public trajectory bridge and Route-B transport node; do not
# replace it with a runtime-wide glob.
for name in __init__.py task.py trajectory_bridge.py \
  planner_command_egress.py planner_transport_node.py \
  planner_transport_receiver.py planner_transport_pump.py \
  bspline_tcp_envelope.py planner_scene_binding.py; do
  cp -a "$repo/Simulator/wksim_runtime/$name" "$work/Simulator/wksim_runtime/"
done
for name in ros1_Bspline.msg ros2_Bspline.msg; do
  cp -a "$repo/Simulator/wksim_runtime/message_pins/$name" \
    "$work/Simulator/wksim_runtime/message_pins/"
done
for name in ego_bspline_bridge.py ego_evaluator.py ego_trajectory_adapter.py \
  trajectory_session.py ego_scene_admission.py scene_profile.py; do
  cp -a "$repo/Simulator/wksim_planning/$name" "$work/Simulator/wksim_planning/"
done
set +u
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-Rzj3Pf/install/local_setup.bash
set -u
export CMAKE_BUILD_PARALLEL_LEVEL=4 MAKEFLAGS=-j4
colcon --log-base "$work/colcon-log" build --base-paths "$work/src" \
  --packages-select prometheus_control --build-base "$work/build" --install-base "$work/install" \
  --executor sequential --cmake-args -DCMAKE_BUILD_TYPE=Release \
  "-DWKSIM_SIMULATOR_ROOT=$work/Simulator" > "$work/build.log" 2>&1
python3 -B "$repo/tools/joint_control_candidate.py" seal "$work"
