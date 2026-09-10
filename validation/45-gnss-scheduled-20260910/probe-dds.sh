#!/bin/bash
set -euo pipefail
exec unshare --net --ipc --mount --propagation private bash -c '
set -e
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-8EMCw6/install/local_setup.bash
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export LD_LIBRARY_PATH=/root/wksim-dds-VxM6Ni/agent-install/lib:${LD_LIBRARY_PATH:-}
exec python3 -B tools/probe_ap_gnss_dds.py /root/wksim-ap-gnss-flight-20260910-01 /root/wksim-ap-gnss-scheduled-dds-01
'
