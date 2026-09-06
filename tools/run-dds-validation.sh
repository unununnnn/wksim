#!/usr/bin/env bash
# Agents bind INADDR_ANY upstream. A private network namespace confines the
# entire validation (FCs, Agents, ROS nodes) without changing host firewall rules.
set -euo pipefail
stack=${1:?Usage: run-dds-validation.sh arducopter|px4|both DDS_WORKSPACE [single-stack options]}
dds_work=$(realpath -e -- "${2:?Missing DDS workspace}")
[[ $dds_work == /root/wksim-dds-* ]] || exit 2
case "$stack" in arducopter|px4|both) ;; *) exit 2 ;; esac
if [[ "$(readlink /proc/self/ns/net)" == "$(readlink /proc/1/ns/net)" ]]; then
    exec unshare --net bash "$0" "$@"
fi
ip link set lo up
set +u
source "$dds_work/ros-install/setup.bash"
set -u
export LD_LIBRARY_PATH="$dds_work/agent-install/lib:${LD_LIBRARY_PATH:-}"
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1
if [[ $stack == both ]]; then
    [[ $# == 2 ]] || { echo "Additional diagnostic options require a single stack" >&2; exit 2; }
    exec python3 "$(dirname "$0")/validate_dual_dds.py" "$dds_work"
fi
shift 2
exec python3 "$(dirname "$0")/validate_sitl_physics.py" --stack "$stack" --dds-workspace "$dds_work" "$@"
