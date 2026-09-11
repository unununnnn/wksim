# #102/#39 ROS1→ROS2 Bspline transport: Route-B decision and offline prototype

Status: **offline Route-B prototype only.** This document records (a) the
read-only route determination for the next real ROS1→ROS2 Bspline transport under
#102, and (b) the boundary of the minimal offline prototype that instantiates the
chosen route. It does **not** close #102 or #39 and does **not** claim a ROS
master, DDS, a planner, SITL, UE, a flight, physical force response, crash
atomicity, an ACK, retransmission, or exactly-once delivery. The only thing
executed for this slice is the pure offline test suite (loopback `socketpair`);
no live ROS1 subscribe and no ROS2 control path were run.

## 1. Route decision: why Route B, why not Route A

Two routes were compared for moving one `Bspline` from the ROS1 planner side to
the ROS2/pure receive side.

**Route A — dynamic `ros1_bridge`.** EGO planner (`traj_utils/Bspline`) → the
committed `bspline_ros1_relay.py` (traj_utils→prometheus_msgs) → ROS1 topic →
`ros1_bridge dynamic_bridge` → ROS2 `prometheus_msgs/Bspline` →
`TrajectoryBridgeNode`. The message pair is field-compatible (ROS1 `time` ↔ ROS2
`builtin_interfaces/Time` is a builtin primitive mapping; the ROS1 relay is
internally consistent — both `traj_utils/Bspline` and `prometheus_msgs/Bspline`
generated with MD5 `4f7510f7be6fba2868a5e74dd6e8163b`). **Decisive blocker:
`ros1_bridge` is absent** from `/opt/ros/humble`, `/opt/ros/noetic`, and every
local overlay (confirmed by read-only inspection). Obtaining it needs network
plus a native cross-distro build (source Noetic + Humble, `colcon build` so the
custom message mapping registers). Both are forbidden by the task constraints.
**Route A is infeasible offline.**

**Route B — ROS1 TCP sender + pump receiver (SELECTED).** EGO planner
(`traj_utils/Bspline`) → `bspline_tcp_sender.py` (8-field extraction →
`BsplineTcpEncoder`) → the pinned `wksim.bspline-tcp-envelope.v1` byte stream
over TCP → `planner_transport_receiver.py` (`PlannerTransportPump.feed` →
admission → activation). Every dependency is already local; no `ros1_bridge`, no
DDS bridging, no cross-distro message registration, no native build, no network.
This is exactly the transport the committed envelope was built for.

## 2. Dataflow and the four files

```
ROS1/Noetic (planner host)                     ROS2-side / pure (this slice)
traj_utils/Bspline                             pinned wksim.bspline-tcp-envelope.v1
  └─ bspline_tcp_sender.py  ──TCP frames──▶    planner_transport_receiver.py
       build_payload (8 fields,                 │  recv() -> PlannerTransportPump.feed()
       start_time verbatim)                     │     ├─ BsplineTcpDecoder (transport ledger)
       encode_bspline_frame                     │     └─ TrajectorySceneAdmission (scene gate)
       (BsplineTcpEncoder)                      ▼  admission -> adapter.replan_and_activate
                                          TrajectorySession (activation only; no step/output)
```

| File | Role | ROS-free? |
| --- | --- | --- |
| `Modules/ego_planner_swarm/plan_manage/scripts/bspline_tcp_sender.py` | ROS1 origin. ROS-less testable core (`build_payload`, `encode_bspline_frame`); `rospy`/`socket` imports confined to `main()`. | core yes |
| `Simulator/wksim_runtime/planner_transport_receiver.py` | Pure receive loop. Injected socket → `pump.feed` → outcomes; poison latch; new-session `recover`. Never imports `socket`/binds/listens/connects. | yes |
| `validation/test_planner_transport_receiver.py` | Offline proof over loopback `socketpair`; frames produced via the sender so both halves are tested together. | yes |
| `docs/plan/102-ros1-ros2-transport-route.md` | this document | — |

The receiver reuses the committed `PlannerTransportPump` unchanged; it adds no
new transport, admission, or session logic.

## 3. The generation discipline (#102 critical correction)

