#!/usr/bin/env bash
set -eo pipefail
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
export RC_AUDIT_FIXTURE=/root/wksim-rc-flight-px4-movement-03/rc-px4-movement-03
export WKSIM_EFFICIENCY_FLIGHT_TESTS=1
python3 -B -m unittest validation.test_rc_audit validation.test_efficiency_flight_audit -v
