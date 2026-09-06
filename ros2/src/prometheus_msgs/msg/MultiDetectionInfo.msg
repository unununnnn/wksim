# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: MultiDetectionInfo.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

## 检测到的目标数量
int32 num_objs

## Detecting or Tracking (0:detect, 1:track)
int32 detect_or_track

## 每个目标的检测结果
DetectionInfo[] detection_infos
