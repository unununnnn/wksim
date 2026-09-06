#!/usr/bin/env bash
# Isolated pinned DDS toolchain. Existing PX4/AP builds are never overwritten.
set -euo pipefail
phase=${1:?Usage: build-dds-validation.sh fetch|runtime|firmware WORKSPACE}
dds_work=${2:?Pass the previously created /root/wksim-dds-* directory}
dds_work=$(realpath -e -- "$dds_work")
[[ $dds_work == /root/wksim-dds-* && -d $dds_work ]] || { echo 'Unexpected workspace' >&2; exit 2; }
case "$phase" in fetch|runtime|firmware) ;; *) echo 'Unknown build phase' >&2; exit 2 ;; esac
mkdir -p "$dds_work/src" "$dds_work/logs"
log_path=$(mktemp "$dds_work/logs/${phase}-XXXXXX.log")
exec > >(tee "$log_path") 2>&1
printf 'workspace=%s\nphase=%s\nlog=%s\nutc=%s\n' "$dds_work" "$phase" "$log_path" "$(date -u +%FT%TZ)"

fetch() {
    local name=$1 url=$2 commit=$3 target="$dds_work/src/$1"
    if [[ ! -e $target ]]; then
        git init --quiet "$target"
        git -C "$target" remote add origin "$url"
        git -C "$target" fetch --depth 1 origin "$commit"
        git -C "$target" checkout --detach FETCH_HEAD
    fi
    [[ $(git -C "$target" rev-parse HEAD) == "$commit" ]] || { echo "Wrong source revision: $target" >&2; exit 1; }
    git -C "$target" diff --exit-code
    git -C "$target" diff --cached --exit-code
    printf '%s %s\n' "$name" "$commit"
}

if [[ $phase == fetch ]]; then
    fetch Micro-XRCE-DDS-Agent https://github.com/eProsima/Micro-XRCE-DDS-Agent.git 57d086216d01ec43121845d385894a25987f8a2c
    fetch micro-ROS-Agent https://github.com/micro-ROS/micro-ROS-Agent.git c93ee764e0d2ef4907aeb29233c68cb5f4b56976
    fetch Micro-XRCE-DDS-Gen https://github.com/ArduPilot/Micro-XRCE-DDS-Gen.git b8840058b81c87e1169a5a0ed4744d7b3dc99e0b
    fetch px4_msgs https://github.com/PX4/px4_msgs.git 86d8239e962f6939e05c3737784f60c02fa884db
    if [[ ! -e "$dds_work/src/ardupilot" ]]; then
        # Preserve source, submodule metadata and cached build inputs in a private copy.
        cp -a --reflink=auto /root/wksim-dependencies/ardupilot-1511f271 "$dds_work/src/ardupilot"
    fi
    [[ $(git -C "$dds_work/src/ardupilot" rev-parse HEAD) == 1511f27194f1dcc3728270883047bdf022b3fd53 ]]
    exit 0
fi

set +u
source /opt/ros/humble/setup.bash
set -u

if [[ $phase == runtime ]]; then
    cmake -S "$dds_work/src/Micro-XRCE-DDS-Agent" -B "$dds_work/agent-build" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=/opt/ros/humble \
        -DCMAKE_INSTALL_PREFIX="$dds_work/agent-install" -DUAGENT_SUPERBUILD=OFF \
        -DUAGENT_USE_SYSTEM_FASTDDS=ON -DUAGENT_USE_SYSTEM_FASTCDR=ON -DUAGENT_USE_SYSTEM_LOGGER=ON \
        -DUAGENT_FAST_PROFILE=ON -DUAGENT_CED_PROFILE=OFF -DUAGENT_P2P_PROFILE=OFF \
        -DUAGENT_BUILD_TESTS=OFF -DUAGENT_BUILD_USAGE_EXAMPLES=OFF
    cmake --build "$dds_work/agent-build" --parallel 2
    cmake --install "$dds_work/agent-build"
    CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2 colcon --log-base "$dds_work/colcon-log" build \
        --base-paths "$dds_work/src/micro-ROS-Agent/micro_ros_agent" \
                     "$dds_work/src/ardupilot/Tools/ros2/ardupilot_msgs" "$dds_work/src/px4_msgs" \
        --build-base "$dds_work/colcon-build" --install-base "$dds_work/ros-install" \
        --packages-select micro_ros_agent ardupilot_msgs px4_msgs --executor sequential \
        --cmake-args -DBUILD_TESTING=OFF -DMICROROSAGENT_SUPERBUILD=OFF \
        "-DCMAKE_PREFIX_PATH=$dds_work/agent-install;/opt/ros/humble"
    LD_LIBRARY_PATH="$dds_work/agent-install/lib:${LD_LIBRARY_PATH:-}" ldd "$dds_work/agent-install/bin/MicroXRCEAgent"
    exit 0
fi

(cd "$dds_work/src/Micro-XRCE-DDS-Gen" && ./gradlew --no-daemon --max-workers=2 assemble)
export PATH="$dds_work/src/Micro-XRCE-DDS-Gen/scripts:$PATH"
cd "$dds_work/src/ardupilot"
./waf configure --board sitl --enable-DDS --out "$dds_work/ap-dds-build"
./waf copter -j2
sha256sum "$dds_work/ap-dds-build/sitl/bin/arducopter"
