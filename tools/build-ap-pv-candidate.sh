#!/usr/bin/env bash
# Explicit opt-in build; preparation alone is prepare_ap_pv_candidate.py.
set -euo pipefail
[[ $# == 1 ]] || { echo 'Usage: build-ap-pv-candidate.sh DDS_WORKSPACE' >&2; exit 2; }
dds_work=$(realpath -e -- "$1")
[[ $(dirname "$dds_work") == /root && $(basename "$dds_work") == wksim-dds-* ]] || exit 2
[[ -x "$dds_work/src/Micro-XRCE-DDS-Gen/scripts/microxrceddsgen" ]] || exit 2
repo=$(realpath -e -- "$(dirname "$0")/..")
prepared=$(python3 "$repo/tools/prepare_ap_pv_candidate.py")
candidate=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["candidate_root"])' <<< "$prepared")
[[ $(dirname "$candidate") == /root && $(basename "$candidate") == wksim-ap-pv-* ]] || exit 2
printf 'Candidate: %s\n' "$candidate"
export PATH="$dds_work/src/Micro-XRCE-DDS-Gen/scripts:$PATH"
cd "$candidate/src"
./waf configure --board sitl --enable-DDS --out "$candidate/build" > "$candidate/configure.log" 2>&1
./waf copter -j4 > "$candidate/build.log" 2>&1
sha256sum "$candidate/build/sitl/bin/arducopter" "$candidate/candidate.patch" "$candidate/pv-source.json" > "$candidate/build-sha256.txt"
printf 'Built, not admitted or installed: %s\n' "$candidate"
