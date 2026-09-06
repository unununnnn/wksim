# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: UAVControlState.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

## 无人机编号
uint8 uav_id

## 无人机控制状态
uint8 control_state
## 状态枚举
uint8 INIT=0
uint8 RC_POS_CONTROL=1
uint8 COMMAND_CONTROL=2
uint8 LAND_CONTROL=3

## 无人机控制器标志量
uint8 pos_controller
## 状态枚举
uint8 PX4_ORIGIN=0
uint8 PID=1
uint8 UDE=2
uint8 NE=3

# 无人机安全保护触发标志量
bool failsafe
