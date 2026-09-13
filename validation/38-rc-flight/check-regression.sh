#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-WjBuqN/install/local_setup.bash
export PYTHONPATH="$PWD/ros2/src/prometheus_control:$PWD:$PYTHONPATH"
export ROS_DOMAIN_ID=93 ROS_LOCALHOST_ONLY=1
export WKSIM_JOINT_CONTROL_TESTS=1
exec /usr/bin/python3 -B -m unittest validation.test_rc_control validation.test_rc_input validation.test_rc_transport validation.test_control_operation_clock validation.test_scene_lease validation.test_prometheus_native -v
