# Operator console contract — #18

Windows-only local desktop web console; Python standard library host plus local HTML/CSS/JS. Bind 127.0.0.1 only. No CDN, cloud service, copied vendor branding or browser-side flight controller. The host calls the unchanged formal WSL entry and cancellation contract. A closed browser does not stop or pace physics. The console does not silently adopt processes after server restart.

Visual direction: an operational workbench with clear configuration, live run, and recorded-evidence sections, not a marketing page. ui-ux-pro-max's two broad searches returned marketing navigation, so those unverified patterns are not persisted. Verified applicable advice: data-dense layout, high-contrast semantic tokens, keyboard focus, labelled fields, focusable error summary with field links, inline errors and reduced motion. Local system fonts (Segoe UI / Microsoft YaHei, Cascadia Mono), slate/white surfaces with restrained teal action emphasis; no web-font dependency. Layout adapts to 375px and 1440px without hiding controls.

## HTTP interface (version 1)

All paths below are same-origin. POST requires JSON and `X-Wksim-CSRF` with the token returned by bootstrap. Host and Origin are validated, responses are no-store and no-CORS, no user-selected executable or arbitrary file path is served. Malformed requests return `{error: string}` with non-2xx status. All timestamps retain their clock labels.

- `GET /api/bootstrap` → `{version:1, csrf, defaults:{px4:config, arducopter:config}, configs:[{name,revision,config}], runs:[run], data_root, ue_available}`.
- `POST /api/configs` with `{name,config,expected_revision:null|string}` → `{name,revision,config}`. Atomic compare-and-save. Strict existing configuration/mission validators. Reload uses bootstrap's saved entries. Saving or editing never starts a flight.
- `POST /api/preflight` with `{config}` → `run`. Async read-only WSL check. The returned id is its preflight ticket; poll `/api/runs/ID`.
- `POST /api/start` with `{config,preflight_id,with_view:boolean}` → `run`. Requires a successful check of that exact saved/form config. Formal runtime rechecks actual resources before flight. An actual new run_id is derived per launch; only execution identity/display socket differ from the immutable requested configuration. Concurrent starts from this console are rejected; independent CLI experiments remain supported.
- `GET /api/runs` → `{runs:[run]}`; `GET /api/runs/ID` → `run`.
- `POST /api/runs/ID/cancel` with `{mission_id}` → `{submitted:true,request}`. Current identity required. Cancel is not an immediate stop; only the formal Task determines landing completion.
- `POST /api/runs/ID/mission-action` with exactly `{mission_id,action_token,action:'pause'|'resume',control_epoch,native_generation}` → `{submitted:true,request}`. An owned running flight, currently live observation and unchanged action offer are required. Publication is neither native ACK nor task action completion.
- `POST /api/runs/ID/view` with `{action:'open'|'close'}` → view status. Own UE5.5 view only; may fail without stopping physics. View restart does not replay recorded truth.
- `GET /api/runs/ID/evidence?stream=prometheus&offset=0&limit=50` → `{records,diagnostics,total,offset,limit}`. Terminal experiments only; raw recorded events, not re-simulation. Stream choices: prometheus, dds, truth, telemetry. Empty/missing streams remain explicit.
- `GET /api/runs/ID/result` → `{format_version:1, values, raw_json, sha256, diagnostics}` from this console's known terminal run. `raw_json` retains the original report byte-for-byte as UTF-8 text; native NaN/Infinity (unknown telemetry) become explicit `{nonfinite:token}` markers only in `values`. The source is never rewritten. Required navigation values still reject nonfinite values. No arbitrary path parameter.
- `POST /api/shutdown` with `{}` → `{stopping:true}` only if no live owned job or view. Never kill an active flight from a server shutdown or browser close.

`run` has `{id,kind:'preflight'|'flight',status:'queued'|'running'|'pass'|'failed'|'cancelled'|'unowned',config,config_revision,run_id,directory,started_unix,finished_unix,error,result,live,view,phases}`. The last three may be null/empty during startup. `result` is the real preflight/runtime JSON, not a synthesized passing result. `live` contains raw public state/control and mission status, event tail, and `freshness` with status live/waiting/stale/recorded and labelled ages. `view` contains state starting/live/stale/stopped/failed/unavailable plus error and paths/actual Actor readback as available. A passing preflight is labelled candidate admission, never flight readiness. `pass` for a flight requires the formal result and zero process return code. An unowned historical in-progress record is never represented as a currently owned live process.

