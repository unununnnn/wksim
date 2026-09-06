#!/usr/bin/env bash
# Minimal ROS2/DDS dependencies. Run prepare, review plan, then run install.
# No full-system upgrade, GUI, Gazebo, or global Agent source installation.
set -euo pipefail
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 22.04 ]] || { echo 'Requires Ubuntu 22.04' >&2; exit 1; }
[[ $(id -u) == 0 ]] || { echo 'Run as root inside the validation WSL distro' >&2; exit 1; }
[[ $(dpkg --print-architecture) == amd64 ]] || { echo 'Requires amd64' >&2; exit 1; }
phase=${1:-plan}
case "$phase" in prepare|plan|install) ;; *) echo 'Usage: bootstrap-humble-validation.sh prepare|plan|install' >&2; exit 2 ;; esac
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
evidence_dir=$(mktemp -d "$repo_dir/validation/humble-${phase}-XXXXXX")
exec > >(tee "$evidence_dir/output.log") 2>&1
printf 'phase=%s\nevidence=%s\nutc=%s\n' "$phase" "$evidence_dir" "$(date -u +%FT%TZ)"
dpkg --audit
apt-mark showhold

if [[ $phase == prepare ]]; then
    if ! dpkg-query -W -f='${Status}' ros2-apt-source 2>/dev/null | grep -q 'install ok installed'; then
        validation_tmp=$(mktemp -d /tmp/wksim-ros-source.XXXXXX)
        source_deb="$validation_tmp/ros2-apt-source.deb"
        curl --fail --location --retry 2 --connect-timeout 15 --max-time 120 \
            https://github.com/ros-infrastructure/ros-apt-source/releases/download/1.2.0/ros2-apt-source_1.2.0.jammy_all.deb \
            --output "$source_deb"
        printf '%s  %s\n' 767884cf4ed03116b9d64438930a832ed854147ae435279a7924dfdf60f94433 "$source_deb" | sha256sum --check --strict
        dpkg-deb --field "$source_deb" Package Version Architecture Depends
        apt-get -s --no-remove --no-install-recommends install "$source_deb" | tee "$evidence_dir/source-plan.log"
        if grep -Eq '^Remv |^Inst [^ ]+ \[' "$evidence_dir/source-plan.log"; then
            echo 'Source setup would remove or upgrade an existing package; review required' >&2
            exit 1
        fi
        DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-remove --no-install-recommends "$source_deb"
    fi
    dpkg-query -W -f='${Package} ${Version}\n' ros2-apt-source
    apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 \
        -o APT::Update::Error-Mode=any update
    exit 0
fi

packages=(ros-humble-ros-base ros-humble-rmw-fastrtps-cpp python3-colcon-common-extensions
          ros-humble-geographic-msgs ros-humble-micro-ros-msgs libspdlog-dev default-jdk-headless)
apt-get -s -V --no-remove --no-install-recommends install "${packages[@]}" > "$evidence_dir/packages-plan.log"
grep -E '^([0-9]+ upgraded|Remv |Inst [^ ]+ \[)' "$evidence_dir/packages-plan.log"
if grep -Eq '^Remv |^Inst [^ ]+ \[' "$evidence_dir/packages-plan.log"; then
    echo 'Plan would remove or upgrade existing packages; review required before expanding scope' >&2
    exit 1
fi
[[ $phase == plan ]] && exit 0
DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-remove --no-install-recommends "${packages[@]}"
# ROS setup scripts are not consistently nounset-safe; keep the caller's strict mode.
set +u
source /opt/ros/humble/setup.bash
set -u
ros2 pkg prefix rclcpp
ros2 pkg prefix rmw_fastrtps_cpp
ros2 pkg prefix geographic_msgs
ros2 pkg prefix micro_ros_msgs
javac -version
dpkg-query -W -f='${Package} ${Version}\n' "${packages[@]}" ros-humble-fastrtps ros-humble-fastcdr | tee "$evidence_dir/versions.txt"
