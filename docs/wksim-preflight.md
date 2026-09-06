# Candidate preflight v1 — issue #11

This reusable product entry checks one independent quad-X/native-DDS experiment before any flight controller is created. It imports no control node, runs no compiler or subprocess, initializes no DDS participant, and changes no host network. A successful result means the selected resources match the reviewed candidate; runtime still owns isolation, resource reservation, startup, estimator readiness and task completion.

## Contract

`Simulator.wksim_runtime.config.load_config(path) -> dict` reads strict JSON. `validate_config(data) -> dict` returns a copy, raising `ConfigError(ValueError)` for malformed or unsupported configuration. Unknown fields, duplicate JSON keys, NaN, unsupported model/stack/communication, traversal and unsafe run identifiers fail closed.

Required top-level fields: `schema_version=1`, explicit per-run `run_id`, `vehicle_id=1`, `stack=px4|arducopter`, `model_profile=quad_x`, `communication=native_dds`, absolute Linux `dds_workspace`, `prometheus_workspace`, `px4_root`; AP additionally requires `ap_candidate`. Run IDs are 1–64 ASCII letters/digits/underscore/hyphen, beginning with a letter or digit. Runtime must reserve their uniqueness; preflight does not reserve an output directory. Example IDs must be changed for each actual run.

Optional `capabilities` defaults to `["native_position_mission"]`. This is the only currently admitted request. The Full index rows are retained obligations, not automatic compatibility claims. Optional `model_library` must match the pinned library SHA256 and its sibling `build.json`; omission selects the existing baseline library. There is no implicit fallback when a baseline `/tmp` library has been removed.

Optional `display_socket` is a Unix datagram **receiver** pathname `/tmp/<directory containing run_id>/<socket>`, at most 107 UTF-8 bytes. Existing parent directories must be owned by the current UID with mode 0700 and not resolve through a symlink. Runtime may create a missing private parent. An existing Unix socket is allowed; ordinary files and symlinks are rejected. A missing relay is allowed. This field grants no host UDP/DDS mutation.

`Simulator.wksim_runtime.preflight.preflight(config) -> dict` always reports `ok`, `reasons` (each has stable `code` and human `message`), `identities`, `capabilities`, and `children_created=0`. Validated inputs appear in `config`; after model selection **`config.model_library` and `identities.model_library.path` identify the same resolved, checked file**. Runtime must use that file. Building another model requires separate verification before use; passing this check is not permission to substitute a different binary. `candidate_status` distinguishes implementation, build and historical flight provenance. `known_candidate` identifies the explicitly recorded built-but-unflown AP candidate when its binary is encountered.

CLI: `python3 -m Simulator.wksim_runtime.preflight CONFIG`. JSON goes to stdout; a concise conclusion and reasons go to stderr. Exit 0 admits, exit 2 rejects. API use does not mutate the caller's configuration. The separate runtime entry is `bash tools/run-wksim.sh CONFIG --output-root DIR` / `run(config, output_root)` and belongs to the runtime slice.

## Reviewed identities

The index pins the two existing flight result files by SHA256, then consumes their actual firmware, model build, installed Prometheus implementation and AP patched-source identities. Full resolved resource roots and hashes are both required; basename similarity never grants admission.

| Resource | Reviewed selection / SHA256 |
| --- | --- |
| Ubuntu / DDS / Prometheus | Ubuntu 22.04, ROS2 Humble; `/root/wksim-dds-VxM6Ni`, `/root/wksim-ros2-0viK3f` |
| AP firmware | `/root/wksim-ap-dds-yaw-state-4Wr27s/build/sitl/bin/arducopter`; `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5` |
| PX4 firmware | `/opt/aerotwinsim/src/px4-d6f12ad1/build/px4_sitl_default/bin/px4`; `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd` |
| AP Agent | DDS `ros-install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent`; `aa4f7a2a861958d7ae76ce6c8a866558b8baf73b5aad0a7b7fed1f8e17af9791` |
| PX4 Agent | DDS `agent-install/bin/MicroXRCEAgent`; `c61334626f2b625fdee68f7326ca1dabdf788b16d991a0e6879903cf24edb4b7` |
| Model library | `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`; AP `/tmp/wksim-model-bbwyws87/libwksim_model.so`, PX4 `/tmp/wksim-model-ndhnl3vz/libwksim_model.so` |
| Model source archive | `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`; local archive provenance, not redistribution permission |
| AP fresh candidate | `/root/wksim-ap-dds-yaw-fJUTtb`, built, **not flown/admitted**, binary `6e666bd73e5add95d3279fbfc08d0b4a47773cc2befaf14a49e70fb8d21c23b2` |

