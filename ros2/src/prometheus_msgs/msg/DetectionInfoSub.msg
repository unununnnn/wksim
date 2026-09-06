# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: DetectionInfoSub.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
#目标框的位置（主要斜对角两个点）
float32 left
float32 top
float32 bot
float32 right


## TRACK TARGET(目标框ID)
int32 track_ids
