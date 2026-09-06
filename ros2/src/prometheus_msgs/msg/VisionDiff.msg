# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: VisionDiff.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
uint8 id
uint8 detect

uint16 object_x  # 左上角
uint16 object_y  # 左上角
uint16 object_width
uint16 object_height

uint16 frame_width
uint16 frame_height

# Gimbal 跟踪pid
float32 kp
float32 ki
float32 kd

int8 ctl_mode  # 0: yaw+pitch, 1: roll+pitch 3:混合(未实现)
int8 YAW_PITCH = 0
int8 ROLL_PITCH = 1
int8 MIX=3

# 用于自动缩放
float32 curr_size  #框选近大远小
float32 max_size
float32 min_size  #框选大小

float32 track_ignore_error
bool auto_zoom
