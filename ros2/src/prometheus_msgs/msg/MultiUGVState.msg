# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: MultiUGVState.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

##
int32 swarm_num_ugv

## 从1开始
UGVState[] ugv_state_all
