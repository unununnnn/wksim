"""Repeatable pure-Python comparator for the proven G6 first-step 13-state comparison.

Compares the reference run-03 observability JSON against the target first-step
trace (jsonl), reproducing the reviewed comparison-v2 semantics:

- same-time events are distinguished by their real sequence position (the two
  t=0.0005 observations are ordered, never merged);
- the final major state is the LAST t=0.001 record (the ode4 update / last
  PostOutputs), never the fourth-stage minor;
- exactly 4 stages + 1 update, exactly the 13 mapped rigid-body states
  (4 blocks: q0..q3, p,q,r, xe,ye,ze, ub,vb,wb; target indices fixed by the
  proven comparison-v2 mapping), all hex decoded as finite float64;
- missing/duplicate/out-of-order events, bad times, or invalid hex reject the
  alignment outright.

It never claims 36-state coverage, never claims G6/R1 passage, and reports
bitwise hex pairs plus ULP distances for every difference.

CLI:  compare_first_step_trace.py --reference R.json --target T.jsonl --output O.json
Both inputs are read exactly once (hashed from the same bytes that are parsed);
the output file is created exclusively and never overwrites history.
"""

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path


# Fixed C3G block -> target 36-vector slice mapping, provenance:
# validation/coordination/g6-target-first-step-20260913/comparison-v2.json
# (target_indices).  13 of 36 continuous states only.
BLOCK_MAP = (
    ("q0 q1 q2 q3", 6, 9),
    ("p,q,r", 10, 12),
    ("xe,ye,ze", 13, 15),
    ("ub,vb,wb", 16, 18),
)
MAPPED_STATES = 13
TOTAL_STATES = 36
EXPECTED_TIMES = (0.0, 0.0005, 0.0005, 0.001)
SOLVE_TIMES = (0.0, 0.0005, 0.0005, 0.001, 0.001)
SOLVE_MAJOR_FLAGS = (1, 0, 0, 0, 1)
PQR_DERIV_SLICE = (10, 13)  # p,q,r in the 36-wide target vector
EVENT_SEQUENCE = ("PreOutputs", "PostOutputs", "PreDerivatives", "PostDerivatives")
# The final boundary adds one more Pre/PostOutputs pair after the update.
FINAL_EXTRA = ("PreOutputs", "PostOutputs")


def _fail(reasons, message):
    reasons.append(message)


def decode_f64_hex(value):
    """Strict 16-hex-digit big-endian IEEE-754 double; must decode finite."""
    if not isinstance(value, str):
        raise ValueError("hex value must be a string")
    text = value[2:] if value.startswith("0x") else value
    number = struct.unpack(">d", bytes.fromhex(text))[0]
    if not math.isfinite(number):
        raise ValueError(f"non-finite f64: {value!r}")
    return number


def norm_hex(value):
    """Lowercase, prefix-free 16-digit f64 hex."""
    text = value[2:] if isinstance(value, str) and value.startswith("0x") else value
    return text.lower()


def ulp_distance(hex_a, hex_b):
    """ULP distance between two f64 hex strings; sign semantics are explicit:
    a sign flip (including +0.0 vs -0.0) has no meaningful ULP distance and is
    reported as None -- the hex pair itself is the evidence."""
    a = int.from_bytes(bytes.fromhex(norm_hex(hex_a)), "big")
    b = int.from_bytes(bytes.fromhex(norm_hex(hex_b)), "big")
    if (a >> 63) != (b >> 63):
        return None
    return abs(a - b)


def norm_block(path):
    return " ".join(str(path).split())


def block_terminal_name(path):
    """Terminal path segment of a block path; the declared integrator identity.
    No substring matching: a pseudo block whose path merely CONTAINS the name
    never matches."""
    normalized = norm_block(path)
    return normalized.split("/")[-1] if normalized else ""


