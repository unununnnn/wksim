# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: DepthCompressed.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header
uint32 height
uint32 width
uint8[] data
