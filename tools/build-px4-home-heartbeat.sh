#!/usr/bin/env bash
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
baseline=/root/wksim-px4-state-ONa1Kw/src
[[ $(git -C "$baseline" rev-parse HEAD) == d6f12ad1c4f70ad3230afd7d86e971421e02fef4 ]]
work=$(mktemp -d /root/wksim-px4-home-XXXXXX)
printf 'PX4 home candidate: %s\n' "$work"
mkdir "$work/src"
tar -C "$baseline" --exclude=./build -cf - . | tar -C "$work/src" -xf -
git -C "$work/src" apply --check "$repo/patches/px4/0003-home-observation-heartbeat.patch"
git -C "$work/src" apply "$repo/patches/px4/0003-home-observation-heartbeat.patch"
make -C "$work/src" -j4 px4_sitl_default > "$work/build.log" 2>&1
ldd "$work/src/build/px4_sitl_default/bin/px4" > "$work/dependency-check.log"
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1
python3 -B "$repo/tools/px4_home_candidate.py" seal "$work"
