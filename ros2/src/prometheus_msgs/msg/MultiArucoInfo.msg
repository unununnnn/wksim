# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: MultiArucoInfo.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

## 检测到的aruco码数量
int32 num_arucos

## 每个aruco码的检测结果
ArucoInfo[] aruco_infos
