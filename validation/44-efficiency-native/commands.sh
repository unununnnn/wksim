#!/bin/bash
set -euo pipefail
lib=/root/wksim-efficiency-model-r97g_cit/libwksim_efficiency.so
for case in normal event revoke-pending revoke-active tamper; do
 python3 -B tools/probe_motor_efficiency.py --library "$lib" --case "$case" --output "/root/wksim-efficiency-native-$case-02"
done
python3 -B tools/probe_motor_efficiency.py --library "$lib" --case event --output /root/wksim-efficiency-native-event-03
python3 -B tools/probe_motor_efficiency.py --library /root/wksim-private-tmp-bhi18a3s/artifacts/wksim-model-qhdy93lm/libwksim_model.so --case reference --output /root/wksim-efficiency-native-reference-02
