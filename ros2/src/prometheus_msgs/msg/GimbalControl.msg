# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: GimbalControl.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

# gimbal commod mode; 0:None; 1:speed; 2:angle; 3:mixed
uint8 mode
# RPY <deg>
float32[3] angle
# RPY <deg/s>
float32[3] speed