AP patch files 0001/0002 and 11 affected source hashes are checked. Seven installed `prometheus_control` files are checked against the flown implementation. Installed `ardupilot_msgs`/`px4_msgs` and `prometheus_msgs` use a 2026-09-05 read-only content snapshot: sort relative paths of `.py/.so/.msg/.srv/.idl` and versioned `.so.*` files, hash each file, then SHA256 the UTF-8 concatenation `relative_path + NUL + file_sha256 + LF`. This records schemas, generated Python and ELF type support while excluding mutable bytecode caches. The index stores these real snapshot hashes.

Python import origin, first ament package prefix, linker search path and already-imported package paths must resolve to the selected installation. This catches an AP overlay from another candidate even if its schema source is identical. The current snapshot strengthens admission but does not retroactively prove that every generated installation byte was recorded during the historical flight. Firmware flight capability remains limited to those two pinned result manifests and the six-input independent position scenario, including disarmed ground DDS reconnect.

## Actual checks, 2026-09-05

Run from the wksim checkout inside the selected Ubuntu distribution. These commands perform no flight and need no isolated flight slot:

```bash
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-0viK3f/install/local_setup.bash
python3 -m Simulator.wksim_runtime.preflight Simulator/wksim_runtime/examples/arducopter.json
WKSIM_PREFLIGHT_LIVE_RESOURCES=1 python3 -m unittest validation.test_wksim_preflight -v
```

Observed: AP admitted; eight tests passed, including real pinned-resource checks, fJUTtb rejection, wrong model contents, missing ament overlay, strict configuration, frozen index/evidence integrity, unsupported capabilities without subprocess creation, and existing/absent/unsafe display receiver cases. Tests create only their own temporary files and a private local Unix receiver, and remove them on completion.

In a fresh shell, source DDS and Prometheus only, then run:

```bash
python3 -m Simulator.wksim_runtime.preflight Simulator/wksim_runtime/examples/px4.json
```

Observed: PX4 admitted. Initial checking exposed the need for its separate `MicroXRCEAgent` identity; that path was corrected and the positive check passed.

Actual mixed-overlay negative, in a fresh shell:

```bash
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-fJUTtb/ros-install/local_setup.bash
source /root/wksim-ros2-0viK3f/install/local_setup.bash
python3 -m Simulator.wksim_runtime.preflight Simulator/wksim_runtime/examples/arducopter.json
```

Observed: rejected with `mixed_overlay` for Python, ament and the AP shared-library search paths; `children_created=0`. The correctly flown AP binary was still selected, proving this rejection is caused by the actually mixed message layer. Unit negatives separately select fJUTtb as firmware and reject its unflown identity.

## Remaining boundaries

The index has 87 rows: one admitted narrow mission, all 48 frozen Full expansion table rows (12 simulation modes, 7 communication modes, 16 model rows, 13 workflow/environment domains), and 38 ticket rows. Unknown build/flight status is `null`; unimplemented complete Full rows stay false even where a diagnostic subset exists. No Cartesian product of communication, firmware and model names is accepted. The frozen manual hash is `29da779803edaa15c8a751500e96a88243dfc6b71ed6c66e462bf228956143c3`.

The preflight worker launched no live SITL/UE. Main subsequently verified product issues#12/#17 with both exact pinned stacks; the four completed ticket rows now link to `validation/product-first-wave-20260905/manifest.json`. This status-only update admits no additional capability, changes no baseline identity, and does not mark complete Full rows as implemented. Eight real-resource preflight checks passed again after the status update; log `validation/product-first-wave-20260905/post-status-preflight.log`. The immutable earlier run manifests retain the capability snapshot seen at their own launch.

Joint time/dropout/airborne policy, MATLAB operations, plugin ABI and numerical budgets remain unestablished. Preflight reads mutable local files; it is not a signature authority or atomic filesystem snapshot. Runtime must use the checked paths and recheck hashes immediately before launch if resources could have changed. No vendor installation, upstream ROS1 source, existing process, commit or push was changed; approved issue publication and completion are recorded separately.
