# QGC settings and autoconnect containment: bounded supplement

Date: 2026-09-06 JST. Related: [GitHub #42](https://github.com/unununnnn/wksim/issues/42). Read alongside [the existing local launch assessment](qgc-local-launch.md); this note answers its remaining historical CLI/settings gap, without repeating the local inventory or current-source UDP audit.

**Result: no concrete supported isolated normal-GUI launch route has been established for the installed vendor executable.** The historical upstream sources do not supply the missing `--settings-file` facility. Consequently this research does not satisfy the main agent's condition for adding a host telemetry transport for QGC. This is a bounded research result, not a production policy or completion of #42.

## Evidence boundary

The parent and wksim AGENTS, context map/context, issue #1, issue #42 and its comments, research skill, and prior launch assessment were read. No wksim ADR directory exists. The research skill's primary-source/single-note workflow was followed directly; the explicit no-nested-agents instruction overrides its background-agent step. No agent was delegated. No product, executable, settings, firewall, installation, GUI/browser automation, or local runtime was changed or launched. Remote official text was read over HTTPS without saving source downloads. Only this note was written.

Local facts are inherited from the main agent/prior assessment, not independently remeasured here: `E:/rflysimtools/QGroundControl/QGroundControl.exe`, size 33,909,760, product/file version `0.0.0.0`, SHA256 `61f3c559fbb6401368981cc41030a23312d584f64a206d5d9b922c3813da7bc9`; adjacent Qt5Core version `5.15.2.0`. These identify a file/dependency, not its QGC source revision. Main confirms `configData/Config.json` is RflySim VisionSensors camera configuration, not QGC link settings. Do not repurpose it.

## Historical release anchors

GitHub's official commit API resolved these tags during this investigation. The linked application sources, each version's `src/main.cc`, `src/QGCConfig.h`, and AutoConnect metadata/group implementation were inspected. Sampling these exact releases does **not** assert every intervening patch or vendor fork has identical behavior.

| Release / immutable application source | Commit | Settings schema version | ZeroConf metadata |
| --- | --- | --- | --- |
| [v3.5.0](https://github.com/mavlink/qgroundcontrol/blob/88e67fbf076e3c0a4e6c102781ead8ae0f6f641a/src/QGCApplication.cc) | `88e67fbf076e3c0a4e6c102781ead8ae0f6f641a` | 8 | absent |
| [v4.0.0](https://github.com/mavlink/qgroundcontrol/blob/ec864809dbf5f7a51ada43a8e830ba858a8f55a3/src/QGCApplication.cc) | `ec864809dbf5f7a51ada43a8e830ba858a8f55a3` | 9 | absent |
| [v4.1.0](https://github.com/mavlink/qgroundcontrol/blob/d24b9c4af2df0df857b96b042cb74646120c5b7c/src/QGCApplication.cc) | `d24b9c4af2df0df857b96b042cb74646120c5b7c` | 9 | absent |
| [v4.2.0](https://github.com/mavlink/qgroundcontrol/blob/cf9588a12ce9ace68cc6c2a6578caedabafcfad6/src/QGCApplication.cc) | `cf9588a12ce9ace68cc6c2a6578caedabafcfad6` | 9 | present, true |
| [v4.3.0](https://github.com/mavlink/qgroundcontrol/blob/83d9a3c3e832f939ec39f6e14cb8bac9ccacc3da/src/QGCApplication.cc) | `83d9a3c3e832f939ec39f6e14cb8bac9ccacc3da` | 9 | present, true |
| [v4.4.0](https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/QGCApplication.cc) | `15bdfd5f16562a09ccb1a57808ed0405049645a7` | 9 | present, true |

Metadata endpoints: [3.5](https://github.com/mavlink/qgroundcontrol/blob/88e67fbf076e3c0a4e6c102781ead8ae0f6f641a/src/Settings/AutoConnect.SettingsGroup.json), [4.0](https://github.com/mavlink/qgroundcontrol/blob/ec864809dbf5f7a51ada43a8e830ba858a8f55a3/src/Settings/AutoConnect.SettingsGroup.json), [4.1](https://github.com/mavlink/qgroundcontrol/blob/d24b9c4af2df0df857b96b042cb74646120c5b7c/src/Settings/AutoConnect.SettingsGroup.json), [4.2](https://github.com/mavlink/qgroundcontrol/blob/cf9588a12ce9ace68cc6c2a6578caedabafcfad6/src/Settings/AutoConnect.SettingsGroup.json), [4.3](https://github.com/mavlink/qgroundcontrol/blob/83d9a3c3e832f939ec39f6e14cb8bac9ccacc3da/src/Settings/AutoConnect.SettingsGroup.json), [4.4][metadata]. Schema constants are in each pinned revision's `src/QGCConfig.h` ([4.4 example][config]). Absence of a metadata key alone does not prove absence of all discovery code in an older/custom build.

## Exact CLI and migration findings

- `--settings-file`: no registration or explicit settings-file selection exists in the inspected application/main startup paths in these six releases. They select application/organization identity, set `QSettings::IniFormat`, then construct default `QSettings`. No supported syntax for this proposed flag can be supplied. This scoped negative finding is not a binary-wide/vendor-fork proof. In the [4.4 parser][parser], unknown options are not rejected by this parser; silence or a normally opened window cannot establish successful isolation.
- `--clear-settings`: a boolean action, not a path selector. It clears the selected settings and recursively removes/recreates the parameter cache. `--clear-cache` separately removes parameter/airframe caches. `DeleteAllSettingsNextBoot` is tested with `contains`, so even a present false value triggers clearing in these startup paths. Do not supply these flags or that marker for an isolation test. [Startup][app]
- Startup compares `SettingsVersion` with the compiled schema and clears on mismatch. v3.5.0/v4.0.0 also clear a nonempty store with no version key; v4.1.0–v4.4.0 inspected constructors omit that missing-key branch. Thus a hand-seeded older profile can lose all suppression keys before links start. An empty profile also restores auto-connect defaults. Never guess the vendor schema from Qt's version. [Release sources above; 4.4 constant][config]
- `--unittest` and `--unittest:<selection>` are parsed under `QT_DEBUG`; executing the test suite additionally depends on `UNITTEST_BUILD`. They change application identity to an `_unittest` name and clear settings; these are test lifecycle controls, not a supported isolated normal GUI. A release build can leave the flag ineffective. [4.4 main][main], [application][app]
- `--logging:full` or `--logging:LinkManagerLog,MultiVehicleManagerLog` use a **colon within the same argument**. The parser does not consume a following value and does not implement `--logging=full`. Bare `--logging` sets a boolean but provides no categories. Category rules are comma-separated and applied after settings-based filters. These options enable diagnostics; they do not suppress connections. [Parser][parser], [filter implementation][logging], [official 4.4 logging guide](https://docs.qgroundcontrol.com/Stable_V4.4/en/qgc-user-guide/settings_view/console_logging.html)
- `--log-output` is a boolean, not an output-path argument. In 4.4, AppMessages opens `QGCConsole.log` under `AppSettings::crashSavePath()` with `WriteOnly | Text`; it is another write surface, not a private-log guarantee. [AppMessages][messages]

The newer local source comparison is already covered by `qgc-local-launch.md` at `7846c6db13c01d392d95a20b62a40fd8db20fd5e` (`v5.1.4-2`): no settings-file registration, and `--allow-multiple` only affects instance guarding. That prior finding is not newly revalidated here and is not evidence that the installed vendor file implements newer options.

## Autoconnect keys and paths: suppression is incomplete containment

All six sampled versions declare `AutoConnect` with persisted group **`LinkManager`**, not `[AutoConnect]`. The following are schema facts, **not an INI recipe approved for the vendor binary**. [Group implementation][group], [metadata][metadata]

| Persisted key | Observed default / purpose |
| --- | --- |
| `LinkManager/autoConnectUDP` | true; creates default MAVLink UDP link |
| `LinkManager/autoConnectPixhawk` | true; recognized flight-controller serial device |
| `LinkManager/autoConnectSiKRadio` | true; telemetry radio serial device |
| `LinkManager/autoConnectPX4Flow` | true; flow serial device |
| `LinkManager/autoConnectRTKGPS` | true; RTK receiver |
| `LinkManager/autoConnectLibrePilot` | true; recognized serial device |
| `LinkManager/autoConnectNmeaPort` | `Disabled`; separate NMEA source; `UDP Port` selects a network input |
| `LinkManager/autoConnectNmeaBaud` | 4800 |
| `LinkManager/nmeaUdpPort` | 14401 |
| `LinkManager/udpListenPort` | 14550 |
| `LinkManager/udpTargetHostIP`, `udpTargetHostPort` | empty address, port 14550; outgoing target, not a receive allowlist |
| `LinkManager/autoConnectZeroConf` | true in sampled 4.2–4.4 metadata; absent in sampled 3.5–4.1 metadata |

For the inspected **4.4 implementation**, `setToolbox()` starts a one-second timer; `_updateAutoConnectLinks()` invokes UDP, MAVLink forwarding, and ZeroConf helpers. ZeroConf discovers `_mavlink._udp` and `_mavlink._tcp`, constructs configurations and connects them. Turning off UDP alone therefore does not disable TCP discovery. No global `autoConnectTCP` or `autoConnectSerial` switch exists in the inspected AutoConnect schema. [LinkManager][links]

Saved links form another path: `LinkConfigurations/count`, `LinkConfigurations/LinkN/type`, `/name`, and `/auto` are loaded by `loadLinkConfigurationList()`; normal boot calls `startAutoConnectedLinks()`, which connects configurations marked automatic. Serial, UDP, TCP, and compiled-in Bluetooth are supported here. Device discovery flags do not replace clearing/validating the saved-link list **inside an already proven private profile**. No Bluetooth-disable key is invented. [Link root][linkroot], [LinkManager][links], [normal boot][app]

`_updateAutoConnectLinks()` returns early for suspended connections or unit testing, but those are internal state/lifecycle conditions, not an evidenced normal-launch CLI. On desktop builds with serial support, it calls `QGCSerialPortInfo::availablePorts()` before checking individual device enable flags. Setting all device flags false suppresses those automatic opens but does not stop USB/serial enumeration. NMEA selection and RTK handling need separate consideration. This is not a complete audit of every firmware-upgrade/plugin device path, so zero hardware access is not established. [LinkManager][links]

The 4.4 forwarding helper also consults root-level `forwardMavlink`; `App` uses the empty group. Telemetry saving (`telemetrySave`, `telemetrySaveNotArmed`) controls log persistence, not connection creation or receive-only operation. [App group](https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/Settings/AppSettings.cc), [App metadata](https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/Settings/App.SettingsGroup.json)

The existing wildcard/learned-peer concern also exists in historical 4.4: [UDPLink][udp] binds `AnyIPv4` with sharing flags, learns datagram senders, and sends to session targets. A loopback target or private upstream SITL consumer does not enforce QGC's receive boundary. No further general transport research was needed after reading the prior assessment.

## Qt 5.15.2: environment redirection does not close the gap

The exact upstream Qt tag resolves to `40143c189b7c1bf3c2058b77d00ea5c4e3be8b28`. Its Windows [QSettings implementation][qtsettings] obtains `FOLDERID_RoamingAppData` and `FOLDERID_ProgramData` through `SHGetKnownFolderPath` for default INI paths. The XDG environment branch is not this desktop Windows branch. Changing only child-process `APPDATA`, `LOCALAPPDATA`, `HOME`, `USERPROFILE`, or `XDG_CONFIG_HOME` is therefore **not an established redirection mechanism** for this QSettings path; environment-variable names resembling those folders do not change the API call's source of truth.

Qt offers explicit-filename construction and `QSettings::setPath()` APIs, but these are C++ APIs, not universal Qt launch flags. Organization/system fallbacks can also supply settings absent from the primary file. [Qt QSettings documentation](https://doc.qt.io/archives/qt-5.15/qsettings.html#fallback-mechanism)

[Qt's Windows QStandardPaths implementation][qtpaths] independently uses known folders for data/cache/config paths. Redirecting one settings object would not prove isolation of caches, crash logs or other file writes. Test-mode APIs are not a demonstrated normal QGC CLI remedy. A vendor-patched Qt DLL may differ; its version resource alone does not prove correspondence with upstream Qt source. No environment, registry, known-folder, or firewall changes were attempted.

## Safest next test and actual QGC evidence

The immediate next step is an **evidence check, not an executable launch**: use the main agent's existing metadata/package provenance to seek vendor documentation or matching source for this exact hash. It must establish a normal-GUI private settings mechanism, startup schema/migration behavior, discovery suppression, and the required loopback/fixed-peer transport boundary. This research found no command meeting those requirements. Do not probe unknown options with the executable, including `--help`, to infer containment from absence of an error. No installation/rebuild/OS-isolation workaround is proposed within this scope.

Only after a concrete route exists could a later separately scoped empty-session test record the actual settings location, untouched original profile, effective autoconnect settings, endpoints/peers, and device access. GUI/browser automation is currently unavailable; report that limitation and do not bypass it. The conditional host transport was not created because its intended QGC endpoint lacks this prerequisite; this is the current investigation boundary, not a claim that the user's overall migration implementation authorization has been withdrawn. A materially different QGC rebuild or OS-isolation plan needs an explicit scope decision before execution.

For a future contained session, actual evidence can come from **real PX4/ArduCopter SITL telemetry** on the existing receive boundary, never fabricated MAVLink. The desktop [MAVLink Inspector](https://docs.qgroundcontrol.com/Stable_V4.4/en/qgc-user-guide/analyze_view/mavlink_inspector.html) shows received messages, source components, rates and changing fields. Pair an actual QGC capture with system/component identity, HEARTBEAT autopilot/type and mode, timestamps, and matching native-run evidence; record AUTOPILOT_VERSION only if actually received. Link/vehicle diagnostic logs supplement this but do not prove the GUI rendered it. A replay of real recorded telemetry, if later used, must be labeled replay and cannot prove live connection/hand-off acceptance.

Ordinary QGC viewing is not silent: [MultiVehicleManager][vehicles] sends GCS heartbeats, and [InitialConnectStateMachine][initial] requests versions, parameters and plans. A `gcsHeartbeatEnabled` setting alone is not a transmit prohibition. No ARM, mode change, mission upload, calibration or hardware query is needed to demonstrate received identity; nevertheless automatic traffic must be prevented from reaching hardware by a proven boundary. Without that boundary, absence of operator commands is insufficient. No live QGC receive/UI evidence was collected here, and #42 remains unaccepted.

## Verification and remaining unknowns

Verified by direct official source reads: sampled CLI registrations, colon parser syntax, destructive clearing/migration paths, key groups/defaults, saved-link autostart, 4.4 enumeration/ZeroConf/forwarding paths, and Qt 5.15.2 Windows path selection. Documentation was checked against code; one attempted AppMessages path returned 404 and was corrected using the official tree to `src/QmlControls/AppMessages.cc`. No binary reverse engineering was used.

Unknown: vendor QGC commit/build flags/patches, exact settings identity/schema, vendor-specific supported isolation options, actual runtime endpoints/device access, and real GUI receive behavior. The authoritative gap is executable-to-source correspondence **plus** a supported containment mechanism; the hash, Qt version and this upstream survey do not supply either. Markdown whitespace/read-back verification is the only local validation appropriate to this one-file research change.

[app]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/QGCApplication.cc
[main]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/main.cc
[config]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/QGCConfig.h
[parser]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/CmdLineOptParser.cc
[logging]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/QGCLoggingCategory.cc
[messages]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/QmlControls/AppMessages.cc
[group]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/Settings/AutoConnectSettings.cc
[metadata]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/Settings/AutoConnect.SettingsGroup.json
[links]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/comm/LinkManager.cc
[linkroot]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/comm/LinkConfiguration.cc
[udp]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/comm/UDPLink.cc
[qtsettings]: https://github.com/qt/qtbase/blob/40143c189b7c1bf3c2058b77d00ea5c4e3be8b28/src/corelib/io/qsettings.cpp
[qtpaths]: https://github.com/qt/qtbase/blob/40143c189b7c1bf3c2058b77d00ea5c4e3be8b28/src/corelib/io/qstandardpaths_win.cpp
[vehicles]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/Vehicle/MultiVehicleManager.cc
[initial]: https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/Vehicle/InitialConnectStateMachine.cc
