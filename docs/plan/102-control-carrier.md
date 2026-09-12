# Ordered planner control frames

The existing v1 Bspline envelope and default decoder/pump behavior remain unchanged. Explicit `accept_control=True` on both decoder and pump enables control envelopes with schema `wksim.bspline-tcp-envelope.v2` and exactly `schema`, `transport_session_id`, `sequence`, `control`. Control payloads are `{"kind":"gate","open":true|false}`, `{"kind":"hold"}` or `{"kind":"cancel"}`. No anchor is accepted from the wire.

`encode_control_frame` and `encode_frame` share one encoder sequence. The opted-in decoder's `read_frame_any` returns a typed result from that same stream. The pump checks stable run/mission/UAV/epoch identity and current generation before changing a gate or session. Gate changes are idempotent and spend no session event; hold/cancel use the pump's shared event allocator and existing atomic session methods. A rejected session operation still consumes its valid transport frame, but does not consume a session event or change the gate/session. Generation changes retain the existing rule that the caller must supply a fresh identity before later buffered frames are processed.

Control mode starts with its gate closed. Recovery requires a new transport token and preserves the configured control mode, while resetting the gate closed. The v2 schema/field/kind values are included in the immutable protocol snapshot; changed public/private pins reject new construction and cannot rewrite existing instances.

The raw decoder has no poison latch: a v1-only read method leaves an unexpected control frame buffered; an opted-in typed reader can consume it. The pump separately latches POISONED after a transport error. A default v1 decoder rejects control frames and retains its single JSON parse per frame.

Main-agent verification: 202 tests across envelope, pump, session, adapter and command egress passed, including malformed identity, schema drift, opt-in recovery, mixed-stream sequence order and the v1 parse-count regression.

This does not enable control frames in the ROS1 sender or ROS2 transport node. Those integrations still need explicit mode selection and public stop/release ACK handling. A terminal planner session that stops publishing is not evidence that a real FC stopped its last P+V command. No trajectory-time gate or physics/freshness limit was changed.
