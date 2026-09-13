#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-omuYiq/install/local_setup.bash
export PYTHONPATH="$PWD:$PYTHONPATH"
export WKSIM_GLOBAL_AUDIT_ROOT=/root/wksim-global-flight-ap-20260910-03/61341c9f94fc459d889ca248c6a5fe44
exec python3 -B -m unittest validation.test_global_audit -v
