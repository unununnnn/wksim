# #102 Bspline TCP Transport Envelope Contract

## 1. Context & Motivation

In the wksim simulation architecture, EGO planner trajectories generated in ROS 1 Noetic (WSL distro `RflySim-20.04`) must be transported across runtime boundaries into the ROS 2 Humble environment (`Ubuntu-22.04` and Windows host) for evaluation by `Simulator.wksim_planning.ego_bspline_bridge`.

An audit of the local environment established that:
- `ros1_bridge` is completely absent locally (no binaries in `/opt/ros/noetic` or `/opt/ros/humble`, no Debian packages, and no cached source).
- Installing or building `ros1_bridge` requires external network access and heavy workspace cross-compilation dependencies.
- The 8 fields of `prometheus_msgs/Bspline.msg` are identical in schema between ROS 1 and ROS 2.

To guarantee offline viability, deterministic execution, and auditability, ticket #102 introduces a dedicated Python TCP transport. This document defines the wire framing and envelope specification for the first pure offline, audited slice: `Simulator/wksim_runtime/bspline_tcp_envelope.py`.

---

## 2. Scope & Safety Boundaries

This envelope slice operates strictly under the following invariants:
1. **Pure Python, No ROS Imports**: Never imports `rospy` or `rclpy`.
2. **No Socket Execution**: Provides serialization, wire framing, stream buffer parsing, and validation without opening network sockets.
3. **No ID Minting**: Does not mint or invent `run_id`, `mission_id`, `epoch`, `request_id`, or `command_id`. Session identity is strictly limited to transport session tracking.
4. **No Time Mutation**: Does not shift, translate, or offset `start_time`. The timestamp instant is preserved exactly; only the structural representation is converted between ROS discrete components (`sec`, `nanosec`) and normalized integer nanoseconds.
5. **No Transport Pass Claims**: Does not claim socket, ROS master, DDS, or end-to-end transport passage.

---

## 3. Wire Framing Specification

Every message on the TCP stream is framed with a 4-byte big-endian unsigned length prefix (`>I`):

```
+-----------------------------+----------------------------------------------+
  | 4-Byte Length Header (>I)   | Variable-Length Payload (UTF-8 JSON bytes)   |
  | (0 < L <= 1,048,572 bytes)  | (L bytes)                                    |
+-----------------------------+----------------------------------------------+
```

### Framing Invariants:
- `MAX_FRAME_BYTES = 1,048,576` (1 MiB total frame cap).
- `MAX_PAYLOAD_BYTES = 1,048,572` (Payload cap excluding header).
- `MAX_BUFFER_BYTES = 2,097,152` (2 MiB streaming buffer cap).
- Header specifies the exact byte length of the UTF-8 JSON text.
- `L == 0` is invalid. `pack_frame()`, `unpack_frame_header()`,
  `decode_frame()`, and `feed()` reject it consistently with
  `invalid_frame_header`; no zero-length frame enters a decoder buffer.
- Frames shorter than declared length are rejected as `truncated_frame`.
- Data trailing a declared frame in single-frame decoding is rejected as `spliced_frame`.
- In streaming mode, `feed()` appends bytes to an internal buffer and `read_frame()` yields exactly one frame per invocation, cleanly handling multi-frame concatenation and chunked fragmentation. `feed()`, `decode_frame()`, `pack_frame()`, and `unpack_frame_header()` strictly reject non-bytes-like inputs with reason `invalid_frame_header`.
- **Poison frame recovery contract**: a frame that fails any validation stays at the head of the stream buffer and permanently blocks that decoder (head-of-line). No state (`expected_sequence`, high-water mark) advances, and appending further valid bytes cannot unblock it. Recovery REQUIRES discarding the decoder and its connection and establishing a new transport with a NEW `transport_session_id`; the new session's decoder rejects old-session frames with `session_mismatch`.

---

## 4. Envelope Schema & Pinned Metadata

The payload is a deterministic UTF-8 JSON object containing exact top-level fields:

```json
{
  "schema": "wksim.bspline-tcp-envelope.v1",
  "transport_session_id": "0123456789abcdef0123456789abcdef",
  "sequence": 1,
  "source_package": "prometheus_msgs",
  "source_msg_type": "prometheus_msgs/Bspline",
  "ros1_msg_sha256": "08ab59c600038eaff054bab381c48f3bf16c693a34007c64b8ba98b8a44ee706",
  "ros2_msg_sha256": "83922f2387a58be693aaad1f4d35d5421719e9288daa65ed5f48f27132c4dbe8",
  "payload": {
    "drone_id": 0,
    "order": 3,
    "traj_id": 1,
    "start_time": {
      "sec": 10,
      "nanosec": 5000000
    },
    "knots": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    "pos_pts": [
      {"x": 0.0, "y": 0.0, "z": 1.0},
      {"x": 0.5, "y": 0.0, "z": 1.0}
    ],
    "yaw_pts": [],
    "yaw_dt": 0.0
  }
}
```

