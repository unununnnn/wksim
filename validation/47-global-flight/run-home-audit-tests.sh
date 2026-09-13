#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-jW617Y/install/local_setup.bash
export PYTHONPATH="$PWD:$PYTHONPATH"
export WKSIM_GLOBAL_AUDIT_ROOT="${1:?retained complete home-change run}"
exec python3 -B -m unittest validation.test_global_home_audit -v
