# Native telemetry observation boundary

This is the implemented one-way foundation for [#42](https://github.com/unununnnn/wksim/issues/42),
not a GCS command connection, QGC UI acceptance, or completed control handoff.
The formal Prometheus DDS task remains the only task-control sender. The observer
does not issue MAVLink queries, heartbeats, mode changes, parameters or arming.

## Configuration and ownership

An otherwise admitted independent experiment can explicitly add:

```json
"telemetry_socket": "/tmp/<private directory containing this run_id>/native.sock"
```

The Linux directory is owned by the runtime UID, mode0700, without symlink
resolution. An existing receiver must be a same-UID Unix datagram socket with
mode0600. The UTF-8 path is at most107 bytes. It must differ from `display_socket`.
Reservations use the same global path/inode key space for both consumer types,
including across independent network namespaces. The receiver owns its socket;
the runtime does not remove or replace it. An absent receiver is allowed.

Inside the existing private Linux network/IPC/mount namespaces, the optional
observer exclusively binds loopback UDP14661 for PX4 or14660 for ArduCopter.
It accepts source system22 or241 respectively, component1. PX4 must come from
loopback18591. ArduCopter's source port is learned once from a valid native
ArduPilot heartbeat and cannot change within that observer process. These are
isolation/identity checks, not cryptographic MAVLink authentication.

The output uses an **unbound** Unix datagram socket and has no receive path.
The observer never sends to its input UDP socket. It cannot forward GCS commands
back into the flight controller. No host-network UDP socket, QGC, serial port,
Bluetooth device, hardware or external network is opened by this component.

Only when telemetry is selected, the pinned ArduCopter defaults additionally
load `Simulator/wksim_runtime/arducopter-telemetry.parm`: `MAV1_POSITION=10`,
`MAV1_EXTRA1=10`, `MAV1_EXTRA3=5`. These are stream rates only. The historical
core profile and its `SR0_*` entries are preserved; no control, health, failsafe,
physics, flight binary or installed ROS2 package is changed.

The DDS defaults file must remain LAST. In the fixed ArduCopter source,
`AP_Param::read_param_defaults_file` assigns `done_all_default_params` per file;
`load_object_from_eeprom` reloads dynamic defaults only when that flag is false.
Putting the already-resolved telemetry file last masked the unresolved, later
created DDS subtree. A real failed startup and a launch-plan regression caught
this. Reordering only the new file before `dds.parm` restored real DDS startup;
the upstream FC was not patched or rebuilt.

## Wire data, limits and lifecycle

Each output JSON object contains `schema_version=1`,
`kind=native_mavlink_observation`, run/vehicle/stack/system/component identity,
strictly increasing observer sequence, source endpoint, message IDs and
`packet_base64`. The decoded bytes are the original native UDP datagram, without
packing it again. A fresh dialect parser checks CRC, complete datagram consumption
and all contained messages' source identity. Unknown, corrupt, truncated,
oversized or mixed-identity data is rejected as a whole. ArduCopter's serial0
startup console text is separately counted as `non_mavlink` and never forwarded.

`observed_monotonic_s` and `observed_unix_s` are application-dequeue times. They
are **not** kernel arrival times, FC boot time, the authority clock or proof of
native state freshness. Native timestamps/units remain inside the original
messages. A future live consumer must apply its own run/sequence and state-age
checks; this stream alone must not be treated as a control-validity signal.

The observer drains at most64 UDP datagrams per poll, each at most8192 bytes.
Unix sends are nonblocking. Missing/full/disconnected receivers cause counted
drops, with no application retry queue or replay. Kernel queues remain bounded;
sequence gaps are expected. Reopening the same run's receiver gets newly sent
datagrams, not an application replay of packets discarded while absent.

A selected but invalid observer prevents FC startup. After its ready event,
observer exit is recorded in `result.json` but does not terminate physics,
the real FC, the native DDS Agent or the Prometheus task. Owned-child teardown
still applies at normal landed stop. A missing final observer report remains
explicitly null, not a fabricated success. Consumer traffic never determines
physics time.

## Exact local dialect build

The initially installed PyPI pymavlink2.4.49 did not know several messages from
the pinned PX4 firmware, including actual ESC_INFO290 packets. Selecting its
`common`, `development` or `all` modules did not solve that mismatch. The official
[pymavlink guide](https://mavlink.io/en/mavgen_python/) notes that PyPI's definitions
come from the ArduPilot fork and can differ from MAVLink/mavlink.

`tools/build_telemetry_dialects.py` uses the already present firmware XML and each
firmware's own pinned MAVLink/pymavlink generator submodules. It creates a NEW
output directory, validates XML with that generator's matching schema, checks
firmware/submodule identities and hashes inputs/outputs. It does not install or
upgrade global pymavlink. Local XML byte differences are accepted only when they
are exactly CRLF versus LF; no source file is rewritten.

```bash
python3 tools/build_telemetry_dialects.py /root/wksim-telemetry-dialects-NEW
```

That command produces a **candidate**, not an automatic runtime promotion.
Review its full `manifest.json`, then update the active
`Simulator/wksim_runtime/telemetry-dialects.json` with its path/hash and decoder
identities. The runtime verifies the full evidence hash, cross-checks selected
fields and executes the SHA256-checked generated Python bytes. It will not
silently fall back to another dialect if those artifacts disappear or differ.
The optional observer requires these local generated resources; the core flight
runtime without telemetry has no new decoder requirement. Generated libraries
remain local; their upstream inputs and generator provenance are in the build
manifest, not represented as new wksim-authored protocol definitions.

## Reproduce the real boundary gate

From the existing Windows workspace:

```powershell
wsl.exe -d Ubuntu-22.04 -u root -- python3 /mnt/c/Users/PC/Documents/odid编译/wksim/tools/validate_sitl_telemetry.py --stack both
```

The validator creates new configurations/evidence directories and receiver
sockets. The ordinary formal entry flies the unchanged three-waypoint mission.
The receiver detaches above2m, reopens after2wall seconds, verifies new native
packets, then terminates only the exact owned observation child. The task must
continue and normally land, with independent physical truth and process cleanup
evidence. The validator sends no MAVLink control commands and opens no QGC.

This gate is not proof that an arbitrary ground station is safe to launch.
See [the local QGC assessment](qgc-local-launch.md). Explicit relinquish/resume
of task control while keeping an experiment alive, and actual GCS interaction,
remain separate uncompleted requirements of #42.