def parse_reference(data):
    """Validate and index the reference observability events."""
    reasons = []
    if type(data) is not dict or type(data.get("events")) is not list:
        return {}, ["reference input must be a dict with an events list"]
    if type(data.get("event_count")) is not int or data.get("event_count") != len(data.get("events", [])):
        _fail(reasons, "reference event_count disagrees with the events list")
    if type(data.get("dropped_events")) is not int or data.get("dropped_events") != 0:
        _fail(reasons,
              f"reference dropped_events must be 0, got {data.get('dropped_events')!r}")
    events = data.get("events", [])
    if any(type(event) is not dict or type(event.get("time")) not in (int, float)
           or not math.isfinite(event["time"]) for event in events):
        return {}, reasons + ["reference events require objects with finite numeric times, not bool"]
    blocks = {}
    for key, _, _ in BLOCK_MAP:
        matched = [e for e in events
                   if block_terminal_name(e.get("block", "")) == key]
        if len({id(e) for e in matched}) == 0:
            _fail(reasons, f"reference block missing: {key}")
            continue
        blocks[key] = matched
    per_block = {}
    for key, lo, hi in BLOCK_MAP:
        rows = blocks.get(key)
        if rows is None:
            continue
        # Real callback order is the array order; same-time events keep their
        # sequence position and are never merged.
        sequence = [(e.get("event"), e.get("time")) for e in rows]
        expected = [(name, t) for t in EXPECTED_TIMES for name in EVENT_SEQUENCE]
        # The final boundary adds one more Pre/PostOutputs pair (the major
        # record) after the update's derivatives pair.
        expected += [(name, EXPECTED_TIMES[-1]) for name in FINAL_EXTRA]
        if sequence != expected:
            _fail(reasons,
                  f"reference event sequence for {key} differs: {sequence}")
            continue
        derivatives = [e for e in rows if e.get("event") == "PostDerivatives"]
        finals = [e for e in rows if e.get("event") == "PostOutputs"
                  and e.get("time") == 0.001]
        if len(derivatives) != 4:
            _fail(reasons, f"{key}: PostDerivatives count {len(derivatives)} != 4")
            continue
        if not finals:
            _fail(reasons, f"{key}: no PostOutputs at t=0.001")
            continue
        width = hi - lo + 1
        try:
            payloads = ([e["cont_states"] for e in derivatives]
                        + [e["derivatives"] for e in derivatives]
                        + [finals[-1]["cont_states"]])
            for payload in payloads:
                if (payload.get("dtype") != "double"
                        or list(payload.get("shape", [])) != [width, 1]
                        or len(payload.get("hex", [])) != width):
                    raise ValueError(
                        "payload dtype/shape/hex correspondence differs: "
                        f"dtype={payload.get('dtype')!r} shape={payload.get('shape')!r} "
                        f"hex_len={len(payload.get('hex', []))!r}")
            states = [[decode_f64_hex(h) for h in e["cont_states"]["hex"]]
                      for e in derivatives]
            derivs = [[decode_f64_hex(h) for h in e["derivatives"]["hex"]]
                      for e in derivatives]
            final_states = [decode_f64_hex(h)
                            for h in finals[-1]["cont_states"]["hex"]]
        except (KeyError, TypeError, ValueError) as error:
            _fail(reasons, f"{key}: invalid hex payload: {error}")
            continue
        if any(len(row) != width for row in states + derivs) \
                or len(final_states) != width:
            _fail(reasons, f"{key}: payload width differs from the mapped {width}")
            continue
        per_block[key] = dict(
            stage_state_hex=[e["cont_states"]["hex"] for e in derivatives],
            stage_deriv_hex=[e["derivatives"]["hex"] for e in derivatives],
            final_state_hex=finals[-1]["cont_states"]["hex"])
    return per_block, reasons


