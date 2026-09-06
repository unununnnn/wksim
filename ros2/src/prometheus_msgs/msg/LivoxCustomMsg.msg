# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: LivoxCustomMsg.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
# Livox publish pointcloud msg format.

std_msgs/Header header  # ROS standard message header
uint64 timebase  # The time of first point
uint32 point_num  # Total number of pointclouds
uint8 lidar_id  # Lidar device id number
uint8[3] rsvd  # Reserved use
LivoxCustomPoint[] points  # Pointcloud data
