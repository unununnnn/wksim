# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: BoundingBox.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
# 目标框相关信息
string class_name  # 类别
float64 probability  # 置信度
int64 xmin  # 右上角
int64 ymin
int64 xmax  # 坐下角
int64 ymax
