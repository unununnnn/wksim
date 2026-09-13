"""Pure offline C3G stage-2 operand-boundary comparator.

Consumes explicitly supplied retained traces or dedicated operand packets
and derives the C3G k=0→1, ODE4 stage-2 (t=0.0005, mrdivide seq 2)
boundary already documented for p,q,r derivative index 1:

- residual ``rtb_IntegratorSecondOrderLimi_d[0..2]``
- inertia ``Selector2[0..8]``
- result ``Product2[0..2]``
- residual subterms when the packet actually carries them

Bit and ULP differences are computed fail-closed. Missing, malformed,
non-finite, wrong-identity, or incomplete evidence is rejected. An
aligned observation is never treated as causal proof and never claims
G6 or Full acceptance.

CLI:
    python -B tools/compare_g6_c3g_stage2.py \\
        --reference R.json --target T.json[l] --output NEW.json \\
        [--documented-divergence D.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
_REPO = _TOOLS.parent
for _path in (str(_TOOLS), str(_REPO)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from compare_first_step_trace import (
        decode_f64_hex,
        norm_hex,
        parse_reference,
        parse_solve_reference,
        parse_solve_target,
        parse_target,
        ulp_distance,
    )
except ImportError:  # pragma: no cover - package-style import
    from tools.compare_first_step_trace import (
        decode_f64_hex,
        norm_hex,
        parse_reference,
        parse_solve_reference,
        parse_solve_target,
        parse_target,
        ulp_distance,
    )


OPERAND_SCHEMA = "g6-c3g-stage2-operand-boundary/v1"
REQUIRED_CASE = "C3G"
REQUIRED_SOLVER = "ode4"
REQUIRED_BLOCK = "p,q,r"
REQUIRED_FIELD = "derivatives"
REQUIRED_STAGE = 2
REQUIRED_INDEX = 1
REQUIRED_K = (0, 1)
STAGE2_TIME_S = 0.0005
STAGE2_TIME_HEX = "3f40624dd2f1a9fc"
MRDIVIDE_SEQ = 2
DOCUMENTED_REF_Q = "bc56d4db33a987b8"
DOCUMENTED_TGT_Q = "bc56d4db33a987b9"
FROZEN_SELECTOR2 = (
    "3f959b3d07c84b5e",
    "0000000000000000",
    "0000000000000000",
    "0000000000000000",
    "3f966cf41f212d77",
    "0000000000000000",
    "0000000000000000",
    "0000000000000000",
    "3fa2bd3c36113405",
)
VECTOR_FIELDS = {
    "residual": 3,
    "selector2": 9,
    "product2": 3,
    "Sum4_f": 3,
}
SCALAR_FIELDS = ("M1_1", "Fd_0", "Sum1_a_1", "TT0gLR", "aero_damp_q")
SUBTERM_FIELDS = SCALAR_FIELDS + ("Sum4_f",)
REQUIRED_PACKET_FIELDS = ("residual", "selector2", "product2") + SUBTERM_FIELDS
NON_CLAIMS = (
    "aligned means the supplied C3G stage-2 operands could be compared",
    "identical residual and Selector2 do not prove reference solver internals",
    "1 ULP does not exclude libm, unmapped states, or another evaluation order",
    "subterm equality is an observation, not a causal isolation of M1/Fd/gyro/damping",
    "this slice does not approve G6 budgets, close #59, or accept G6 or Full",
)


def _fail(reasons, message):
    reasons.append(message)


def _exact_int(value):
    return value if type(value) is int else None


def _hex_pair(left, right):
    ulp = ulp_distance(left, right)
    return dict(
        reference_hex=left,
        target_hex=right,
        ulp=ulp,
        sign_flip=ulp is None,
    )


def _compare_hex_list(left, right):
    differences = []
    for index, (ref_hex, tgt_hex) in enumerate(zip(left, right)):
        if norm_hex(ref_hex) != norm_hex(tgt_hex):
            differences.append(dict(index=index, **_hex_pair(ref_hex, tgt_hex)))
    return dict(equal=not differences, differences=differences)


def _compare_hex_scalar(left, right):
    if norm_hex(left) == norm_hex(right):
        return dict(equal=True, differences=[])
    return dict(equal=False, differences=[dict(index=0, **_hex_pair(left, right))])


def _require_hex_list(values, width, label, reasons):
    if type(values) is not list or len(values) != width:
        _fail(reasons, f"incomplete {label}: expected {width} hex values")
        return None
    decoded = []
    for index, value in enumerate(values):
        try:
            decode_f64_hex(value)
        except ValueError as error:
            _fail(reasons, f"{label}[{index}]: {error}")
            return None
        decoded.append(value)
    return decoded


def _require_hex_scalar(value, label, reasons):
    if isinstance(value, list):
        if len(value) != 1:
            _fail(reasons, f"incomplete {label}: expected one hex value")
            return None
        value = value[0]
    try:
        decode_f64_hex(value)
    except ValueError as error:
        _fail(reasons, f"{label}: {error}")
        return None
    return value


def detect_kind(payload):
    if type(payload) is dict:
        if payload.get("schema") == OPERAND_SCHEMA:
            return "operand_packet"
        if "events" in payload or "pqr_input_probe" in payload:
            return "reference_first_step"
        return None
    if type(payload) is list:
        return "target_jsonl"
    return None


def _require_identity(payload, reasons, *, source):
    if payload.get("case") != REQUIRED_CASE:
        _fail(reasons, f"{source} case must be {REQUIRED_CASE}")
    if payload.get("solver") != REQUIRED_SOLVER:
        _fail(reasons, f"{source} solver must be {REQUIRED_SOLVER}")
    if payload.get("block") != REQUIRED_BLOCK:
        _fail(reasons, f"{source} block must be {REQUIRED_BLOCK}")
    if payload.get("field") != REQUIRED_FIELD:
        _fail(reasons, f"{source} field must be {REQUIRED_FIELD}")
    if _exact_int(payload.get("stage")) != REQUIRED_STAGE:
        _fail(reasons, f"{source} stage must be the integer {REQUIRED_STAGE}")
    if _exact_int(payload.get("index")) != REQUIRED_INDEX:
        _fail(reasons, f"{source} index must be the integer {REQUIRED_INDEX}")
    k_values = payload.get("k")
    if type(k_values) is not list or [_exact_int(item) for item in k_values] != list(REQUIRED_K):
        _fail(reasons, f"{source} k must be the exact integers {list(REQUIRED_K)}")
    time_s = payload.get("time_s")
    try:
        if not isinstance(time_s, str) or decode_f64_hex(time_s) != STAGE2_TIME_S:
            _fail(reasons, f"{source} time must be stage-2 t=0.0005 hex")
    except ValueError as error:
        _fail(reasons, f"{source} time: {error}")


def parse_operand_packet(payload, *, source):
    reasons = []
    if type(payload) is not dict:
        return None, [f"{source} operand packet must be an object"]
    if payload.get("schema") != OPERAND_SCHEMA:
        _fail(reasons, f"{source} schema must be {OPERAND_SCHEMA}")
    _require_identity(payload, reasons, source=source)
    operands = payload.get("operands")
    if type(operands) is not dict:
        return None, reasons + [f"{source} operands must be an object"]
    missing = [name for name in REQUIRED_PACKET_FIELDS if name not in operands]
    if missing:
        _fail(reasons, f"{source} incomplete operand packet, missing {missing}")
        return None, reasons
    parsed = {}
    for name, width in VECTOR_FIELDS.items():
        parsed[name] = _require_hex_list(operands.get(name), width, f"{source} {name}", reasons)
    for name in SCALAR_FIELDS:
        parsed[name] = _require_hex_scalar(operands.get(name), f"{source} {name}", reasons)
    if reasons or any(value is None for value in parsed.values()):
        return None, reasons
    return parsed, reasons


def _reference_first_step_identity(data, reasons):
    if type(data) is not dict:
        _fail(reasons, "reference first-step trace must be an object")
        return
    if data.get("case") != REQUIRED_CASE:
        _fail(reasons, f"reference case must be {REQUIRED_CASE}")
    if data.get("solver") != REQUIRED_SOLVER:
        _fail(reasons, f"reference solver must be {REQUIRED_SOLVER}")
    if data.get("fixed_step_s") != 0.001 or data.get("stop_time_s") != 0.001:
        _fail(reasons, "reference identity must be ode4 0.001 s first-step k=0→1")


def parse_retained_reference(data):
    reasons = []
    _reference_first_step_identity(data, reasons)
    if reasons:
        return None, reasons
    try:
        per_block, block_reasons = parse_reference(data)
        reasons.extend(block_reasons)
        solve, solve_reasons = parse_solve_reference(data, per_block)
        reasons.extend(solve_reasons)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return None, reasons + [f"malformed retained reference: {error}"]
    if solve is None and not reasons:
        _fail(reasons, "reference incomplete: pqr_input_probe stage-2 solve is absent")
    if reasons or solve is None:
        return None, reasons
    events = solve["events"]
    if len(events) < 3:
        return None, ["reference incomplete: stage-2 solve event missing"]
    event = events[MRDIVIDE_SEQ]
    if event.get("time") != STAGE2_TIME_S or _exact_int(event.get("order")) != 3:
        return None, ["reference stage-2 solve identity differs"]
    residual = _require_hex_list(event["inputs"][0]["hex"], 3, "reference residual", reasons)
    selector2 = _require_hex_list(event["inputs"][1]["hex"], 9, "reference selector2", reasons)
    product2 = _require_hex_list(event["outputs"][0]["hex"], 3, "reference product2", reasons)
    if reasons:
        return None, reasons
    return dict(residual=residual, selector2=selector2, product2=product2,
                subterms=None), reasons


def parse_retained_target(lines):
    reasons = []
    if type(lines) is not list:
        return None, ["target first-step trace must be a jsonl list"]
    start = next((row for row in lines if row.get("kind") == "first_step_trace_start"), None)
    if type(start) is not dict or start.get("case") != REQUIRED_CASE:
        _fail(reasons, f"target case must be {REQUIRED_CASE}")
    if start is not None and start.get("solver") not in (None, REQUIRED_SOLVER):
        _fail(reasons, f"target solver must be {REQUIRED_SOLVER}")
    try:
        target, target_reasons = parse_target(lines)
        reasons.extend(target_reasons)
        rows, solve_reasons = parse_solve_target(lines, target) if target else (None, [])
        reasons.extend(solve_reasons)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return None, reasons + [f"malformed retained target: {error}"]
    if rows is None and not any("incomplete" in item for item in reasons):
        _fail(reasons, "target incomplete: mrdivide stage-2 solve row is absent")
    if reasons or rows is None:
        return None, reasons
    row = next((item for item in rows if _exact_int(item.get("mrdivide_seq")) == MRDIVIDE_SEQ), None)
    if row is None:
        return None, ["target incomplete: stage-2 mrdivide_seq=2 row missing"]
    time_s = row.get("time_s")
    try:
        if not isinstance(time_s, str) or decode_f64_hex(time_s) != STAGE2_TIME_S:
            _fail(reasons, "target stage-2 time must be t=0.0005 hex")
    except ValueError as error:
        _fail(reasons, f"target stage-2 time: {error}")
    if _exact_int(row.get("is_major")) != 0:
        _fail(reasons, "target stage-2 is_major must be the integer 0")
    residual = _require_hex_list(row.get("numerator_hex"), 3, "target residual", reasons)
    selector2 = _require_hex_list(row.get("matrix_hex"), 9, "target selector2", reasons)
    product2 = _require_hex_list(row.get("result_hex"), 3, "target product2", reasons)
    if reasons:
        return None, reasons
    return dict(residual=residual, selector2=selector2, product2=product2,
                subterms=None), reasons


def parse_documented(data):
    reasons = []
    if type(data) is not dict:
        return None, ["documented divergence must be an object"]
    if "blocks" in data:
        chosen = None
        for block in data.get("blocks", []):
            if block.get("block") != REQUIRED_BLOCK:
                continue
            for item in block.get("stage_differences", []):
                if (_exact_int(item.get("stage")) == REQUIRED_STAGE
                        and item.get("field") == REQUIRED_FIELD
                        and _exact_int(item.get("index")) == REQUIRED_INDEX):
                    chosen = item
                    break
        if chosen is None:
            return None, ["documented comparison lacks p,q,r stage-2 derivatives[1]"]
        data = dict(data, **chosen, case=data.get("case", REQUIRED_CASE))
    if data.get("case") not in (None, REQUIRED_CASE):
        _fail(reasons, f"documented case must be {REQUIRED_CASE}")
    if _exact_int(data.get("stage")) != REQUIRED_STAGE:
        _fail(reasons, "documented stage must be the integer 2")
    if data.get("field") != REQUIRED_FIELD:
        _fail(reasons, "documented field must be derivatives")
    if _exact_int(data.get("index")) != REQUIRED_INDEX:
        _fail(reasons, "documented index must be the integer 1")
    try:
        decode_f64_hex(data.get("reference_hex"))
        decode_f64_hex(data.get("target_hex"))
    except (TypeError, ValueError) as error:
        return None, reasons + [f"documented hex: {error}"]
    documented_ulp = ulp_distance(data["reference_hex"], data["target_hex"])
    declared = data.get("ulp")
    if declared is not None and _exact_int(declared) != documented_ulp:
        _fail(reasons, "documented ulp does not match the hex pair")
    if reasons:
        return None, reasons
    return dict(
        reference_hex=data["reference_hex"],
        target_hex=data["target_hex"],
        ulp=documented_ulp,
    ), reasons


def _classify(residual, selector2, product2):
    if not residual["equal"]:
        return "residual_already_differs"
    if not selector2["equal"]:
        return "selector2_already_differs"
    if product2["equal"]:
        return "identical_operands_identical_result"
    return "identical_operands_different_result"


def _subterm_section(reference, target):
    if reference.get("subterms") is None or target.get("subterms") is None:
        return dict(status="unobserved", fields={})
    fields = {}
    for name in SCALAR_FIELDS:
        fields[name] = _compare_hex_scalar(reference[name], target[name])
    fields["Sum4_f"] = _compare_hex_list(reference["Sum4_f"], target["Sum4_f"])
    return dict(status="compared", fields=fields)


def _as_packet_side(parsed):
    if parsed.get("subterms") is None and "M1_1" in parsed:
        return dict(parsed, subterms=True)
    return parsed


def _compare_sides(reference, target, documented):
    residual = _compare_hex_list(reference["residual"], target["residual"])
    selector2 = _compare_hex_list(reference["selector2"], target["selector2"])
    product2 = _compare_hex_list(reference["product2"], target["product2"])
    subterms = _subterm_section(_as_packet_side(reference), _as_packet_side(target))
    observation = dict(
        kind=_classify(residual, selector2, product2),
        matches_documented_divergence=False,
        documented_q_ulp=None,
    )
    reasons = []
    if documented is not None:
        ref_q = reference["product2"][REQUIRED_INDEX]
        tgt_q = target["product2"][REQUIRED_INDEX]
        if (norm_hex(ref_q) != norm_hex(documented["reference_hex"])
                or norm_hex(tgt_q) != norm_hex(documented["target_hex"])):
            _fail(reasons,
                  "documented divergence does not match extracted Product2[1]")
        else:
            observation["matches_documented_divergence"] = True
            observation["documented_q_ulp"] = documented["ulp"]
    if reasons:
        return dict(status="rejected", reasons=reasons)
    return dict(
        status="aligned",
        scope=("C3G k=0→1 stage-2 p,q,r derivative index 1 operand boundary; "
               "not whole-model, G6, or Full acceptance"),
        identity=dict(
            case=REQUIRED_CASE,
            k=list(REQUIRED_K),
            stage=REQUIRED_STAGE,
            time_s=STAGE2_TIME_S,
            mrdivide_seq=MRDIVIDE_SEQ,
            block=REQUIRED_BLOCK,
            field=REQUIRED_FIELD,
            index=REQUIRED_INDEX,
        ),
        operands=dict(
            residual=residual,
            selector2=selector2,
            product2=product2,
            subterms=subterms,
        ),
        observation=observation,
        causal=dict(
            status="unproven",
            reasons=[
                "the decision tree labels an observation branch only",
                "identical operands do not prove LAPACK versus handwritten mrdivide",
                "a residual difference does not isolate a single upstream term as cause",
                "unobserved motor/aero states and libm calls remain open",
            ],
        ),
        non_claims=list(NON_CLAIMS),
    )


def _compare_checked(reference, target, documented=None):
    reasons = []
    documented_parsed = None
    if documented is not None:
        documented_parsed, documented_reasons = parse_documented(documented)
        reasons.extend(documented_reasons)
    ref_kind = detect_kind(reference)
    tgt_kind = detect_kind(target)
    if ref_kind == "operand_packet" and tgt_kind == "operand_packet":
        ref_side, ref_reasons = parse_operand_packet(reference, source="reference")
        tgt_side, tgt_reasons = parse_operand_packet(target, source="target")
        reasons.extend(ref_reasons)
        reasons.extend(tgt_reasons)
        if reasons or ref_side is None or tgt_side is None:
            return dict(status="rejected", reasons=reasons)
        return _compare_sides(ref_side, tgt_side, documented_parsed)
    if ref_kind == "reference_first_step" and tgt_kind == "target_jsonl":
        ref_side, ref_reasons = parse_retained_reference(reference)
        tgt_side, tgt_reasons = parse_retained_target(target)
        reasons.extend(ref_reasons)
        reasons.extend(tgt_reasons)
        if reasons or ref_side is None or tgt_side is None:
            return dict(status="rejected", reasons=reasons)
        return _compare_sides(ref_side, tgt_side, documented_parsed)
    if ref_kind is None or tgt_kind is None:
        _fail(reasons, "malformed trace identity or unsupported payload")
    else:
        _fail(reasons, f"format/identity mismatch: {ref_kind} vs {tgt_kind}")
    return dict(status="rejected", reasons=reasons)


def compare(reference, target, documented=None):
    """Malformed payloads reject alignment instead of escaping as exceptions."""
    try:
        return _compare_checked(reference, target, documented)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as error:
        return {"status": "rejected", "reasons": [f"malformed trace payload: {error}"]}


def load_payload(path):
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8")
    if Path(path).suffix.lower() == ".jsonl":
        payload = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        payload = json.loads(text)
    return payload, hashlib.sha256(raw).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--documented-divergence", type=Path)
    args = parser.parse_args(argv)
    reference, reference_sha = load_payload(args.reference)
    target, target_sha = load_payload(args.target)
    documented = None
    documented_sha = None
    if args.documented_divergence is not None:
        documented, documented_sha = load_payload(args.documented_divergence)
    result = compare(reference, target, documented=documented)
    result["reference_sha256"] = reference_sha
    result["target_sha256"] = target_sha
    if documented_sha is not None:
        result["documented_sha256"] = documented_sha
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