### Field Definitions & Requirements:

| Field | Type | Invariants & Pinned Values |
|---|---|---|
| `schema` | string | Exactly `"wksim.bspline-tcp-envelope.v1"` |
| `transport_session_id` | string | Exactly 32 lowercase hex characters (`^[0-9a-f]{32}$`) |
| `sequence` | integer | Strictly monotonically increasing integer; mismatch or rewind rejected |
| `source_package` | string | Exactly `"prometheus_msgs"` |
| `source_msg_type` | string | Exactly `"prometheus_msgs/Bspline"` |
| `ros1_msg_sha256` | string | Exactly `08ab59c600038eaff054bab381c48f3bf16c693a34007c64b8ba98b8a44ee706` |
| `ros2_msg_sha256` | string | Exactly `83922f2387a58be693aaad1f4d35d5421719e9288daa65ed5f48f27132c4dbe8` |
| `payload` | object | Must contain exactly the 8 Bspline fields |

---

## 5. Bspline Payload Validation

All 8 fields from `prometheus_msgs/Bspline.msg` are strictly validated:

1. **`drone_id`**:
   - ROS type: `int32`.
   - Python type: strict `int` (non-bool).
   - Bounds: `-2,147,483,648 <= drone_id <= 2,147,483,647`.
2. **`order`**:
   - ROS type: `int32`.
   - Python type: strict `int` (non-bool).
   - Bounds: `1 <= order <= 2,147,483,647`.
3. **`traj_id`**:
   - ROS type: `int64`.
   - Python type: strict `int` (non-bool).
   - Bounds: `-9,223,372,036,854,775,808 <= traj_id <= 9,223,372,036,854,775,807`.
4. **`start_time`**:
   - ROS 1 input: accepts `{"secs": int, "nsecs": int}` or `{"sec": int, "nanosec": int}`.
   - Wire format: strictly `{"sec": int, "nanosec": int}`.
   - Bounds: `0 <= sec <= 2,147,483,647` and `0 <= nanosec < 1,000,000,000`.
   - Strict rejection of negative values, floats, booleans, and extraneous keys.
5. **`knots`**:
   - ROS type: `float64[]`.
   - Python container: strict list/tuple on input, strict list on wire.
   - Cardinality cap: `len(knots) <= 4,128` (`MAX_KNOTS`).
   - Elements: finite real numbers (no booleans, no `NaN`, no `+Inf`, no `-Inf`).
6. **`pos_pts`**:
   - ROS type: `geometry_msgs/Point[]`.
   - Python container: strict list/tuple on input, strict list on wire.
   - Cardinality cap: `len(pos_pts) <= 4,096` (`MAX_POINTS`).
   - Wire element: dictionary with exact keys `{"x", "y", "z"}`.
   - Coordinates: finite real numbers (no booleans, no `NaN`, no `+Inf`, no `-Inf`).
7. **`yaw_pts`**:
   - ROS type: `float64[]`.
   - Python container: strict list/tuple on input, strict list on wire.
   - Cardinality cap: `len(yaw_pts) <= 4,096` (`MAX_YAW_PTS`).
   - Elements: finite real numbers (no booleans, no `NaN`, no `+Inf`, no `-Inf`).
8. **`yaw_dt`**:
   - ROS type: `float64`.
   - Value: finite real number (no boolean, no `NaN`, no `+Inf`, no `-Inf`).

---

## 6. Bridge Mapping Transformation

When decoded on the ROS 2 / consumer side, the envelope payload is normalized into the dictionary expected by `Simulator/wksim_planning/ego_bspline_bridge.py::bridge_bspline`:

```python
{
    "drone_id": int,
    "order": int,
    "traj_id": int,
    "start_time": int,       # sec * 1_000_000_000 + nanosec
    "knots": List[float],
    "pos_pts": List[Tuple[float, float, float]],
    "yaw_pts": List[float],
    "yaw_dt": float,
}
```

This mapping matches `BSPLINE_FIELDS` and enables direct invocation of:
```python
spline, traj_id, start_tick = bridge_bspline(mapping, anchor_ns=anchor_ns, current_tick=current_tick)
```

