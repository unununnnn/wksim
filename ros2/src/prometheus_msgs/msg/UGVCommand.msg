# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: UGVCommand.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

## 控制命令的编号 防止接收到错误命令， 编号应该逐次递加
uint32 command_id

## 控制命令的模式
uint8 mode
# enum Mode 控制模式枚举
uint8 HOLD=0
uint8 DIRECT_CONTROL_BODY=1
uint8 DIRECT_CONTROL_ENU=2
uint8 POINT_CONTROL=3
uint8 PATH_CONTROL=4
uint8 TEST=5

float32[2] position_ref  ## [m]
float32 yaw_ref  ## [rad]

float32[2] linear_vel  ## [m/s]
float32 angular_vel  ## [rad/s]
