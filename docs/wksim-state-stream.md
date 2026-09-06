# Single-vehicle product state stream (issue #17)

Product v2 comes directly from each autonomous core's `Model.step` output. It
does not tail `truth.jsonl`, consume DDS, generate trajectories, or send controls.
The existing `Simulator/ue55/bridge.py` and `tools/validate_ue55.py` remain v1
diagnostic regression tools and are not product acceptance entry points.

## Entry and wire contract

Both `Simulator.wksim_core.ap_json` and `px4_mavlink` accept optional
`--state-socket PATH --run-id ID --vehicle-id 1`. Their `serve` functions accept
the corresponding keyword-only `state_socket=None, run_id=None, vehicle_id=1`.
Absent socket configuration is a no-op; absent receiver or full receiver queue
drops that display sample and never terminates or waits the model. AP emits after
each newly advanced frame, not duplicate servo replies; PX4 emits after each
four-substep model result. Neither physics scheduling nor controls were changed.

The runtime entry is `bash tools/run-wksim.sh CONFIG --output-root DIR`.
Its optional `display_socket` config feeds the core flags. Use the same run ID
in config, bridge and UE; v2 accepts the runtime pattern
`[A-Za-z0-9][A-Za-z0-9_-]{0,63}`. Vehicle ID is JSON integer `1`, not the flight
stack name. A new run needs a new ID; sequence and simulation time reset only
with a new run. Relaunch UE with that new identity.

Each UTF-8 JSON datagram is at most 4096 bytes:

| Field | v2 constraint |
| --- | --- |
| `version` | integer 2 |
| `run_id`, `vehicle_id` | exact selected run, integer 1 |
| `sequence` | core emission ordinal, integer 1..2^53−1; gaps are expected |
| `sim_time_s` | actual model time, finite nonnegative; strictly increasing |
| `source_wall_time_s` | source Unix UTC seconds; freshness only, never simulation time |
| `position_ned_m` | three finite numbers, absolute values ≤10^6 |
| `quaternion_wxyz` | four finite numbers, norm squared within 10^-5 of one |
| `rotor_rpm` | four finite numbers in [0,100000] |
| conventions | `position_frame=NED`, `position_unit=m`, `quaternion_order=WXYZ`, `body_frame=FRD`, `rotor_unit=rpm`, `configuration=quad-X`, `rotor_order=[FR,RL,FL,RR]` |

Relay, Windows bridge and UE reject wrong run/vehicle/version/conventions,
malformed physical fields, non-increasing sequence/time, and expired samples.
Source age is checked on the WSL clock against the relay's response timestamp.
The Windows bridge adds the full measured monotonic request/response roundtrip
to bound transport age, then adds `display_wall_time_s` and
`display_clock=windows_utc_bound` for UE's same-host freshness check. The original
source wall time and simulation time are never rewritten. Maximum age remains
0.75s; delayed requests are dropped. WSL/Windows UTC equality is not assumed:
real integration observed a 1.4s offset and the former direct comparison rejected
fresh state. This view-only age bound is not a joint clock, physics epoch,
airborne dropout policy or numerical budget.
Excessive same-host age or transport delay fails closed (STALE); source model
time is never rewritten. UE expires the bounded Windows display stamp, so
transport delay cannot extend LIVE.

## Transport and ownership

The relay binds a **pathname** AF_UNIX datagram socket in the WSL host network
namespace. Linux pathname sockets remain reachable from the FC's private network
namespace through the shared filesystem; abstract sockets are not used. DDS stays
inside the original private namespace/domain77. No WSL IP listener, Windows
firewall opening or DDS exposure is needed.

The socket must be directly inside a real directory under Linux `/tmp`, owned by
the relay user with mode0700; total path length ≤107 UTF-8 bytes. Use a directory
containing the run ID for runtime preflight compatibility. Relay rejects symlink
parents, existing socket/file/symlink paths and nonprivate/nonlocal paths. Run
core and relay as the same WSL user. The relay never replaces an existing endpoint
and unlinks only the socket inode it created on normal EOF/exit. After an abrupt
kill use a fresh private path or have the run owner inspect its abandoned socket;
do not remove another running relay's endpoint. Identity filtering is not remote
authentication; the directory is the local ownership boundary.

The physics writer performs one nonblocking `sendto`, has no retry/history queue,
and counts drops. Relay stores one accepted state, drains at most256 packets per
iteration, and returns null if it cannot finish draining or its state expired.
Windows sends one `?` pull byte and waits for exactly one bounded JSON line over
`wsl.exe` pipes, then forwards at most50Hz to UE loopback. A stalled pipe can stop
relay draining; it cannot stop physics, which drops on a full Unix socket queue.
Reconnect starts at a fresh source packet; no old file is read or replayed.
UE ACKs are view-only and never flow to the core.

## Build and run in an isolated display slot

