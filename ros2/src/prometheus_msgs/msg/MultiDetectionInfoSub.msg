# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: MultiDetectionInfoSub.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

#模式：0：空闲  2.simaRPN  3.deepsort/sort
uint8 mode

## 检测到的目标数量
int32 num_objs

## 每个目标的检测结果
DetectionInfoSub[] detection_infos
