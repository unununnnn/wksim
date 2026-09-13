#!/usr/bin/env bash
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
parent=/root/wksim-px4-land-7RjMjQ
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1
python3 -B "$repo/tools/px4_land_candidate.py" check "$parent/land-build.json" --sha256 45c5332cf06a84952189fcf2eabc5d2e15fde9236c704a5c3d6318e7f5dcb3ac
candidate=$(mktemp -d /root/wksim-px4-component-XXXXXX)
printf 'PX4 component observation candidate: %s\n' "$candidate"
mkdir "$candidate/src"
tar -C "$parent/src" --exclude=./build -cf - . | tar -C "$candidate/src" -xf -
git -C "$candidate/src" apply --check "$repo/patches/px4/0005-component-wait-tracing.patch"
git -C "$candidate/src" apply "$repo/patches/px4/0005-component-wait-tracing.patch"
make -C "$candidate/src" -j4 px4_sitl_default > "$candidate/build.log" 2>&1
ldd "$candidate/src/build/px4_sitl_default/bin/px4" > "$candidate/dependency-check.log"
python3 -B "$repo/tools/px4_component_candidate.py" seal "$candidate"
