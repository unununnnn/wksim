#!/usr/bin/env bash
# One private independent experiment. Requires Ubuntu-22.04 and CAP_SYS_ADMIN/root.
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}"
exec unshare --net --ipc --mount --propagation private bash -c '
set -euo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
exec python3 -m Simulator.wksim_runtime.runtime "$@"
' wksim "$@"
