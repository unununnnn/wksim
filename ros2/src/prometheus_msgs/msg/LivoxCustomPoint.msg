# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: LivoxCustomPoint.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
# Livox costom pointcloud format.

uint32 offset_time  # offset time relative to the base time
float32 x  # X axis, unit:m
float32 y  # Y axis, unit:m
float32 z  # Z axis, unit:m
uint8 reflectivity  # reflectivity, 0~255
uint8 tag  # livox tag
uint8 line  # laser number in lidar