def parse_solve_reference(data, per_block):
    """Validate the reference pqr_input_probe solve evidence; returns
    (solve, reasons).  'solve' is None when the probe section is absent."""
    probe = data.get("pqr_input_probe")
    reasons = []
    if probe is None:
        return None, []
    if type(probe) is dict and len(probe) == 1 and probe.get("enabled") is False:
        return None, []
    if type(probe) is not dict:
        return None, ["reference pqr_input_probe must be an object"]
    if probe.get("enabled") is not True or probe.get("status") != "traced":
        _fail(reasons, "reference pqr_input_probe must be enabled and traced")
    upstream = probe.get("upstream")
    if (type(upstream) is not dict
            or upstream.get("BlockType") != "Product"
            or upstream.get("is_product_block") is not True
            or upstream.get("Inputs") != "*/"
            or upstream.get("Multiplication") != "Matrix(*)"):
        _fail(reasons, "reference upstream must be Product with Inputs=*/ and Multiplication=Matrix(*)")
    if type(probe.get("dropped_events")) is not int or probe.get("dropped_events") != 0:
        _fail(reasons, "reference solve dropped_events must be 0")
    events = probe.get("events", [])
    if type(events) is not list or len(events) != 5:
        _fail(reasons, f"reference solve must have exactly 5 events, got {len(events)}")
        return None, reasons
    if type(probe.get("event_count")) is not int or probe["event_count"] != len(events):
        _fail(reasons, "reference solve event_count differs from retained events")
    upstream_path = upstream.get("path") if type(upstream) is dict else None
    for index, event in enumerate(events):
        if type(event) is not dict:
            _fail(reasons, f"reference solve event {index} must be an object")
            continue
        if (event.get("event") != "PostOutputs"
                or type(event.get("order")) is not int
                or event.get("order") != index + 1
                or event.get("block") != upstream_path
                or event.get("input_port_count") != 2
                or event.get("output_port_count") != 1):
            _fail(reasons, f"reference solve event {index} identity/order/ports differ")
        if type(event.get("time")) not in (int, float):
            _fail(reasons, f"reference solve event {index} time must be numeric, not bool")
            continue
        try:
            time_value = struct.unpack(">d", struct.pack(">d", event["time"]))[0]
        except (TypeError, struct.error):
            _fail(reasons, f"reference solve event {index} has invalid time")
            continue
        if time_value != SOLVE_TIMES[index]:
            _fail(reasons, f"reference solve event {index} time differs: {time_value}")
        inputs = event.get("inputs", [])
        outputs = event.get("outputs", [])
        if type(inputs) is not list or len(inputs) != 2 or type(outputs) is not list or len(outputs) != 1:
            _fail(reasons, f"reference solve event {index} payload port counts differ")
            continue
        expected_shapes = ([1, 3], [3, 3])
        for port_index, payload in enumerate(inputs):
            if (type(payload) is not dict or payload.get("dtype") != "double"
                    or list(payload.get("shape", [])) != list(expected_shapes[port_index])
                    or len(payload.get("hex", [])) != (3 if port_index == 0 else 9)):
                _fail(reasons,
                      f"reference solve event {index} input {port_index} dtype/shape/hex differ")
                continue
            for h in payload["hex"]:
                decode_f64_hex(h)
        if (len(outputs) != 1 or outputs[0].get("dtype") != "double"
                or list(outputs[0].get("shape", [])) != [1, 3]
                or len(outputs[0].get("hex", [])) != 3):
            _fail(reasons, f"reference solve event {index} output dtype/shape/hex differ")
            continue
        for h in outputs[0]["hex"]:
            decode_f64_hex(h)
    if reasons:
        return None, reasons
    # The first four Product outputs must equal the reference p,q,r
    # PostDerivatives per stage (the operands/results chain, not just states).
    pqr = per_block["p,q,r"]
    for index in range(4):
        if events[index]["outputs"][0]["hex"] != pqr["stage_deriv_hex"][index]:
            _fail(reasons,
                  f"reference solve event {index} output does not equal reference p,q,r derivatives")
    return dict(events=events, upstream=upstream), reasons


