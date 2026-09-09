#!/usr/bin/env bash
# A fresh independent experiment owns its network, IPC, /dev/shm and /tmp.
set -euo pipefail
repo=$(realpath -e -- "$(dirname "$0")/..")
export PYTHONDONTWRITEBYTECODE=1
exec unshare --net --ipc --mount --propagation private bash -c '
set -eo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
repo=$1
shift
exec /usr/bin/python3 -B "$repo/tools/run_hex_flight.py" "$@"
' wksim "$repo" "$@"
