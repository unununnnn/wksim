#!/usr/bin/env bash
set -eo pipefail
model=/root/wksim-private-tmp-bhi18a3s/artifacts/wksim-model-qhdy93lm
work=$(mktemp -d /tmp/wksim-global-origin-check-XXXXXX)
g++ -std=c++17 -O2 -I "$model" tools/global_origin_probe.cpp -ldl -o "$work/probe"
"$work/probe" "$model/libwksim_model.so"
sha256sum tools/global_origin_probe.cpp "$model/Exp1_MinModelTemp.h" "$model/Exp1_MinModelTemp.cpp" "$work/probe"
