# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: FormationAssign.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
#队形位置
geometry_msgs/Point[] formation_poses

#位置点是否选取
bool[] assigned
