#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-jW617Y/install/local_setup.bash
export PYTHONPATH="$PWD:$PYTHONPATH"
exec python3 -B tools/audit_global_flight.py "${1:?run directory}" --output "${2:?fresh external audit output}"
