#!/usr/bin/env bash
set -eo pipefail
cd '/mnt/c/Users/PC/Documents/odid编译/wksim'
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-FVMjak/install/local_setup.bash
export PYTHONPATH="/root/wksim-attitude-audit-deps-g_2y8olg:$PYTHONPATH"
export PYTHONDONTWRITEBYTECODE=1
exec /usr/bin/python3 -B "$@"
