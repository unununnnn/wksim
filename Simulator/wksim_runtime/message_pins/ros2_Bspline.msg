# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: Bspline.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
int32 drone_id

int32 order
int64 traj_id
builtin_interfaces/Time start_time

float64[] knots
geometry_msgs/Point[] pos_pts

float64[] yaw_pts
float64 yaw_dt
