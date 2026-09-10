#!/usr/bin/env bash
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1
exec unshare --net --ipc --mount --propagation private bash -c '
set -eo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
repo=$1
shift
exec python3 -B "$repo/tools/run_gnss_flight.py" "$@"
' wksim "$repo" "$@"
