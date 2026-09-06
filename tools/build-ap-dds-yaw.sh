#!/usr/bin/env bash
# Opt-in candidate only. Never patch or rebuild the existing validated FC source.
set -euo pipefail
dds_work=$(realpath -e -- "${1:?Usage: build-ap-dds-yaw.sh DDS_WORKSPACE [--with-state|--with-clock-stop]}")
[[ $# == 1 || ( $# == 2 && ( $2 == --with-state || $2 == --with-clock-stop ) ) ]] || exit 2
repo=$(realpath -e -- "$(dirname "$0")/..")
[[ $(dirname "$dds_work") == /root && $(basename "$dds_work") == wksim-dds-* ]] || exit 2
source_root="$dds_work/src/ardupilot"
[[ $(git -C "$source_root" rev-parse HEAD) == 1511f27194f1dcc3728270883047bdf022b3fd53 ]]
[[ -z $(git -C "$source_root" status --porcelain) ]] || { echo 'Base source is not clean' >&2; exit 2; }
patch_file="$repo/patches/arducopter/0001-dds-global-position-yaw.patch"
state_patch="$repo/patches/arducopter/0002-dds-local-state.patch"
clock_patch="$repo/patches/arducopter/0003-json-integer-clock-interruptible-stop.patch"
git -C "$source_root" apply --check "$patch_file"
prefix=wksim-ap-dds-yaw
[[ ${2:-} != --with-clock-stop ]] || prefix=wksim-ap-clock-stop
candidate=$(mktemp -d "/root/$prefix-XXXXXX")
printf 'Candidate: %s\n' "$candidate"
cp -a --reflink=auto "$source_root" "$candidate/src"
git -C "$candidate/src" apply "$patch_file"
if [[ ${2:-} == --with-state || ${2:-} == --with-clock-stop ]]; then
    git -C "$candidate/src" apply --check "$state_patch"
    git -C "$candidate/src" apply "$state_patch"
fi
if [[ ${2:-} == --with-clock-stop ]]; then
    git -C "$candidate/src" apply --check "$clock_patch"
    git -C "$candidate/src" apply "$clock_patch"
    python3 "$repo/tools/validate_ap_json_clock.py" "$candidate"
fi
git -C "$candidate/src" diff --check
export PATH="$dds_work/src/Micro-XRCE-DDS-Gen/scripts:$PATH"
cd "$candidate/src"
./waf configure --board sitl --enable-DDS --out "$candidate/build" > "$candidate/configure.log" 2>&1
./waf copter -j4 > "$candidate/build.log" 2>&1
if [[ ${2:-} == --with-clock-stop ]]; then
    # DDS schemas are unchanged: retain the independently pinned state overlay.
    sha256sum "$state_patch" "$clock_patch"
fi
sha256sum "$candidate/build/sitl/bin/arducopter" "$patch_file"
if [[ ${2:-} == --with-state ]]; then
    set +u
    source /opt/ros/humble/setup.bash
    set -u
    colcon --log-base "$candidate/ros-log" build --base-paths "$candidate/src/Tools/ros2/ardupilot_msgs" \
        --build-base "$candidate/ros-build" --install-base "$candidate/ros-install" \
        --cmake-args -DBUILD_TESTING=OFF > "$candidate/ros-build.log" 2>&1
    sha256sum "$state_patch"
    printf 'Overlay: %s/ros-install/local_setup.bash\n' "$candidate"
fi
printf 'Candidate build complete: %s\n' "$candidate"
