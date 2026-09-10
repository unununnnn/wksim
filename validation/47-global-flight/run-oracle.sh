#!/usr/bin/env bash
set -eo pipefail
work=$(mktemp -d /tmp/wksim-global-oracle-XXXXXX)
g++ -std=c++17 -O0 -ffp-contract=off validation/lunar-117-20260909-coordinate-01/oracle.cpp -o "$work/oracle"
python3 -B validation/test_global_reference.py --oracle "$work/oracle"
