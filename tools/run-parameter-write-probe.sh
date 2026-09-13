#!/usr/bin/env bash
# runtime.run owns preflight, reservations, private /tmp and child teardown.
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}"
exec unshare --net --ipc --mount --propagation private bash -c '
set -euo pipefail
ip link set lo up
mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm
exec python3 -B -m tools.probe_parameter_write "$@"
' parameter-write "$@"
