#!/usr/bin/env bash
set -eo pipefail
if [[ ${WKSIM_118_PRIVATE:-0} != 1 ]]; then
  export WKSIM_118_PRIVATE=1
  export WK_SESSION_HOST_SHM_DEV=$(stat -c %d /dev/shm)
  exec unshare --net --ipc --mount --propagation private bash "$0"
fi
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
export ROS_DOMAIN_ID=79 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export WKSIM_TEST_PRIVATE_ROS=1
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
export PYTHONPATH="$PWD/ros2/src/prometheus_control:$PWD${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
python3 -B -m unittest validation.test_global_reference validation.test_prometheus_native validation.test_prometheus_native_epochs -v
