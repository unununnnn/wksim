#!/bin/bash
set -euo pipefail
exec unshare --net --ipc --mount --propagation private bash -c '
set -e
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
export WK_SCENE_ROS_TESTS=1
exec bash validation/44-efficiency-flight/control-tests.sh
'
