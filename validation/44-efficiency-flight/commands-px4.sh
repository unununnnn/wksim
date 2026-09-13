#!/bin/bash
set -euo pipefail
for spec in 'px4 fault 01' 'px4 fault 02' 'arducopter baseline 01' 'arducopter fault 01' 'arducopter fault 02'; do
 read -r stack case attempt <<< "$spec"
 run="efficiency-$stack-$case-$attempt"
 printf 'START %s\n' "$run"
 bash tools/run-efficiency-flight.sh --stack "$stack" --case "$case" --run-id "$run" \
  --output-root "/root/wksim-efficiency-flight-$stack-$case-$attempt" \
  --control-manifest /root/wksim-joint-control-WjBuqN/build.json \
  --control-sha256 ae5236af5052e81a256566a5e05d1840752fffb4d6f5cc512e0c0a5bb9e88c1d
 bash work/audit-efficiency-flight.sh "/root/wksim-efficiency-flight-$stack-$case-$attempt/$run" \
  --output "/root/$run-audit.json"
done
