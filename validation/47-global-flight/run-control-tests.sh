#!/usr/bin/env bash
set -eo pipefail
[[ $(readlink /proc/self/ns/net) != $(readlink /proc/1/ns/net) ]]
export WKSIM_GNSS_ROS_TESTS=1 ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-jW617Y/install/local_setup.bash
export PYTHONPATH="$PWD/ros2/src/prometheus_control:$PWD:$PYTHONPATH"
exec python3 -B -m unittest validation.test_global_native validation.test_global_reference \
  validation.test_prometheus_native validation.test_prometheus_native_epochs \
  validation.test_rc_control validation.test_control_takeoff_settle \
  validation.test_gnss_flight validation.test_gnss_observers -v
