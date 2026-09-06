# Local QGroundControl launch assessment

Assessment date: 2026-09-06 JST. Scope: #42 launcher-preparation sidecar,
supporting `docs/plan/tickets/32-qgc-handoff.md`; this is not full #42 acceptance.

Follow-up: [historical CLI/settings and Qt5.15.2 evidence](2026-09-06_qgc-isolation-research.md) now supplements this assessment. Six sampled upstream releases still do not establish a supported isolated launch for the unknown vendor build. No QGC launch or product source change followed.

**Result: no verified supported isolated launch plan for the available executable.**
Do not launch it through the console. No launcher helper or settings file was
created. This is the requested evidence-only outcome when settings isolation
cannot be verified, not a deferred implementation placeholder.

The required contract is a separate instance with its own new settings directory,
serial/Bluetooth/UDP discovery disabled, and exactly one explicit UDP link bound
to loopback port 14590 targeting 127.0.0.1:14591. Merely specifying that target
does not establish this contract.

## Read-only local inventory

| Candidate | Observed result |
| --- | --- |
| `E:/rflysimtools/QGroundControl/QGroundControl.exe` | Exists; 33,909,760 bytes; ProductName `QGroundControl`; OriginalFilename `QGroundControl.exe`; FileVersion and ProductVersion both `0.0.0.0`. Actual QGC release version remains unverified. |
| Adjacent `Qt5Core.dll` | Windows FileVersion `5.15.2.0`; dependency metadata, not a QGC version. |
| Windows uninstall registration | DisplayName `QGroundControl`; DisplayVersion, InstallLocation and DisplayIcon empty. UninstallString points to `D:\install\QGroundControl\QGroundControl-Uninstall.exe`. |
| `D:/install/QGroundControl/QGroundControl.exe` | `Test-Path` returned false. Registration is not evidence of a usable executable. |
| `C:/Program Files` and `C:/Program Files (x86)` | No QGroundControl-named candidate returned by directory inventory. Recursive inventory suppressed access errors, so this is not proof of absence in inaccessible directories. |
| `C:/Users/PC/Documents/odid编译/qgroundcontrol` | Recursive `QGroundControl.exe` inventory returned no executable. Source checkout is present. |

SHA256 of the RflySim executable, calculated with `Get-FileHash`:

```text
61F3C559FBB6401368981CC41030A23312D584F64A206D5D9B922C3813DA7BC9
```

No executable was run, including `--help` or `--version`. Version resources and
hash identify the observed file but do not prove its implementation matches the
source checkout. No binary patching, installation, browser/UI access, hardware
access, socket creation or network connection was performed.

## Inspected source evidence

All paths below are relative to the exact source root
`C:/Users/PC/Documents/odid编译/qgroundcontrol`.
HEAD: `7846c6db13c01d392d95a20b62a40fd8db20fd5e`;
`git describe`: `v5.1.4-2-g7846c6db1`.
Existing changes in `CLAUDE.md` and untracked `docs/agents/` were preserved.

| Source and line | Observed behavior and implication |
| --- | --- |
| `src/main.cc:13` | Parses arguments, initializes Platform, constructs QGCApplication, then initializes the app. |
| `src/Utilities/QGCCommandLineParser.cc:111` | Inspected option registration and parsing. No settings-file/settings-path option is registered. `--clear-settings` clears stored settings; it does not select another file. |
| `src/Utilities/QGCCommandLineParser.cc:206` and `src/Utilities/Platform/Platform.cc:288` | `--allow-multiple` bypasses the single-instance guard. It does not change settings identity or location. This flag is verified only in this source, not in the installed candidate. |
| `src/QGCApplication.cc:73` and `:95` | Normal application identity is fixed by build constants (daily builds have a separate fixed identity). Test/boot modes change identity but clear settings and run a different lifecycle; they are not a supported normal isolated GUI session. |
| `src/QGCApplication.cc:102` | Sets `QSettings::IniFormat`, then constructs default `QSettings`. This source uses default-location INI settings, not an explicit per-run settings file. Windows uninstall registration is unrelated to that choice. |
| `src/QGCApplication.cc:121` and `:132` | Clears settings on request/test boot or settings-version mismatch. Do not point an experiment at the user's existing settings or use `--clear-settings`. |
| `src/Comms/UDPLink.cc:106` | UDP settings load a local port and target host/port entries; this does not select a loopback bind address. |
| `src/Comms/UDPLink.cc:350` and `:368` | Binds `AnyIPv4` with `ReuseAddressHint | ShareAddress`, then attempts to join a multicast group. Target 127.0.0.1 does not restrict receiving to loopback or establish exclusive port ownership. |
| `src/Comms/UDPLink.cc:438` and `:478` | Receives datagrams and adds their sender addresses/ports to session targets. The write path also sends to session targets. A single configured peer is not an exclusive peer allowlist. |
| `src/Settings/AutoConnect.SettingsGroup.json:6` | UDP, Pixhawk, SiK, RTK, LibrePilot and ZeroConf discovery defaults include true values. NMEA has a separate source selector. An empty fresh profile would not disable discovery. |
| `src/Comms/LinkManager.cc:370` and `:428` | Loads saved link types, including Bluetooth, and their `auto` field. Preserving/copying an existing profile can retain automatic links. No Bluetooth-disable key is invented here. |

Literal search of `src/` found no `QSettings::setPath`, `settings-path` or
`settings-file` implementation. The inspected constructor and option parser are
the concrete basis for the unsupported-settings-file conclusion. Changing
APPDATA, HOME, XDG_CONFIG_HOME, the working directory, or supplying a portable
INI beside the executable has not been verified to redirect this Windows
candidate's settings; none is proposed as a launch workaround.

Codebase Memory `list_projects` and `index_status` verified project
`qgroundcontrol-v5.1.4-secure-link` and its root. Ranked graph searches located
the parser and UDP worker, then actual source was read. Searches were navigation,
not exhaustive symbol inventories. Exact coverage checks returned
`metadata_changed` for the cited files, with partial parse records for the C++
files; the graph snapshot is 2026-08-31. Findings above use current direct source
reads and literal searches, not graph completeness. The source/index was not
modified or rebuilt during this read-only assessment.

## Integration decision and validation

There is no approved command to hand to the shared console host. A preparation
helper that emitted an INI and `--allow-multiple` would incorrectly claim both
settings isolation and loopback-only behavior. The local executable additionally
lacks verified release/source correspondence. Therefore `qgc.py` and
`validation/test_wksim_console_qgc.py` were intentionally not created.

To reopen implementation, evidence must establish a locally available executable
with a supported normal-GUI settings isolation mechanism and a transport that
enforces the specified loopback/peer boundary without discovery. That evidence
must cover the actual executable and settings schema. Rebuilding/patching QGC or
introducing OS network isolation would require work outside this sidecar; neither
was done. A private SITL boundary by itself does not fix QGC's settings location
or wildcard receive socket.

Validation performed: read-only executable metadata/hash, registry and directory
inventory, source review, and Markdown patch whitespace check. No controlled
runtime tests were added because there is no runtime implementation. No process
or network tests ran, and port availability was not probed. Only this document
was written; user QGC settings, source checkout, shared runtime/config/console
host and GitHub issues were untouched by this sidecar.