**Downstream admission is narrower than envelope validity.** An envelope-valid payload is NOT automatically accepted by `ego_bspline_bridge`: the bridge independently enforces `drone_id == 0`, `order == 3`, `1 <= traj_id <= uint32 max` strictly increasing, empty `yaw_pts`, `yaw_dt == 0`, exact knot cardinality, and the authority-clock anchor/grid checks. The envelope guarantees transport fidelity only.

**Frozen identity discipline.** The pinned schema name, source package/type, both message SHA-256 values, frame/payload/buffer caps, payload array caps, integer bounds, nanosecond limit, session-id rule, exact payload fields, and exact envelope fields are captured into each encoder/decoder instance at construction; monkeypatching the module globals afterwards does not alter existing instances. The constructor's import-time captured defaults are the trust root: it also rejects mutations of both public and private module names and recomputes both repository `Bspline.msg` SHA-256 values, refusing to start on drift (`hash_mismatch`) or modified protocol constants. The stateless top-level helpers use the import-time field contract when no explicit field tuple or limit is passed. `BsplineEnvelopeError` likewise validates reasons against an import-time frozen tuple, so clearing or replacing the public/private reason names cannot make a stable error code fail with `ValueError`.

`to_bridge_mapping` is private (`_to_bridge_mapping`): it assumes an already-validated payload and does not re-validate. External callers must go through `BsplineTcpDecoder` (or `parse_and_validate_envelope`) so validation cannot be skipped.

---

## 7. Rejection Order & Error Reasons

The implementation raises `BsplineEnvelopeError(reason, message)` with stable machine-readable reasons:

| Reason Code | Trigger Condition |
|---|---|
| `invalid_frame_header` | Invalid input type or zero payload length (`L == 0`) |
| `truncated_frame` | Header shorter than 4 bytes, or received bytes fewer than declared payload length |
| `spliced_frame` | Unframed trailing bytes in single-frame decoder |
| `oversized_frame` | Header or payload exceeds 1 MiB, or stream buffer exceeds 2 MiB |
| `invalid_json` | UTF-8 decode error or JSON syntax error |
| `duplicate_key` | Any duplicate key in JSON object at any hierarchy level |
| `invalid_envelope_schema`| Missing/extra envelope keys or schema name mismatch |
| `invalid_session_id` | Session ID not 32 lowercase hex characters |
| `session_mismatch` | Received session ID does not match decoder session |
| `sequence_mismatch` | Sequence rewind, duplicate, gap, or negative integer |
| `invalid_source` | `source_package` or `source_msg_type` mismatch |
| `hash_mismatch` | ROS 1 or ROS 2 Bspline message file SHA-256 mismatch |
| `invalid_payload` | Missing/extra payload keys or invalid payload container |
| `invalid_field` | Integer out of range, boolean passed for number, or NaN/Inf |
| `invalid_time` | Invalid time keys, negative nanosec, nanosec >= 1e9, or non-int |
| `invalid_point` | Point missing/extra coordinates, non-dict on wire, or non-finite |
| `array_length_exceeded` | `knots`, `pos_pts`, or `yaw_pts` exceeds respective maximum length |

---

## 8. State API & High-Water Mark Semantics

Both `BsplineTcpEncoder` and `BsplineTcpDecoder` maintain explicit sequence state:

### Encoder State Invariant:
- `next_sequence`: Expected sequence number for the next frame.
- `high_water_sequence`: Sequence number of the last successfully encoded frame.
- **On Failure**: If payload validation or serialization fails, `next_sequence` and `high_water_sequence` do NOT advance.
- **On Success**: High-water mark advances exactly once (`high_water_sequence = next_sequence`, `next_sequence += 1`).

### Decoder State Invariant:
- `expected_sequence`: Expected sequence number for the next frame.
- `high_water_sequence`: Sequence number of the last successfully decoded frame.
- **On Failure**: If frame header, framing, JSON syntax, duplicate keys, session ID, sequence, hashes, or payload validation fails, `expected_sequence` and `high_water_sequence` do NOT advance.
- **On Success**: High-water mark advances exactly once (`high_water_sequence = expected_sequence`, `expected_sequence += 1`).

---

The test suite in `validation/test_bspline_tcp_envelope.py` validates this contract across 35 test cases (the original 17 plus the hardening regressions below):

