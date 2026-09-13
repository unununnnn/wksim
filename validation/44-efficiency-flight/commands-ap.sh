#!/bin/bash
set -euo pipefail
for spec in 'baseline 03' 'fault 01' 'fault 02'; do
 read -r case attempt <<< "$spec"
 run="efficiency-arducopter-$case-$attempt"
 printf 'START %s\n' "$run"
 bash tools/run-efficiency-flight.sh --stack arducopter --case "$case" --run-id "$run" \
  --output-root "/root/wksim-efficiency-flight-arducopter-$case-$attempt" \
  --control-manifest /root/wksim-joint-control-8EMCw6/build.json \
  --control-sha256 e61239c514c45d6c65222277066a7ca629e6e2638b9877a040bdfc99643e7e2e
 bash work/audit-efficiency-flight.sh "/root/wksim-efficiency-flight-arducopter-$case-$attempt/$run" \
  --output "/root/$run-audit.json"
done