def parse_target(lines):
    """Validate and index the target trace rows."""
    reasons = []
    if type(lines) is not list or not all(type(row) is dict for row in lines):
        return None, ["target input must be a list of row dicts"]
    kinds = [row.get("kind") for row in lines]
    core = ["first_step_trace_start",
            "ode4_stage", "ode4_stage", "ode4_stage", "ode4_stage",
            "ode4_update", "first_step_trace_end"]
    core_kinds = [k for k in kinds
                  if k not in ("major_output", "mrdivide_solve")]
    if core_kinds != core:
        _fail(reasons, f"target row sequence differs: {kinds}")
        return None, reasons
    # Major rows are optional; when present they must be exactly k=0 before the
    # first stage and k=1 after the update, in that order, each unique.
    major_positions = [i for i, k in enumerate(kinds) if k == "major_output"]
    if major_positions:
        first_stage = kinds.index("ode4_stage")
        update_index = kinds.index("ode4_update")
        if (len(major_positions) != 2
                or lines[major_positions[0]].get("k") != 0
                or major_positions[0] > first_stage
                or lines[major_positions[1]].get("k") != 1
                or major_positions[1] < update_index):
            _fail(reasons,
                  "target major_output rows must be k=0 before stages and k=1 after update")
    stages = [row for row in lines if row.get("kind") == "ode4_stage"]
    if [row["stage"] for row in stages] != [0, 1, 2, 3]:
        _fail(reasons, "target stages not exactly 0,1,2,3 in order")
    times = [struct.unpack(">d", bytes.fromhex(row["time_s"][2:]))[0]
             for row in stages]
    if tuple(times) != EXPECTED_TIMES:
        _fail(reasons, f"target stage times differ: {times}")
    updates = [row for row in lines if row.get("kind") == "ode4_update"]
    if len(updates) != 1:
        _fail(reasons, f"target must have exactly one ode4_update row, got {len(updates)}")
        return None, reasons
    update = updates[0]
    if struct.unpack(">d", bytes.fromhex(update["time_s"][2:]))[0] != 0.001:
        _fail(reasons, "target update row is not the last t=0.001 record")
    # pre/post are the full 36-wide state vectors, strict finite f64 hex.
    if update.get("nXc") != TOTAL_STATES:
        _fail(reasons, f"target update nXc must be {TOTAL_STATES}, got {update.get('nXc')!r}")
    for field in ("pre_hex", "post_hex"):
        values = update.get(field)
        if not isinstance(values, list) or len(values) != TOTAL_STATES:
            _fail(reasons, f"target update {field} not {TOTAL_STATES} entries")
            continue
        try:
            for h in values:
                decode_f64_hex(h)
        except ValueError as error:
            _fail(reasons, f"target update {field}: {error}")
    for row in stages:
        for field in ("state_hex", "deriv_hex"):
            values = row.get(field)
            if not isinstance(values, list) or len(values) != TOTAL_STATES:
                _fail(reasons, f"stage {row.get('stage')} {field} not 36 entries")
                continue
            try:
                for h in values:
                    decode_f64_hex(h)
            except ValueError as error:
                _fail(reasons, f"stage {row['stage']} {field}: {error}")
    if reasons:
        return None, reasons
    return dict(stages=stages, update=update), reasons