1. `test_repository_message_hashes_pinned_and_exact`: Verifies repository `Bspline.msg` files match pinned hashes.
2. `test_no_ros_imports`: Verifies absence of `rospy` and `rclpy` in `sys.modules`.
3. `test_happy_path_roundtrip_and_bridge_execution`: Verifies encode -> wire -> decode -> `bridge_bspline` execution.
4. `test_wire_envelope_exact_metadata`: Verifies all envelope keys and wire formats.
5. `test_session_id_validation_strict`: Verifies 32 lowercase hex check and session mismatch rejection.
6. `test_sequence_monotonicity_and_high_water_invariants`: Verifies sequence rewind, duplicate, skip rejection, and state preservation.
7. `test_schema_and_source_and_hash_mismatches`: Verifies rejection of schema, package, and SHA-256 deviations.
8. `test_duplicate_json_keys_rejected`: Verifies duplicate key rejection at top, payload, and point levels.
9. `test_nan_and_inf_json_constants_rejected`: Verifies rejection of `NaN`, `Infinity`, `-Infinity`.
10. `test_boolean_rejection_for_integers_and_floats`: Verifies booleans are rejected for all numbers.
11. `test_integer_ranges_and_bounds`: Verifies `int32` and `int64` bounds.
12. `test_start_time_validation`: Verifies `0 <= nanosec < 1e9` and time normalization.
13. `test_point_coordinates_exactness`: Verifies exact `{"x", "y", "z"}` keys and coordinates.
14. `test_array_length_limits`: Verifies array size limits for points, knots, and yaw.
15. `test_frame_framing_truncation_splicing_and_oversize`: Verifies length prefix, truncated, spliced, and oversized frames.
16. `test_streaming_decoder_buffer_and_chunking`: Verifies stream chunking and multi-frame deframing.
17. `test_non_claims_and_no_mutation_boundary`: Verifies no ID minting and exact preservation of `start_time`.
18. `test_feed_rejects_non_bytes_with_stable_reason`: Non-bytes-like `feed()` chunks rejected with `invalid_frame_header`.
19. `test_pack_and_unpack_frame_header_reject_non_bytes_with_stable_reason`: Direct `pack_frame()` and `unpack_frame_header()` calls reject non-bytes-like inputs with `invalid_frame_header` without leaking `TypeError`; preserve `bytearray` and truncated/oversized classifications.
20. `test_monkeypatched_globals_do_not_change_existing_instances`: Construction-time message-hash snapshots immune to later module-global patches.
21. `test_zero_length_frame_rejected_consistently`: All frame construction, header parsing, standalone decode, and stream feed paths reject `L == 0` with the same reason.
22. `test_monkeypatched_globals_do_not_change_existing_instances`: Construction-time snapshots immune to later schema, frame, payload, buffer, and message-hash module-global patches.
23. `test_new_instances_reject_schema_and_size_pin_drift`: New instances refuse modified fixed schema and size pins, while message-hash drift remains covered separately.
24. `test_monkeypatched_globals_break_new_instance_construction`: New instances re-verify repository message hashes and refuse on drift.
25. `test_poison_frame_requires_new_session_recovery`: Poison frame permanently blocks; recovery only via new decoder + new `transport_session_id`.
26. `test_unvalidated_direct_mapping_bypass_is_not_public`: No public `to_bridge_mapping`; decoder cannot map without validation.
27. `test_decoder_enforces_instance_payload_cap_before_json_validation`: A 1,048,681-byte valid JSON value is rejected as `oversized_frame` before envelope validation, with decoder state unchanged.
28. `test_decoder_counts_utf8_bytes_for_string_payload_cap_and_rolls_back`: A multi-byte UTF-8 `str` is measured by encoded byte length and leaves sequence state unchanged on rejection.
29. `test_scalar_snapshot_immune_to_joint_global_monkeypatch`: Existing instances retain integer bounds, nanosecond conversion, and session validation after public/private global mutation.
30. `test_joint_private_and_public_pin_monkeypatch_rejected_for_new_instances`: New instances reject simultaneous mutation of public and private protocol pin names.
31. `test_field_snapshots_survive_joint_patch_and_reject_shape_errors_stably`: Existing instances retain exact field contracts after joint field/reason patching, and malformed shapes remain reason-coded.
32. `test_new_instances_reject_joint_field_pin_replacement`: New instances reject simultaneous replacement of public and private field pins.
33. `test_missing_and_extra_fields_never_leak_key_error`: Missing or extra payload/envelope fields fail before direct indexing with stable `BsplineEnvelopeError` reasons.
34. `test_reason_tuple_empty_does_not_change_new_instance_error_codes`: New instances and their errors remain usable after both public and private reason tuples are emptied.
35. `test_mixed_mapping_keys_never_leak_sort_or_key_errors`: Mixed `str`/`int`/`tuple` mapping keys in time, point, payload, and envelope validation remain stable `BsplineEnvelopeError` failures without `TypeError` or `KeyError` leaks.
