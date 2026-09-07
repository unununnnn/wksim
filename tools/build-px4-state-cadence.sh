#!/usr/bin/env bash
# New private source/build directory. Does not modify or run the fixed PX4.
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
baseline=/root/wksim-dependencies/px4-d6f12ad1
[[ $(git -C "$baseline" rev-parse HEAD) == d6f12ad1c4f70ad3230afd7d86e971421e02fef4 ]]
[[ $(sha256sum "$baseline/build/px4_sitl_default/bin/px4" | cut -d' ' -f1) == 987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd ]]
work=$(mktemp -d /root/wksim-px4-state-XXXXXX)
printf 'PX4 state candidate: %s\n' "$work"
mkdir "$work/src"
tar -C "$baseline" --exclude=./build --exclude=./wksim-runtime-files.json -cf - . | tar -C "$work/src" -xf -
git -C "$work/src" apply --check "$repo/patches/px4/0001-estimator-status-cadence.patch"
git -C "$work/src" apply "$repo/patches/px4/0001-estimator-status-cadence.patch"
git -C "$work/src" apply --check "$repo/patches/px4/0002-independent-sitl-without-gazebo.patch"
git -C "$work/src" apply "$repo/patches/px4/0002-independent-sitl-without-gazebo.patch"
make -C "$work/src" -j4 px4_sitl_default > "$work/build.log" 2>&1
ldd "$work/src/build/px4_sitl_default/bin/px4" > "$work/dependency-check.log"
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1
python3 -B "$repo/tools/px4_state_candidate.py" seal "$work"