def parse_solve_target(lines, target):
    """Strictly validate the mrdivide solve rows; absent means absent, never
    skipped-to-be-compatible.  Returns (rows, reasons)."""
    reasons = []
    rows = [row for row in lines if row.get("kind") == "mrdivide_solve"]
    if not rows:
        return None, []
    kinds = [row.get("kind") for row in lines]
    pattern = ["first_step_trace_start", "mrdivide_solve", "major_output",
               "ode4_stage", "mrdivide_solve", "ode4_stage",
               "mrdivide_solve", "ode4_stage", "mrdivide_solve", "ode4_stage",
               "ode4_update", "mrdivide_solve", "major_output",
               "first_step_trace_end"]
    if kinds != pattern:
        _fail(reasons, f"solve trace row order differs: {kinds}")
    if [row.get("mrdivide_seq") for row in rows] != [0, 1, 2, 3, 4]:
        _fail(reasons, "solve mrdivide_seq must be 0..4 in order")
    if any(type(row.get("mrdivide_seq")) is not int or type(row.get("is_major")) is not int for row in rows):
        _fail(reasons, "solve sequence and major flag must be integers, not bool")
    times = [struct.unpack(">d", bytes.fromhex(row["time_s"][2:]))[0]
             for row in rows]
    if tuple(times) != SOLVE_TIMES:
        _fail(reasons, f"solve times differ: {times}")
    if [row.get("is_major") for row in rows] != list(SOLVE_MAJOR_FLAGS):
        _fail(reasons, "solve major flags must be 1/0/0/0/1")
    for row in rows:
        for field, width in (("numerator_hex", 3), ("matrix_hex", 9),
                             ("result_hex", 3)):
            values = row.get(field)
            if not isinstance(values, list) or len(values) != width:
                _fail(reasons, f"solve {row.get('mrdivide_seq')} {field} not {width} entries")
                continue
            try:
                for h in values:
                    decode_f64_hex(h)
            except ValueError as error:
                _fail(reasons, f"solve {row.get('mrdivide_seq')} {field}: {error}")
    if reasons:
        return rows, reasons
    # The first four results must bitwise equal the corresponding stage's
    # p,q,r derivative slice; this is the row->stage mapping, never guessed.
    for index in range(4):
        stage_deriv = target["stages"][index]["deriv_hex"][PQR_DERIV_SLICE[0]:PQR_DERIV_SLICE[1]]
        if [norm_hex(h) for h in rows[index]["result_hex"]] !=                 [norm_hex(h) for h in stage_deriv]:
            _fail(reasons,
                  f"solve {index} result does not equal stage {index} p,q,r derivatives")
    return rows, reasons


