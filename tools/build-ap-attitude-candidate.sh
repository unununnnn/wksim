#!/usr/bin/env bash
# Isolated native and message builds only; no admission or flight.
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
dds=/root/wksim-dds-VxM6Ni
export PATH="$dds/src/Micro-XRCE-DDS-Gen/scripts:$PATH"
prepared=$(python3 -B "$repo/tools/prepare_ap_attitude_candidate.py")
candidate=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["candidate_root"])' <<< "$prepared")
printf '%s\n' "$prepared"
printf '%s\n' "$prepared" > "$candidate/prepared.json"
cp "$0" "$candidate/build-ap-attitude-candidate.sh"
printf '%s\n' "$$" > "$candidate/build.pid"
cd "$candidate/src"
./waf configure --board sitl --enable-DDS --out "$candidate/build" --extra-hwdef "$candidate/attitude-extra.hwdef" > "$candidate/configure.log" 2>&1
./waf copter -j4 > "$candidate/build.log" 2>&1
printf '0\n' > "$candidate/native-build.exit"
msgs=$(mktemp -d /root/wksim-ap-attitude-msgs-XXXXXXXX)
printf '%s\n' "$msgs" > "$candidate/messages-root.txt"
mkdir "$msgs/src"
cp -a "$candidate/src/Tools/ros2/ardupilot_msgs" "$msgs/src/"
set +u
source /opt/ros/humble/setup.bash
set -u
cd "$msgs"
colcon --log-base "$msgs/log" build --base-paths "$msgs/src" --build-base "$msgs/build" --install-base "$msgs/install" --parallel-workers 1 > "$candidate/messages-build.log" 2>&1
printf '0\n' > "$candidate/messages-build.exit"
printf 'Built candidate: %s\nMessages: %s\n' "$candidate" "$msgs"
