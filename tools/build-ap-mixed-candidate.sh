#!/usr/bin/env bash
# New isolated source/build only; no installation, admission or flight.
set -euo pipefail
[[ $# == 1 ]] || { echo 'Usage: build-ap-mixed-candidate.sh DDS_WORKSPACE' >&2; exit 2; }
dds_work=$(realpath -e -- "$1")
[[ "$dds_work" == /root/wksim-dds-VxM6Ni ]] || exit 2
[[ -x "$dds_work/src/Micro-XRCE-DDS-Gen/scripts/microxrceddsgen" ]] || exit 2
repo=$(realpath -e -- "$(dirname "$0")/..")
prepared=$(python3 -B "$repo/tools/prepare_ap_mixed_candidate.py" prepare)
candidate=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["candidate_root"])' <<< "$prepared")
source_checksum=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["manifest_sha256"])' <<< "$prepared")
[[ $(dirname "$candidate") == /root && $(basename "$candidate") == wksim-ap-mixed-* ]] || exit 2
printf 'Candidate: %s\n' "$candidate"
export PATH="$dds_work/src/Micro-XRCE-DDS-Gen/scripts:$PATH"
cd "$candidate/src"
./waf configure --board sitl --enable-DDS --out "$candidate/build" > "$candidate/configure.log" 2>&1
./waf copter -j4 > "$candidate/build.log" 2>&1
python3 -B "$repo/tools/prepare_ap_mixed_candidate.py" seal "$candidate" --source-sha256 "$source_checksum"