def _compare_checked(reference_data, target_lines):
    """Run the 13-state first-step comparison; pure."""
    reasons = []
    per_block, ref_reasons = parse_reference(reference_data)
    target, tgt_reasons = parse_target(target_lines)
    reasons.extend(ref_reasons)
    reasons.extend(tgt_reasons)
    if reasons:
        return dict(status="rejected", reasons=reasons)

    blocks = []
    earliest = None
    for key, lo, hi in BLOCK_MAP:
        ref = per_block[key]
        width = hi - lo + 1
        differences = []
        for stage_index, row in enumerate(target["stages"]):
            ref_state = ref["stage_state_hex"][stage_index]
            ref_deriv = ref["stage_deriv_hex"][stage_index]
            for field, ref_hex, tgt_hex in (
                    ("cont_states", ref_state, row["state_hex"]),
                    ("derivatives", ref_deriv, row["deriv_hex"])):
                for index in range(width):
                    if norm_hex(ref_hex[index]) != norm_hex(tgt_hex[lo + index]):
                        ulp = ulp_distance(ref_hex[index], tgt_hex[lo + index])
                        differences.append(dict(
                            stage=stage_index, field=field, index=index,
                            reference_hex=ref_hex[index],
                            target_hex=tgt_hex[lo + index],
                            ulp=ulp,
                            sign_flip=ulp is None))
                        candidate = (stage_index, BLOCK_MAP.index(
                            next(b for b in BLOCK_MAP if b[0] == key)), index)
                        if earliest is None or candidate < earliest[0]:
                            earliest = (candidate, differences[-1])
        final_differences = []
        for index in range(width):
            if norm_hex(ref["final_state_hex"][index]) != norm_hex(
                    target["update"]["post_hex"][lo + index]):
                final_differences.append(dict(
                    index=index,
                    reference_hex=ref["final_state_hex"][index],
                    target_hex=target["update"]["post_hex"][lo + index]))
        blocks.append(dict(block=key, target_indices=[lo, hi],
                           stage_difference_count=len(differences),
                           stage_differences=differences,
                           final_state_differences=final_differences,
                           final_state_selector="last t=0.001 record "
                           "(ode4 update / last PostOutputs), never the "
                           "fourth-stage minor"))
    solve_rows, solve_tgt_reasons = parse_solve_target(target_lines, target)
    solve_ref, solve_ref_reasons = parse_solve_reference(
        reference_data, per_block)
    reasons.extend(solve_tgt_reasons)
    reasons.extend(solve_ref_reasons)
    if solve_rows is None and solve_ref is not None:
        reasons.append("target lacks solve rows while reference solve evidence exists")
    if solve_ref is None and solve_rows is not None:
        reasons.append("reference lacks pqr_input_probe while target solve rows exist")
    if reasons:
        return dict(status="rejected", reasons=reasons)
    solve_section = None
    if solve_rows is not None:
        solve_rows_out = []
        for index, row in enumerate(solve_rows):
            event = solve_ref["events"][index]
            result_differences = []
            for component in range(3):
                if norm_hex(row["result_hex"][component]) != norm_hex(
                        event["outputs"][0]["hex"][component]):
                    result_differences.append(dict(
                        index=component,
                        reference_hex=event["outputs"][0]["hex"][component],
                        target_hex=row["result_hex"][component],
                        ulp=ulp_distance(event["outputs"][0]["hex"][component],
                                         row["result_hex"][component])))
            solve_rows_out.append(dict(
                sequence=index, time=SOLVE_TIMES[index], major=row["is_major"],
                numerator_equal=([norm_hex(h) for h in row["numerator_hex"]]
                                 == [norm_hex(h) for h in event["inputs"][0]["hex"]]),
                matrix_equal=([norm_hex(h) for h in row["matrix_hex"]]
                              == [norm_hex(h) for h in event["inputs"][1]["hex"]]),
                result_differences=result_differences))
        solve_section = dict(
            upstream_path=solve_ref["upstream"]["path"],
            rows=solve_rows_out,
            non_claims=["identical operands do not prove the reference solver internals",
                        "solve-boundary evidence is not whole-model or G6 acceptance"])
    return dict(
        status="aligned",
        scope="13 mapped rigid-body states of 36; not whole-model conformance",
        solve=solve_section,
        mapped_states=MAPPED_STATES,
        total_states=TOTAL_STATES,
        blocks=blocks,
        earliest_difference=(None if earliest is None else dict(
            block=BLOCK_MAP[earliest[0][1]][0], **earliest[1])),
        non_claims=[
            "23 unmapped states are not covered",
            "no G6/R1 passage is claimed",
            "identical stage-0/1 states do not exclude unobserved upstream divergence",
        ])


def compare(reference_data, target_lines):
    """Malformed JSON payloads reject alignment instead of escaping as exceptions."""
    try:
        return _compare_checked(reference_data, target_lines)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, struct.error) as error:
        return {"status": "rejected", "reasons": [f"malformed trace payload: {error}"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    ref_bytes = args.reference.read_bytes()
    tgt_bytes = args.target.read_bytes()
    reference = json.loads(ref_bytes.decode("utf-8"))
    target = [json.loads(line)
              for line in tgt_bytes.decode("utf-8").splitlines() if line.strip()]
    result = compare(reference, target)
    result["reference_sha256"] = hashlib.sha256(ref_bytes).hexdigest()
    result["target_sha256"] = hashlib.sha256(tgt_bytes).hexdigest()
    if args.output.exists():
        print(f"refusing to overwrite existing output: {args.output}",
              file=sys.stderr)
        return 1
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "output": str(args.output)},
                     indent=1))
    return 0 if result["status"] == "aligned" else 1


if __name__ == "__main__":
    sys.exit(main())