## Explicit mission pause/resume

`live.action_offer` is `{version:1, mission_id, action_token, control_epoch,
native_generation, allowed_actions, reason}`. Identities may be null when no
action can be offered. It is a conservative projection, not flight authority:
matching strict mission/native identity, valid armed state and actual
cross-poll source advancement are required. `takeover`/`running` may offer pause
only with observed COMMAND_CONTROL, OFFBOARD/GUIDED and no failsafe; `paused`
may offer resume. Transitions, terminal, stale, unknown and unowned runs do not
enable actions. Runtime validates its own current state again on consumption.

The dialog freezes job/run/mission/epoch/native generation/token/action. The
browser re-GETs the selected run and compares all fields before sending the
five-field POST. Selection changes, lost connectivity, stale feedback and
changed identities permanently invalidate that dialog; there is no token
upgrade. Browser receipt age uses its own monotonic `performance.now()` and a
2.5-second limit. It does not map Windows, WSL, FC boot or physics clocks.
Generations outside JavaScript's exact integer range cannot enable an action.
Server-side submission re-polls the actual reader and pins the same confirmed
epoch/generation through the existing atomic file-request helper.

Per-page records prevent duplicate activation. Buttons use native disabled and
aria-busy state. A valid response means only file submission. Confirmation
requires the original mission event and its exact nested request, including
request_id, mission/run/epoch/generation/token/action. Pause uses
`mission_pausing` → `mission_paused`; resume uses `mission_resume_received` →
`mission_resumed`. Known HTTP rejection is distinct from response loss/server
failure; unknown results are never automatically retried. Without the response
request_id, even same-token evidence stays unconfirmed. Records are page-memory
only: reload does not restore pending request receipt identity. Raw server
audit and runtime files remain retained.

Pause releases task output to PX4 AUTO.LOITER / ArduCopter BRAKE; physics and FC
continue. Resume explicitly requests a new takeover, then restores the recorded
ENU target and a full new dwell, including for BODY inputs. Cancel while paused
does not take control automatically: it waits for explicit resume to take over
and LAND (without further MOVE), or for the other owner to land. Browser/UE
close is not a mission cancel. Original native faults and stale feedback remain
fail-closed, not automatic recovery.

The Node DOM-double tests check logic only. Real HTTP/WSL flight acceptance is
also separate from real browser keyboard, screen-reader, dialog and layout
acceptance, which remains unverified under the current browser-policy limit.

When `with_view=true`, the async job first reports `queued` with `preparation.physics_started=false` while preparing the optional display. Physics/FC do not yet exist. Once the view is ready, failed, or explicitly closed, the formal runtime starts and performs its own preflight. This bounded preparation avoids a short mission finishing during UE cold startup. A failed viewer remains visible as such and does not prevent a headless flight. After launch, physics never waits for rendering; reopening a view attaches to the latest live state.

The P450 display build emits `WKSIM_STARTING` first. `WKSIM_READY` requires zero
pending asset compilation for at least three game ticks and a completed initial
RHI render-command fence, polled without blocking the game thread. This does not
promise sensor calibration or that every subsequent frame is readable. Captures
start only after readiness. Required model/material assets and their provenance
manifest are source/stage SHA256-pinned by preflight, alongside the UE DLL.

The default owned viewer uses the `desktop-balanced` profile: 30 FPS with shadow,
global-illumination, reflection and texture scalability level 1. It was tested
alongside the existing user editor on this machine's 8 GB GPU. No GPU warning is
suppressed and physics remains independent. The view contains original
Prometheus P450 body/rotor geometry, but still explicitly identifies its physics
as the existing quad-X test model, not calibrated P450 dynamics.

## Implementation ownership for this wave

Main: console workspace/orchestration, HTTP host, WSL preflight wrapper, integration and actual browser/dual-stack acceptance.
UI worker: `Simulator/wksim_console/web/` only. No direct filesystem/ROS operations and no fabricated run/trajectory/status fixtures in the shipped interface.
View worker: `Simulator/wksim_console/visual.py` and its test only; pinned UE plus existing product_bridge, no FC processes.
Records worker: `Simulator/wksim_console/records.py` and its test only; live log projection and existing offline evidence reader, no publishers.

All agents must explicitly use gpt-6-astra/low and have actual turn_context verified; no nested delegation. These write scopes prevent shared-file races. Schema changes return to main before code is written against a different interface.
