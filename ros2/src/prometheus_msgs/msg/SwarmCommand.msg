# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: SwarmCommand.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

## 消息来源
string source

## 编队套件数量
uint8 swarm_num

uint8 swarm_location_source

# enum loc 定位来源枚举
uint8 MOCAP = 0
uint8 GPS = 4
uint8 RTK = 5
uint8 UWB = 6

## 命令
uint8 swarm_cmd
# enum CMD 控制模式枚举
uint8 READY=0
uint8 INIT=1
uint8 START=2
uint8 HOLD=3
uint8 STOP=4
uint8 FORMATION=5

uint8 COL_AROUND_CIRCLE=6
uint8 COL_FOLLOW_UAV=7
uint8 COL_FOLLOW_UGV=8

uint8 INIT_PLANNER=9
uint8 SWARM_FORMATION_PLANNER=10

uint8 FOLLOW=11
uint8 SEARCH=12
uint8 ATTACK=13

## 编队控制参考量
float32[3] leader_pos
float32[2] leader_vel
float32 swarm_size
uint8 swarm_shape
uint8 ONE_COLUMN=0
uint8 TRIANGLE=1
uint8 SQUARE=2
uint8 CIRCULAR=3
uint8 AROUND_CIRCLE=4

## 搜索控制参考量
float32 target_area_x_min  ## [m]
float32 target_area_y_min  ## [m]
float32 target_area_x_max  ## [m]
float32 target_area_y_max  ## [m]

## 攻击控制参考量
float32[3] attack_target_pos  ## [m]

#队形位置
geometry_msgs/Point[] formation_poses