The final clock-bound product build uses a fresh project at
`E:/ue5.5/build/wksim-native-state-v2-clockbound-20260905`. Actual command:

```powershell
Set-Location -LiteralPath 'C:/Users/PC/Documents/odid编译/wksim'
./tools/build-ue55.ps1 -Stage 'E:/ue5.5/build/wksim-native-state-v2-clockbound-20260905'
```

Build evidence: `validation/ue55-build-03234a38/manifest.json` and `build.log`.
Build passed (exit0, 33.60s). The 8 source/staging inputs match byte-for-byte;
`Simulator/ue55/state-build-manifest.json` records those hashes, Python sources,
tests and DLL SHA256 `8ff466fbd1eb6489b7e8ac29209bbb7885cf7c876ee97dbcc314ebf41dc00b4a`.
MSVC14.51 was reported nonpreferred and UE headers emitted deprecation warnings;
neither prevented compilation/linking.
Use its new `WksimVisual.uproject` and `Binaries/Win64/UnrealEditor-WksimVisual.dll`;
the old v1 diagnostic stage does not implement product v2. The first v2 build
was retained separately at `validation/ue55-build-d6cb0df0`; it predates the
cross-host clock correction and is not the final acceptance binary.

For a live slot, read the already prepared runtime config in PowerShell
(set `$configPath` to its Windows path). The runtime config must specify
`display_socket`; prepare its private parent directory as the same WSL user
before starting the bridge. Do not derive a separate bridge run ID.

```powershell
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$runId = $config.run_id
$socketPath = $config.display_socket
$socketDirectory = $socketPath.Substring(0, $socketPath.LastIndexOf('/'))
wsl.exe -d Ubuntu-22.04 --exec mkdir -m 700 -- $socketDirectory

$stage = 'E:/ue5.5/build/wksim-native-state-v2-clockbound-20260905'
$project = "$stage/WksimVisual.uproject"
$engine = 'E:/ue5.5/files/UE_5.5/Engine/Binaries/Win64/UnrealEditor.exe'
$ueArgs = @(('"{0}"' -f $project),
    '/Game/Maps/UrbanBlock?game=/Script/WksimVisual.WksimVisualGameMode',
    '-game', '-windowed', '-ResX=1280', '-ResY=720', '-NoSound', '-NoSplash', '-unattended',
    '-ExecCmds="t.IdleWhenNotForeground 0,t.MaxFPS 30"',
    "-WksimRunId=$runId", '-WksimVehicle=1', '-WksimPort=19060')
$ueProcess = Start-Process -FilePath $engine -ArgumentList $ueArgs -WorkingDirectory $stage -WindowStyle Hidden -PassThru

& 'D:/date/miniconda/python.exe' -m Simulator.ue55.product_bridge `
    --wsl-repo '/mnt/c/Users/PC/Documents/odid编译/wksim' `
    --state-socket $socketPath --run-id $runId --vehicle-id 1 --port 19060
```

Run the approved runtime entry in a separate WSL shell with the same config.
The bridge may start before or after the core. Add `--readback NEW_FILE.jsonl`
to record up to64 pending correlated source/actual Actor ACK comparisons;
these diagnostics are output only. Add UE `-abslog=...` and
`-WksimCaptureDir=...` for main's screenshot/evidence directory. Stop only owned
bridge/UE processes after acceptance, never by global process name. The bridge
uses pipe EOF to ask its relay to close. An occupied UDP19060 is a resource
conflict: coordinate a free assigned port on both endpoints.

## Verification boundary

Offline command (no SITL/UE):

```powershell
wsl.exe -d Ubuntu-22.04 --cd '/mnt/c/Users/PC/Documents/odid编译/wksim' --exec python3 -m unittest validation.test_wksim_state_stream validation.test_ue55_bridge validation.test_wksim_core -v
```

The checks exercise real AF_UNIX socket absence/saturation/rebind, a fresh private
network namespace crossing, relay pull/coalescing/expiry/cleanup, malformed and
old-run rejection, identity/private-path rules and existing core/coordinate
regressions. They do not claim Windows pipe throughput or rendered flight success.
The final integrated suite passed80 checks without skips, including six stream
tests and two cross-host clock-bound checks; Windows ran the two bridge checks
separately. Both real product/UE runs now passed: ArduCopter874 and PX4 369
correlated actual Actor readbacks, rendered LIVE/STALE/recovery frames, ten
invalid probes per stack with zero accepted ACKs, and continued physics during
a three-second bridge-process interruption. See the [first-wave report](2026-09-05_product-first-wave-report.md)
and `validation/product-first-wave-20260905/audit.json` for exact identities,
commands, fixed thresholds and retained failures. The scripts tail diagnostics
only to observe acceptance; the UE input remains the core Unix state stream.
MATLAB, joint scenes/clocks/dropout policy, plugin ABI, vendor numerical
equivalence and final aircraft assets remain outside this slice.
