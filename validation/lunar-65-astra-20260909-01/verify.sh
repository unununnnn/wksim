#!/usr/bin/env bash
# Offline only. Refuses to overwrite outputs from a previous verification.
set -eo pipefail
set -C
cd '/mnt/c/Users/PC/Documents/odid编译/wksim'
case_dir=validation/lunar-65-astra-20260909-01
runner="$case_dir/run-audit.sh"
bash "$runner" -m unittest validation.test_hex_flight_audit validation.test_hex_physics_evidence -v > "$case_dir/tests-final.log" 2>&1
for run in hex-px4-01 hex-px4-02; do
    set +e
    bash "$runner" tools/audit_hex_flight.py --run-dir "/root/wksim-hex-flight-px4-${run##*-}/$run" \
        --output "$case_dir/$run-rejected.json" > "$case_dir/$run-cli.log" 2>&1
    code=$?
    set -e
    printf '%s exit=%s\n' "$run" "$code"
    test "$code" = 1
done
set +e
bash "$runner" tools/audit_hex_flight.py --run-dir /root/wksim-hex-flight-px4-03/hex-px4-03 \
    --require-cold-reset --output "$case_dir/px4-03-cold-required.json" > "$case_dir/cold-required-cli.log" 2>&1
code=$?
set -e
printf 'cold-required exit=%s\n' "$code"
test "$code" = 1
sha256sum tools/audit_hex_flight.py validation/test_hex_flight_audit.py tools/hex_physics_evidence.py \
    Simulator/wksim_runtime/hex-flight-v1.json "$case_dir/px4-03-audit-final.json" \
    "$case_dir/tests-final.log" > "$case_dir/hashes.txt"
tail -5 "$case_dir/tests-final.log"
