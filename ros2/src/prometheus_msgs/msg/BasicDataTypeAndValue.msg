# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0
# wksim ROS2 migration of Prometheus 5dcd8cfa764d: BasicDataTypeAndValue.msg.
# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.
string name

uint8 type
uint8 INTEGER=1
uint8 BOOLEAN=2
uint8 FLOAT=3
uint8 DOUBLE=4
uint8 STRING=5

int32 integer_value
bool boolean_value
float32 float_value
float64 double_value
string string_value
