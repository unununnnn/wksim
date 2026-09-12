# Ordered planner control frames

The existing v1 Bspline envelope and default decoder/pump behavior remain unchanged. Explicit `accept_control=True` on both decoder and pump enables control envelopes with schema `wksim.bspline-tcp-envelope.v2` and exactly `schema`, `transport_session_id`, `sequence`, `control`. Control payloads are `{"kind":"gate","open":true|false}`, `{"kind":"hold"}` or `{"kind":"cancel"}`. No anchor is accepted from the wire.

`encode_control_frame` and `encode_frame` share one encoder sequence. The opted-in decoder's `read_frame_any` returns a typed result from that same stream. The pump checks stable run/mission/UAV/epoch identity and current generation before changing a gate or session. Gate changes are idempotent and spend no session event; hold/cancel use the pump's shared event allocator and existing atomic session methods. A rejected session operation still consumes its valid transport frame, but does not consume a session event or change the gate/session. Generation changes retain the existing rule that the caller must supply a fresh identity before later buffered frames are processed.

Control mode starts with its gate closed. Recovery requires a new transport token and preserves the configured control mode, while resetting the gate closed. The v2 schema/field/kind values are included in the immutable protocol snapshot; changed public/private pins reject new construction and cannot rewrite existing instances.

The raw decoder has no poison latch: a v1-only read method leaves an unexpected control frame buffered; an opted-in typed reader can consume it. The pump separately latches POISONED after a transport error. A default v1 decoder rejects control frames and retains its single JSON parse per frame.

Main-agent verification: 202 tests across envelope, pump, session, adapter and command egress passed, including malformed identity, schema drift, opt-in recovery, mixed-stream sequence order and the v1 parse-count regression.

Control frames require explicit opt-in at both ends; the wiring below does not establish physical acceptance. A terminal planner session that stops publishing is not evidence that a real FC stopped its last P+V command. No trajectory-time gate or physics/freshness limit was changed.

The sender and transport node now have explicit control-mode wiring; the default
remains v1. On the sender, `~accept_control=true` enables the reviewed uav1 Bool
gate topic plus private `~hold` and `~cancel` Empty topics. Encoding and TCP writes
share one lock, a write failure retires the connection, and a sent terminal cancel
suppresses subsequent output. Callback lock order is the wire order; it is not a
guarantee of original publication order across ROS topics. Start the sender and
establish its subscriptions before enabling planner output. The sender still
has no transport ACK or automatic reconnect.

On the transport node, control mode requires explicit cancel/expected-native
modes. A consumed batch is folded before any publication, so a later gate-close
or stop suppresses an earlier activation in that batch. Gate-open alone cannot
resume an old trajectory. HOLD retains normal sampling; cancel waits for the
existing pending command ACK at the original sample boundary before requesting
release. Release observation uses the unchanged ROS operation clock and a 10s
deadline; switching production `use_sim_time` is rejected. Setup request IDs are
included in SessionState correlation and matched setup/revocation events are
routed through the release classifier.

Validation retained all original real-TCP regression tests. The combined
generated-message/callback/TCP suites passed 25 tests in an isolated ROS2
environment, including actual sender-core TCP bytes through hold/cancel and
public request assembly. A further 131 sender/receiver/codec/pump tests passed,
including blocked-write shutdown and concurrent frame ordering. ACKs in these
tests are synthetic; live ROS1 subscriber wiring and real FC release remain
unverified.

## Public release foundation

`PlannerCommandEgress.request_release` now uses the existing public SetupRequest
mode interface and the same request-id allocator as commands. It requires an
explicit setup publisher, requested/expected native modes, and current strict
ownership/freshness verdicts. Existing command pending state returns busy without
clearing that pending request or consuming another ID. A sent release prevents
further trajectory publication; setup events remain processable.

Allowed exit modes match ControlNode: BRAKE, POSCTL, AUTO.LOITER, AUTO.LAND and
AUTO.RTL. OFFBOARD is not a release mode. Confirmation requires a matching
successful `native_ack` followed by matching mode observation in
`setup_completed`; receipt alone is insufficient. ControlNode emits even a
negative native ACK as INFO, then emits its error/revocation separately. Matched
rejection/revocation and contradictory completion events fault; older setup
request events and foreign run/epoch events do not confirm the release.

`build_ros_mode_request` assembles the generated SetupRequest without publishing
or allocating IDs. Five valid mode variants and malformed identity/counter/time
inputs were checked with actual ROS2 serialization. The related pure suites pass
221 tests. Actual FC mode observation and live ROS1-to-public-control verification remain outstanding; this foundation is not a
physical cancellation result.
