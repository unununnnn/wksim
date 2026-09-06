# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: GimbalState.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
std_msgs/Header header

# gimbal type; value = {SV::GimbalType};0:G1;1:Q10F;2:AT10;3:GX40;4:SU17
uint8 type
# gimbal movement mode; 0:None; 1:lock head; 2：unlock head; 3: tracking;
uint8 move_mode
# gimbal image type; 0:normal; 1:infrared; 2:merge;
uint8 image_mode
# gimbal zoom
bool is_zoom
# gimbal rec; 0:none; 1:gimbal rec; 2:local rec; 3:gimbal & local rec;
uint8 is_rec
# gimbal fov, XY
float32[2] fov
# gimbal real time angle, RPY <deg>
float32[3] angle_rt
# gimbal real time angle rate, RPY <deg/s> <if gimbal supported>
float32[3] angle_rt_rate
# gimbal setted max angle rate <deg/s> <if gimbal supported>
float32[3] angle_rate_set
# gimbal follow the track result; 0: false, 1:true
uint8 gimbal_follow_track_res_mode
