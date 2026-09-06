# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: UAVCommand.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

## 控制命令的模式
uint8 agent_cmd
# Agent_CMD 枚举
uint8 INIT_POS_HOVER=1  # home点上方悬停
uint8 CURRENT_POS_HOVER=2  # 当前位置上方悬停
uint8 LAND=3
uint8 MOVE=4
uint8 USER_MODE=5

## 控制等级
uint8 control_level
# Control_Level 枚举
uint8 DEFAULT_CONTROL=0  ### 默认控制
uint8 ABSOLUTE_CONTROL=1  ### 绝对控制，在该控制等级下不在响应 默认控制 下任何指令，持续的Move模式应谨慎使用该优先级
uint8 EXIT_ABSOLUTE_CONTROL=2  ### 退出绝对控制控制，在该控制下，会响应上述两种控制的指令

## 移动命令下的子模式
uint8 move_mode
## 移动命令下的子模式枚举
uint8 XYZ_POS = 0  ### 惯性系定点控制
uint8 XY_VEL_Z_POS = 1  ### 惯性系定高速度控制
uint8 XYZ_VEL = 2  ### 惯性系速度控制
uint8 XYZ_POS_BODY = 3  ### 机体系位置控制
uint8 XYZ_VEL_BODY = 4  ### 机体系速度控制
uint8 XY_VEL_Z_POS_BODY = 5  ### 机体系定高速度控制
uint8 TRAJECTORY = 6  ### 轨迹追踪控制
uint8 XYZ_ATT = 7  ### 姿态控制（来自外部控制器）
uint8 LAT_LON_ALT = 8  ### 绝对坐标系下的经纬度

## 控制参考量
float32[3] position_ref  ## [m]
float32[3] velocity_ref  ## [m/s]
float32[3] acceleration_ref  ## [m/s^2]
float32 yaw_ref  ## [rad]
bool yaw_rate_mode  ## True 代表控制偏航角速率
float32 yaw_rate_ref  ## [rad/s]
float32[4] att_ref  ## [rad] + [0-1]
float64 latitude  ## 无人机经度、纬度、高度                 
float64 longitude  ## 无人机经度、纬度、高度
float64 altitude  ## 无人机经度、纬度、高度

## 控制命令的编号 防止接收到错误命令， 编号应该逐次递加
uint32 command_id
