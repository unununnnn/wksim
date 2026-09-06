# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: StationCommand.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

## 中途点
#geometry_msgs/PoseStamped first_goal

## 目标点
geometry_msgs/PoseStamped goal

## 控制命令的模式
uint8 command
# enum Command 控制模式枚举
uint8 START=0
uint8 RETURN=1
uint8 STOP=2
