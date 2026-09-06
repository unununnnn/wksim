# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: LinktrackNodeframe2.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
uint8 role
uint8 id
uint32 local_time
uint32 system_time
float32 voltage
float32[3] pos_3d
float32[3] eop_3d
float32[3] vel_3d
float32[3] angle_3d
float32[4] quaternion
float32[3] imu_gyro_3d
float32[3] imu_acc_3d
LinktrackNode2[] nodes