The pump **never rewrites `planner_generation`**. The caller identity **must
carry the session's current generation**, and the pump rejects a stale or future
one (`generation_mismatch`) **before the decoder consumes a byte**
(`Simulator/wksim_runtime/planner_transport_pump.py::_check_feed_identity`, plus a
per-`read_frame` re-check that stops draining before consuming a frame on a
now-stale generation). The pump's current bounds are honored: `current_tick ∈
[0, 2**63-1]` (`invalid_tick`/`tick_regressed`), event sequence ≤ `MAX_COMMAND_ID`
(`sequence_exhausted`), session generation ≤ `MAX_GENERATION`
(`generation_exhausted`).

The receiver **requires** that identity. Its `poll`/`drain` take the **complete**
`Identity` — the stable tuple plus `planner_generation` and `command_high_water` —
from the caller on **every** call and pass it to the pump **unchanged**. The
receiver **never** reads the pump's `session_generation`/`command_high_water` to
fill in or overwrite the caller's identity (reading it to *build* the identity was
exactly the auto-stamping flaw this slice removes; that would re-break stale-caller
isolation). The only pump read the receiver performs is a **reject-only** pre-check:
before `poll`'s `recv` and before `drain`'s `feed(b"")` it mirrors the pump's
`_check_feed_identity` and raises `generation_mismatch` for a well-formed
stale/future generation **without** pulling bytes off the socket (a stale caller's
`recv` would otherwise consume bytes the pump then refuses, silently dropping them)
and without any decoder mutation. A malformed or stable-tuple-mismatched identity is
**not** pre-rejected there; it falls through to the pump, which preserves the
two-commit boundary by recording it as a consumed `rejected_identity`
(`transport_consumed=True, session_activated=False`). `command_high_water` is
**telemetry, not an identity gate**: `Identity.from_value` range-validates it and
the session uses it only to initialize its command counter, so the receiver passes
it through verbatim and never gates on it. This is the same caller pattern the pump
test uses (`current_identity(pump)`), now required of every receiver caller.

Because each activation advances the generation, a frame that arrived in the same
`recv` chunk as a prior activation stays buffered until a feed presents the new
generation. `receiver.drain()` performs that follow-up feed with **no** `recv`
(it feeds `b""`). A caller that has not yet refreshed its identity to the new
generation gets `generation_mismatch` from `drain` with **zero consumption** — the
buffered frame is flushed only after the caller explicitly re-reads the current
generation and presents it. After `recover`, the old generation is likewise rejected
with zero consumption on the new pump.

## 4. Boundaries

- **Identity.** Wire identity = `transport_session_id` + `SCHEMA_V1` + the two
  pinned `Bspline.msg` SHA-256 hashes (encoder/decoder re-verify them from the
  repository at construction). Sender and receiver must share the
  `transport_session_id`; a mismatch is a `session_mismatch` poison. The planner
  identity tuple is **not** on the wire — it is supplied at the receiver and
  enforced by admission; the caller supplies `planner_generation`/
  `command_high_water` explicitly on every `poll`/`drain` (the receiver passes them
  through unchanged and never fills them from the pump). Single-`uav_id=1`.
- **Clock.** The sender passes `start_time` through verbatim (ROS1
  `secs`/`nsecs`; no flatten/offset/rebase). It is flattened to integer
  nanoseconds only by the receiving decoder, and the admission bridge enforces
  the authority anchor / 1 ms-grid / not-in-past against the caller-supplied
  `current_tick`. The receiver reads **no** wall clock; `current_tick` is
  supplied per call. The authority-clock source (eventually ROS2 `/clock`) is a
  later slice.
- **Session (two-commit, inherited).** `read_frame()` commits the transport
  sequence high-water **first**; admission runs **second**. A frame can be
  transport-consumed yet never activate the session (`transport_consumed=True,
  session_activated=False`); `event_sequence` is spent only on activation. No
  crash atomicity, no exactly-once.
- **Poison.** Any envelope failure (frame > 1 MiB, buffer > 2 MiB,
  `hash_mismatch`, `session_mismatch`, sequence gap/dup, malformed JSON) latches
  terminal `POISONED`, blocks the decoder head-of-line, and refuses further
  bytes. The receiver checks the latch **before** any blocking `recv`.
- **Recovery.** Only via `receiver.recover(new_connection,
  transport_session_id=NEW)`, which delegates to `PlannerTransportPump.recover`:
  new transport session, `planner_generation + 1`, `command_high_water`
  preserved. A frame from the old transport session is poison to the recovered
  pump.
- **ACK / delivery.** The transport is **fire-and-forget**: **no ACK, no
  retransmission, no back-pressure, no feedback path to the sender.** The sender
  cannot learn of a receiver poison; a dead connection cannot be resumed on the
  same session. Recovery therefore requires an **operator-coordinated** restart
  of both ends with a **new** shared `transport_session_id`. The per-frame
  `FrameOutcome` ledger at the receiver is the only confirmation signal, and it
  is local to the receiver.

## 5. Cross-distro import / PYTHONPATH reality (honest)

- The sender lives in the `Modules` tree, which is a **PEP 420 namespace** (no
  `__init__.py`), not an installed package. It therefore inserts the repository
  root (derived from `__file__`, `parents[4]`) onto `sys.path` before importing
  `Simulator.wksim_runtime.bspline_tcp_envelope`. The envelope re-verifies the
  pinned message hashes against **that** repository, so the sender must run
  against a real checkout (in the Noetic distro, the mounted Windows repo, e.g.
  `/mnt/c/.../wksim`). Nothing is installed or vendored.
- The receiver sits inside the `Simulator` tree and imports the committed
  envelope/pump directly (repo root on `sys.path`).
- The offline receiver **test** self-inserts repo root and the sender's script
  directory, so it runs identically on Windows and both WSL distros with a bare
  `python3 validation/test_planner_transport_receiver.py`. (The older
  `test_planner_transport_pump.py` instead assumes repo root is already on
  `sys.path`, e.g. via `python -m pytest` from the repo root or
  `PYTHONPATH=.` — a pre-existing property, not introduced here.)
- **Not** exercised here: importing the real `traj_utils`/`prometheus_msgs`
  Python classes in the Noetic overlay, and importing `prometheus_msgs`/
  `wksim_msgs` under Humble. Those require sourcing the respective ROS
  environments and are part of the later live smoke, not this offline slice.

## 6. Dependencies present vs missing (read-only inspection)

| Dependency | State | Where |
| --- | --- | --- |
| `ros1_bridge` | **ABSENT** (both distros + all overlays) — removes Route A | — |
| Noetic `traj_utils`/`prometheus_msgs` `Bspline` Python classes (MD5 `4f7510f7…`) | present | `/root/wksim-msg-overlay-20260912-msgonly-01` (RflySim-20.04) |
| Humble `prometheus_msgs/Bspline` + `wksim_msgs` (`CommandRequest`/`SessionState`) + type support `.so` | present | `/root/wksim-ros2-launch-entry-20260911` (Ubuntu-22.04) |
| committed TCP envelope (`BsplineTcpEncoder/Decoder`, pins) | present | `Simulator/wksim_runtime/bspline_tcp_envelope.py` |
| receive-side pump + scene admission | present | `planner_transport_pump.py`, `ego_scene_admission.py` |
| ROS1 master + live EGO planner publishing `traj_utils/Bspline` | **not run** — reserved/isolated main-agent resource | — |
| ROS2 control path (`TrajectoryBridgeNode` → `CommandRequest`) | **not run** — later public-control slice (#39) | — |

## 7. Verification boundary

Run (offline, this slice): `validation/test_planner_transport_receiver.py` — 26
tests, pure, no socket-creation/ROS/master/DDS/SITL/UE/wall clock/external
network (loopback `socketpair` only). It passes on Windows and on both WSL
distros (RflySim-20.04 Python 3.10.12, Ubuntu-22.04 Python 3.10.12), together
with the unchanged `test_planner_transport_pump.py` (28 tests) and the committed
dependency suites.

- `SenderConversionTests` — 8-field extraction preserves `traj_id` and passes
  `start_time` through **unrewritten** (flattened to ns only at decode); both
  ROS1 `secs`/`nsecs` and `sec`/`nanosec` time forms accepted; round-trip through
  the real encoder→decoder; missing field rejected; ROS imports confined to
  `main()`.
- `ReceiverTransportTests` — single-frame activation over the socket;
  fragmentation completing exactly once; multi-frame flushed across the
  generation advance via `drain()`; a collision frame rejected
  `transport_consumed=True, session_activated=False`; poison latch →
  `receiver_poisoned` before any blocking `recv` → `recover` on a new
  connection/session admitting a fresh frame at `generation+1`; an old-session
  frame is poison to the recovered receiver.
- `ReceiverGenerationIsolationTests` — the #102 correction. A caller presents the
  complete `Identity` (generation + command high-water) on every call. A stale
  identity after activation makes `drain` raise `generation_mismatch` with **zero
  consumption** (the buffered frame survives and flushes only after an explicit
  refresh); a future and a stale generation make `poll` raise **before** `recv`
  so the socket bytes survive for a subsequent current-identity poll; a missing
  `planner_generation` defaults to 0 and is stale once past generation 0; a
  missing stable field is a **consumed** `rejected_identity` (two-commit
  boundary); `command_high_water` is telemetry, not a gate (a non-current
  in-range value still activates); after `recover` the old generation is rejected
  with zero consumption on the new pump.
- `ReceiverGuardTests` — invalid pump/socket/recv_bytes rejected; peer close →
  `connection_closed`; `recover` requires poison; pump protocol errors (e.g.
  `tick_regressed`) propagate unchanged; non-claims declared and no socket/ROS
  import or `bind`/`listen`/`connect` in the receiver.

Not run / not claimed: a live ROS1 subscribe, a ROS2 control path, a ROS master,
DDS, SITL, UE, a flight, force/impulse, Terrain15D, crash atomicity, an ACK,
retransmission, exactly-once delivery, or continuous-curve safety (the admission
gate's `sampled_segment_checked` / `continuous_proof=False` bound is inherited).
#102 and #39 remain open.
