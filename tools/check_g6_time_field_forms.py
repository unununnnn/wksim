"""Independent offline structural checker for the 11.8 major time-field forms.

Scope: the three ``schedule_metadata`` slots of the sealed 501-row major
recorder evidence (``Vehicle60[2]`` in seconds, ``Sensor30[0]`` and
``GPS30[0]`` in microseconds).  For each slot this tool recomputes, from raw
bytes and without executing any model:

* the **product form** ``(k * 0.001) * gain`` -- the compiled form the frozen
  contract attributes to the native major outputs;
* the **division form** ``(k / 1000) * gain`` -- the form the native drivers
  use for ``input_time_s``;
* the per-stream row counts and the exact row indices on which the recorded
  column differs from the division form (binary64 operation-order difference).

The recomputation is deliberately independent of
``validation/coordination/major-time-acceptance-20260913-01/verify_times.py``:
it re-derives the row width from the recorded sample lengths, re-derives the
time slot and unit from the tracked ``numerical-conformance-v1.json``
observables whose ``semantic_status`` is ``schedule_metadata``, and re-derives
the per-row time from the reference file bytes with its own little-endian
binary64 row decoder.

Evidence policy (fail closed):

* provenance is bound to the stable evidence anchor
  ``f333316e6efa6b299b4288a9d91fb2bccedfb9d6``, never to an exact HEAD.  The
  observed HEAD is read at runtime only to prove that it descends from the
  anchor (``merge-base --is-ancestor``) and that ``diff anchor..HEAD`` is empty
  for every pinned evidence path; the observed HEAD value itself is never
  recorded.  A non-ancestor checkout, a changed pinned path, or an unavailable
  probe fails closed;
* every **tracked** dependency must be present in the ``HEAD`` tree with the
  exact pinned SHA256/size, otherwise the tool refuses to emit a document and
  reports the exact missing input;
* the split reference arrays are **not** repository-tracked (the ``.gitignore``
  rule ``/validation/*/`` covers the whole directory).  They are declared
  untracked inputs bound by SHA256/size; when any is absent or mismatched the
  tool fails closed with ``status="blocked"`` and reports the exact path,
  expected SHA256 and expected size.  Nothing is guessed and no value is
  invented;
* this checker distinguishes **scheduling evidence** (the time-field forms and
  their row counts, which is all it recomputes here) from
  **dynamics/physical budget** (which it never evaluates, approximates, or
  approves).

Nothing here compiles, simulates, or runs MATLAB, Simulink, native code, ROS,
DDS, SITL, flight, Unreal, or #83.  No existing evidence, contract, or trace
byte is written.  No staging, committing, or pushing is performed.

Determinism: :func:`build_document` is a pure function of the declared pin
bytes and of the anchor-relative provenance verdict (anchor ancestry plus the
per-path ``diff anchor..HEAD`` result), which is itself invariant across any
clean descendant of the anchor.  :func:`dumps` fixes key order, indentation,
ASCII escaping and the trailing newline, so regeneration from the same bytes is
byte-identical and is robust to HEAD drift.

This is a structural cross-check of scheduling metadata.  It is not a numerical
acceptance, not a physical-accuracy claim, not a budget or approval, and not
R1/G6/Full passage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Frozen identity
# --------------------------------------------------------------------------

SCHEMA = "wksim.59-g6-time-field-forms.v1"
KIND = "g6_time_field_forms"
VERSION = 1
GENERATOR = "tools/check_g6_time_field_forms.py"
DEFAULT_OUT = "validation/g6-time-field-forms-20260914.json"
DATE = "2026-09-14"
ISSUE = "#59"
TITLE = ("G6 independent offline T2 time-field structural check "
         "(product form vs division form)")

# Stable evidence anchor (see AGENTS.md): every new-development checkout must
# contain this commit.  Provenance is bound to the anchor, never to an exact
# HEAD.  The observed HEAD is read at runtime only to prove that (a) it descends
# from the anchor (``merge-base --is-ancestor``) and (b) it leaves every pinned
# evidence path byte-identical to the anchor (``diff anchor..HEAD`` empty per
# path).  No exact HEAD is embedded or required anywhere, so the checker stays
# correct across HEAD drift to any clean descendant of the anchor.
ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"

# The current frontier.  This slice advances or closes none of them.
R1_STATUS = "numerical_failed"
OPEN_ITEMS = (
    ("issue_84", "open"),
    ("g6", "open"),
    ("full", "open"),
)
WORK_CLASS = "new-development"
LAYER = "structural_conformance_check"
AUTHORITY = "none"

STOP_TIME_S = 0.5
FIXED_STEP_S = 0.001
ROW_COUNT = 501            # 0..500 inclusive, initial + terminal event
SHIFT_INDEX = 17           # the documented negative-control row
SHIFTED_K = 18

# The reported counts this checker reconstructs rather than trusts.  They are
# constants *of the claim under test*: the checker recomputes every one of them
# from raw bytes and records whether the recomputation still supports them.
CLAIMED_ROWS = 501
CLAIMED_REFERENCE_PRODUCT_ROWS = 501
CLAIMED_REFERENCE_DIVISION_ROWS = 429
CLAIMED_MEASURED_DIVISION_DIFFS = {
    "Vehicle60_2": 72,
    "Sensor30_0": 61,
    "GPS30_0": 61,
}

# --------------------------------------------------------------------------
# Declared pins: repository-tracked evidence (must be in the HEAD tree)
# --------------------------------------------------------------------------

RECORD_PIN = {
    "path": "validation/e0-major-recorder-parent-final-01/record.jsonl",
    "sha256": "8ce61b3338d42f964dbb704bcebe25a7c0b728926eae974970fe3cb6a58ff354",
    "size": 936395,
}

CONTRACT_PIN = {
    "path": "Simulator/wksim_core/numerical-conformance-v1.json",
    "sha256": "23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0",
    "size": 29846,
}

COMPANION_VERIFICATION_PIN = {
    "path": ("validation/coordination/major-time-acceptance-20260913-01/"
             "verification.json"),
    "sha256": "edf6a755f7e3b5b2b71e7c9064311653b689210b43884ed93e9c6d5659cd6f70",
    "size": 2417,
}

COMPANION_REJECTION_PIN = {
    "path": ("validation/coordination/major-time-acceptance-20260913-01/"
             "initial-assumption-rejected.json"),
    "sha256": "d89654102bc29455ff2d94dea687ac75b7fff82761c162748d126c347d53a9a6",
    "size": 300,
}

READER_PIN = {
    "path": ("validation/coordination/major-time-acceptance-20260913-01/"
             "verify_times.py"),
    "sha256": "01c1468255017c21bccd06d9024cd8bcfd122e41715d55aef0e918acaefdc030",
    "size": 3261,
}

CONVENTIONS_PIN = {
    "path": "docs/2026-09-13-major-time-conventions.md",
    "sha256": None,   # recorded at build time; the document is tracked
    "size": None,
}

# Every repository-tracked evidence path whose bytes must be identical between
# the anchor and the observed HEAD.  ``diff anchor..HEAD`` must be empty for
# each of them; any change is a pinned-path overlap and fails closed.
PINNED_EVIDENCE_PATHS = (
    RECORD_PIN["path"],
    CONTRACT_PIN["path"],
    COMPANION_VERIFICATION_PIN["path"],
    COMPANION_REJECTION_PIN["path"],
    READER_PIN["path"],
    CONVENTIONS_PIN["path"],
)

# Identity constants the reader ``verify_times.py`` pins inside its own bytes.
# They are re-read from that tracked file rather than trusted from prose.
READER_PINNED = {
    "record_sha256": RECORD_PIN["sha256"],
    "original_cpp_sha256": (
        "2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274"),
    "insertion_line": 7919,
    "reference_revision": "SLX model 11.8",
    "reference_root": "validation/numerical-conformance-u56ce17a/C0",
}

# --------------------------------------------------------------------------
# Declared inputs that are NOT repository-tracked
# --------------------------------------------------------------------------
# key -> (path, sha256, size, reference_row_width, role)
# ``reference_row_width`` is the number of binary64 values per row including
# the retained leading time column and is cross-checked against the file size
# (size == 501 * width * 8), so no size is invented.

UNTRACKED_REFERENCE_ROOT = "validation/numerical-conformance-u56ce17a/C0"

UNTRACKED_INPUTS = {
    "vehicle60_reference": (
        UNTRACKED_REFERENCE_ROOT + "/Vehicle60.f64",
        "fcbfb3439f2595d459463d61b1b9b5830290e4993b46ef8614e788880ebc8ceb",
        244488,
        61,
        "split reference array for Vehicle60 (60 slots plus leading time)",
    ),
    "sensor30_reference": (
        UNTRACKED_REFERENCE_ROOT + "/Sensor30.f64",
        "066a5561a82737d8ea0fccfd81c60efe82f1eb06156a460e67ba73fe545e8b90",
        124248,
        31,
        "split reference array for Sensor30 (30 slots plus leading time)",
    ),
    "gps30_reference": (
        UNTRACKED_REFERENCE_ROOT + "/GPS30.f64",
        "459dd65a702e64b28f701f79318250be56127470df2579fecbaa607845cc4074",
        124248,
        31,
        "split reference array for GPS30 (30 slots plus leading time)",
    ),
}

# The two recorded form hypotheses under test.  ``gain`` is applied after the
# clock operation, exactly as the compiled expressions are written.
PRODUCT_FORM = "(k * 0.001) * gain"
DIVISION_FORM = "(k / 1000) * gain"
PRODUCT_FORM_ID = "product_then_gain"
DIVISION_FORM_ID = "division_then_gain"
FORM_IDS = (PRODUCT_FORM_ID, DIVISION_FORM_ID)

SLOT_STATUS = "schedule_metadata"

NONCLAIMS = [
    "no numerical acceptance: no model, executable, or solver was run; only "
    "already-sealed binary64 bytes were re-decoded",
    "no physical-accuracy claim: the recomputed quantity is a scheduling time "
    "field, and dynamics/physical budget is neither evaluated nor bounded here",
    "no budget approval, no pending approval, and no contract freeze is "
    "proposed, requested, or recorded",
    "no closure: #84, G6 and Full remain open, and r1_status remains "
    "numerical_failed",
    "no claim that the division-form rows are erroneous: the difference is "
    "binary64 operation order, not a physical error",
    "no claim about the native driver input_time_s beyond the form it uses",
    "no reuse of verify_times.py output: the accompanying recorded counts are "
    "recomputed from raw bytes and only then compared",
    "no MATLAB, Simulink, native, ROS, DDS, SITL, flight, Unreal, or #83 "
    "execution",
    "no staging, commit, or push: the candidate files are written to the "
    "working tree only",
    "no edit to any existing evidence, contract, trace, or coordination byte",
]

SCOPE_LIMITS = [
    "one case (C0, SLX 11.8 normal reference), one sealed 501-row run",
    "three schedule_metadata slots only; the other 118 slots of the three "
    "arrays are outside this check",
    "scheduling evidence only: no dynamics and no physical budget",
    "reference row counts are decomposition of already-recorded bytes, not a "
    "new model execution",
]


# --------------------------------------------------------------------------
# Repository access (index-independent: ls-tree / rev-parse / merge-base only)
# --------------------------------------------------------------------------


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _git(repo_root, *args):
    """Run an index-independent git command; returns (returncode, stdout)."""
    try:
        result = subprocess.run(["git"] + list(args), cwd=str(repo_root),
                                capture_output=True, check=False)
    except OSError:
        return 1, b""
    return result.returncode, result.stdout


def head_tree_paths(repo_root):
    """Repository paths present in the HEAD tree.  Empty set when unavailable."""
    code, out = _git(repo_root, "ls-tree", "-r", "--name-only", "-z", "HEAD")
    if code != 0:
        return set()
    return set(out.decode("utf-8", "replace").split("\0")) - {""}


def head_commit(repo_root):
    code, out = _git(repo_root, "rev-parse", "HEAD")
    return out.decode("utf-8", "replace").strip() if code == 0 else None


def _classify_ancestor(repo_root, ancestor, head):
    """``merge-base --is-ancestor``: 'ancestor' | 'not_ancestor' | 'unavailable'.

    Exit 0 means ``ancestor`` is an ancestor of ``head``; exit 1 means it is
    not; any other exit (for example an unknown object) is reported as
    unavailable so the caller fails closed rather than guessing.
    """
    code, _ = _git(repo_root, "merge-base", "--is-ancestor", ancestor, head)
    if code == 0:
        return "ancestor"
    if code == 1:
        return "not_ancestor"
    return "unavailable"


def _changed_paths_since(repo_root, ancestor, head, paths):
    """Sorted pinned paths whose bytes differ between ``ancestor`` and ``head``.

    An empty list means ``git diff anchor..head`` is empty for every pinned
    path.  ``None`` means the diff could not be completed (fail closed).
    """
    changed = []
    for path in paths:
        code, out = _git(repo_root, "diff", "--name-only", ancestor, head,
                         "--", path)
        if code != 0:
            return None
        if out.decode("utf-8", "replace").strip():
            changed.append(path)
    return sorted(changed)


def _anchor_provenance(repo_root, anchor, observed_head, pinned_paths):
    """Bind provenance to the stable anchor, never to an exact HEAD.

    Returns ``(info, blocks)``.  ``observed_head`` is a purely observational
    runtime value: it is read to prove that the anchor is an ancestor of it and
    that every pinned evidence path is byte-identical between the anchor and
    it, and it is deliberately never recorded in the emitted document.  Any
    failure (non-ancestor, changed pinned path, or an unavailable probe) fails
    closed and invents nothing.
    """
    info = {
        "base_ancestor": anchor,
        "anchor_requirement": (
            "git merge-base --is-ancestor <anchor> <observed HEAD>"),
        "diff_requirement": (
            "git diff <anchor>..<observed HEAD> is empty for every pinned "
            "evidence path"),
        "observed_head_recording": "deliberately_not_recorded",
        "ancestor_check": "unavailable",
        "anchor_is_ancestor_of_observed_head": False,
        "evidence_paths_unchanged_since_anchor": False,
        "pinned_evidence_paths": list(pinned_paths),
        "changed_pinned_paths": None,
    }
    blocks = []
    if observed_head is None:
        blocks.append({
            "id": "observed_head_unavailable",
            "kind": "provenance_unavailable",
            "reason": ("cannot resolve the observed HEAD; provenance cannot be "
                       "bound to the anchor and no value is invented"),
        })
        return info, blocks
    ancestor_state = _classify_ancestor(repo_root, anchor, observed_head)
    info["ancestor_check"] = ancestor_state
    info["anchor_is_ancestor_of_observed_head"] = (ancestor_state == "ancestor")
    if ancestor_state == "not_ancestor":
        blocks.append({
            "id": "base_ancestor_not_ancestor",
            "kind": "anchor_not_ancestor",
            "base_ancestor": anchor,
            "reason": ("the observed HEAD does not descend from the stable "
                       "evidence anchor; this checkout cannot validate the new "
                       "architecture and the checker fails closed"),
        })
    elif ancestor_state == "unavailable":
        blocks.append({
            "id": "base_ancestor_check_unavailable",
            "kind": "provenance_unavailable",
            "base_ancestor": anchor,
            "reason": ("the anchor ancestry check could not be completed (the "
                       "anchor object may be absent); the checker fails closed"),
        })
    changed = _changed_paths_since(repo_root, anchor, observed_head, pinned_paths)
    info["changed_pinned_paths"] = changed
    if changed is None:
        blocks.append({
            "id": "evidence_diff_unavailable",
            "kind": "provenance_unavailable",
            "base_ancestor": anchor,
            "reason": ("the anchor..HEAD diff for the pinned evidence paths "
                       "could not be completed; the checker fails closed"),
        })
    else:
        info["evidence_paths_unchanged_since_anchor"] = (changed == [])
        if changed:
            blocks.append({
                "id": "pinned_path_overlap",
                "kind": "pinned_path_overlap",
                "base_ancestor": anchor,
                "changed_pinned_paths": changed,
                "reason": ("one or more pinned evidence paths changed between "
                           "the anchor and the observed HEAD; the recorded pins "
                           "no longer bind that path and the checker fails "
                           "closed"),
            })
    return info, blocks


def _bits(value):
    return struct.pack("<d", value)


def _read_bytes(repo_root, rel_path):
    return (Path(repo_root) / rel_path).read_bytes()


def _decode_rows(raw, width, expected_rows):
    """Little-endian binary64 row decoder: (rows, notes).

    Each row is ``width`` consecutive little-endian binary64 values.  A file
    whose length is not an exact multiple of the row size, or whose row count
    disagrees with the expected count, is refused rather than padded.
    """
    row_bytes = width * 8
    notes = []
    if row_bytes <= 0:
        return [], ["row width must be positive"]
    if len(raw) % row_bytes:
        return [], [f"file length {len(raw)} is not a multiple of {row_bytes}"]
    rows = len(raw) // row_bytes
    if expected_rows is not None and rows != expected_rows:
        return [], [f"row count {rows} != expected {expected_rows}"]
    fmt = "<" + "d" * width
    return [struct.unpack_from(fmt, raw, offset * row_bytes)
            for offset in range(rows)], notes


# --------------------------------------------------------------------------
# Evidence dependency resolution
# --------------------------------------------------------------------------


def _dependency_entry(repo_root, role, pin, tracked_paths, required=True):
    rel_path = pin["path"]
    tracked = rel_path in tracked_paths
    entry = {
        "role": role,
        "path": rel_path,
        "tracked_at_head": tracked,
        "required_tracked": bool(required),
        "expected_sha256": pin["sha256"],
        "expected_size": pin["size"],
        "sha256": None,
        "size": None,
        "hash_matches": None,
        "size_matches": None,
        "available_on_disk": False,
        "tracked_status": "tracked_at_head" if tracked else "not_tracked_at_head",
    }
    try:
        raw = _read_bytes(repo_root, rel_path)
    except OSError:
        return entry, None
    digest = _sha256(raw)
    entry["available_on_disk"] = True
    entry["sha256"] = digest
    entry["size"] = len(raw)
    entry["hash_matches"] = (pin["sha256"] is None or digest == pin["sha256"])
    entry["size_matches"] = (pin["size"] is None or len(raw) == pin["size"])
    return entry, raw


def _unit_gain(unit):
    if unit == "s":
        return 1.0
    if unit == "us":
        return 1000000.0
    raise ValueError(f"unsupported schedule_metadata unit {unit!r}")


def _contract_schedule_slots(contract):
    """Re-derive the three schedule_metadata slots from the tracked contract.

    The expected measured row width of each array is recomputed as one more
    than the highest index any tracked observable claims for that array, so the
    width check never depends on a hand-written constant.
    """
    observables = contract.get("observables", [])
    widths = {}
    for observable in observables:
        indices = observable.get("indices")
        if not isinstance(indices, list) or not indices:
            continue
        widths[observable.get("array")] = max(
            [widths.get(observable.get("array"), 0)] + list(indices)) + 1
    slots = []
    for index, observable in enumerate(observables):
        if observable.get("semantic_status") != SLOT_STATUS:
            continue
        indices = observable.get("indices")
        if not isinstance(indices, list) or len(indices) != 1:
            raise ValueError(
                f"observable {observable.get('id')!r} is not a single-slot "
                f"schedule_metadata entry: {indices!r}")
        gain = _unit_gain(observable.get("native_unit"))
        array = observable["array"]
        slots.append({
            "observable_id": observable["id"],
            "observable_index": index,
            "array": array,
            "slot": indices[0],
            "unit": observable["native_unit"],
            "gain": gain,
            "array_element_count": widths.get(array),
            "semantic_status": observable["semantic_status"],
            "internal_rule": observable.get("rule"),
            "contract_source": observable.get("source"),
        })
    if len(slots) != 3:
        raise ValueError(
            f"expected exactly 3 schedule_metadata slots, found {len(slots)}")
    return slots


def _reader_constants(reader_text):
    """Which of the identity constants the tracked reader actually pins."""
    found = {}
    for key, literal in (
        ("record_sha256", READER_PINNED["record_sha256"]),
        ("original_cpp_sha256", READER_PINNED["original_cpp_sha256"]),
        ("reference_revision", READER_PINNED["reference_revision"]),
        ("reference_root", READER_PINNED["reference_root"]),
    ):
        found[key] = literal in reader_text
    found["insertion_line"] = (
        f"insertion_line'] == {READER_PINNED['insertion_line']}" in reader_text)
    return found


# --------------------------------------------------------------------------
# Recomputation
# --------------------------------------------------------------------------


def _form_value(k, gain, form_id):
    if form_id == PRODUCT_FORM_ID:
        return (k * 0.001) * gain
    return (k / 1000) * gain


def _stream_recomputation(samples, slot, gain):
    """Product/division-form structure of one recorded column."""
    column = [row[slot] for row in samples]
    product_bits = [_bits(_form_value(k, gain, PRODUCT_FORM_ID))
                    for k in range(ROW_COUNT)]
    division_bits = [_bits(_form_value(k, gain, DIVISION_FORM_ID))
                     for k in range(ROW_COUNT)]
    # The clock operand is computed once per row and reused for every stream, so
    # the two hypotheses are comparable across streams.
    product_match = [k for k in range(ROW_COUNT)
                     if _bits(column[k]) == product_bits[k]]
    product_mismatch = [k for k in range(ROW_COUNT)
                        if _bits(column[k]) != product_bits[k]]
    division_mismatch = [k for k in range(ROW_COUNT)
                         if _bits(column[k]) != division_bits[k]]
    # The two form hypotheses disagree on these rows, gain notwithstanding.
    disagreement = [k for k in range(ROW_COUNT)
                    if product_bits[k] != division_bits[k]]
    return {
        "row_count": len(column),
        "gain": gain,
        "form_clock": {
            PRODUCT_FORM_ID: "k * 0.001",
            DIVISION_FORM_ID: "k / 1000",
        },
        "measured_product_rows_matched": len(product_match),
        "measured_product_rows_mismatch": len(product_mismatch),
        "measured_product_mismatch_indices": product_mismatch,
        "measured_division_rows_matched": ROW_COUNT - len(division_mismatch),
        "measured_division_differs_from_product": len(division_mismatch),
        "measured_division_mismatch_indices": division_mismatch,
        "form_disagreement_rows": len(disagreement),
        "form_disagreement_indices_first": disagreement[:16],
        "form_disagreement_indices_count": len(disagreement),
    }


def _shifted_row_check(samples, slot, gain):
    """Negative control: adding one step to row 17 must reject on that row."""
    column = [row[slot] for row in samples]
    expected = [_bits(_form_value(k, gain, PRODUCT_FORM_ID))
                for k in range(ROW_COUNT)]
    shifted = list(column)
    shifted[SHIFT_INDEX] = _form_value(SHIFTED_K, gain, PRODUCT_FORM_ID)
    mismatches = [k for k in range(ROW_COUNT)
                  if _bits(shifted[k]) != expected[k]]
    return {
        "index": SHIFT_INDEX,
        "shifted_k": SHIFTED_K,
        "unshifted_mismatches": [
            k for k in range(ROW_COUNT) if _bits(column[k]) != expected[k]],
        "shifted_mismatches": mismatches,
        "only_shifted_row_rejected": mismatches == [SHIFT_INDEX],
    }


def _clock_structure(rows, gain, unit):
    """Product/division-form structure of a decoded leading time column."""
    product_match = sum(1 for k, row in enumerate(rows)
                        if _bits(row[0]) == _bits(_form_value(k, gain, PRODUCT_FORM_ID)))
    division_match = sum(1 for k, row in enumerate(rows)
                         if _bits(row[0]) == _bits(_form_value(k, gain, DIVISION_FORM_ID)))
    disagreement = [k for k in range(ROW_COUNT)
                    if _bits(_form_value(k, gain, PRODUCT_FORM_ID))
                    != _bits(_form_value(k, gain, DIVISION_FORM_ID))]
    return {
        "row_count": len(rows),
        "unit": unit,
        "gain_applied_to_clock": gain,
        "product_rows_matched": product_match,
        "division_rows_matched": division_match,
        "product_rows_mismatch": ROW_COUNT - product_match,
        "division_rows_mismatch": ROW_COUNT - division_match,
        "form_disagreement_rows": len(disagreement),
        "form_disagreement_indices_first": disagreement[:16],
        "form_disagreement_indices_count": len(disagreement),
    }


def _reference_recomputation(raw, width, unit):
    """Time-column structure of a split reference file, plus array cross-check.

    The retained leading column of every split reference array is an unscaled
    seconds clock (``gain = 1``), while the remaining columns keep the array's
    native contract unit.  Both facts are recomputed here rather than assumed:
    the clock is compared against both forms with gain 1, and the remaining
    columns are compared against the sealed native major outputs after the
    contract gain, so the "time column" identification is evidence-backed.
    """
    rows, notes = _decode_rows(raw, width, ROW_COUNT)
    if notes:
        return None, notes
    entry = _clock_structure(rows, 1.0, "s")
    entry["row_width"] = width
    entry["leading_time_column_index"] = 0
    entry["array_columns"] = width - 1
    entry["array_columns_native_unit"] = unit
    return entry, []


def _reference_array_crosscheck(reference_rows, measured_rows, slot, gain):
    """Structural inventory of one split reference array over all 501 rows.

    The checker recomputes, for every non-clock reference column, how many rows
    it agrees with each measured native slot (both raw and divided by the
    contract gain) and records the unique full matches.  It deliberately does
    **not** claim a complete per-slot layout identity: the reference decoder's
    slot order is not bound by the tracked evidence, and two Vehicle60 columns
    (one constant column and one reserved column) do not reach 501 rows.  Only
    the three schedule_metadata time columns are asserted here.
    """
    array = slot["array"]
    slot_index = slot["slot"]
    measured_column = [row["major_root_outputs"][array] for row in measured_rows]
    native_slots = len(measured_column[0])
    matches = {}
    unmatched = []
    for column in range(1, len(reference_rows[0])):
        targets = []
        form = None
        for target in range(native_slots):
            if all(_bits(reference_rows[k][column])
                   == _bits(measured_column[k][target])
                   for k in range(ROW_COUNT)):
                targets.append(target)
                form = form or "native_raw"
            elif all(_bits(reference_rows[k][column])
                     == _bits(measured_column[k][target] / gain)
                     for k in range(ROW_COUNT)):
                targets.append(target)
                form = form or "native_gained"
        if targets:
            matches[column] = {"measured_slots": targets, "form": form}
        else:
            unmatched.append(column)
    time_match = matches.get(slot_index + 1)
    time_column = (time_match is not None
                   and slot_index in time_match["measured_slots"])
    return {
        "array": array,
        "contract_gain": gain,
        "non_clock_columns": native_slots,
        "measured_native_slots": native_slots,
        "clock_column": {
            "index": 0,
            "unit": "s",
            "gain_applied": 1.0,
            "role": "retained leading time column (unscaled seconds)",
        },
        "slot_index_in_array": slot_index,
        "reference_column_for_slot": slot_index + 1,
        "slot_reference_column_equals_clock_times_gain": all(
            _bits(reference_rows[k][slot_index + 1])
            == _bits(_form_value(k, gain, PRODUCT_FORM_ID))
            for k in range(ROW_COUNT)),
        "slot_time_column_matches_measured_slot": time_column,
        "slot_time_column_match_form": (
            time_match["form"] if time_column else None),
        "columns_with_a_full_match": len(matches),
        "columns_without_a_full_match": unmatched,
        "column_full_matches": [
            {"column": column,
             "measured_slots": matches[column]["measured_slots"],
             "form": matches[column]["form"]}
            for column in sorted(matches)],
        "evidence_class": "scheduling_evidence",
        "note": ("this inventory binds the retained leading time column to the "
                 "split reference arrays and is a scheduling-metadata check; "
                 "the per-slot identity of the non-time columns is not claimed "
                 "because it is not bound by tracked evidence, and no dynamics "
                 "or physical-budget claim is made"),
    }


def _stream_measurements(samples, gains):
    """Cross-form and cross-stream agreement over the sealed 501 rows."""
    return {
        "vehicle60_slot_2_equals_k_times_0p001": all(
            _bits(samples[k]["major_root_outputs"]["Vehicle60"][2])
            == _bits(_form_value(k, 1.0, PRODUCT_FORM_ID))
            for k in range(ROW_COUNT)),
        "sensor30_slot_equals_k_times_0p001_scaled": all(
            _bits(samples[k]["major_root_outputs"]["Sensor30"][0])
            == _bits(_form_value(k, gains["Sensor30"], PRODUCT_FORM_ID))
            for k in range(ROW_COUNT)),
        "gps30_slot_equals_k_times_0p001_scaled": all(
            _bits(samples[k]["major_root_outputs"]["GPS30"][0])
            == _bits(_form_value(k, gains["GPS30"], PRODUCT_FORM_ID))
            for k in range(ROW_COUNT)),
        "input_time_s_matches_division_form": all(
            _bits(samples[k]["input_time_s"]) == _bits(k / 1000)
            for k in range(ROW_COUNT)),
        "input_time_s_matches_product_form": all(
            _bits(samples[k]["input_time_s"]) == _bits(k * 0.001)
            for k in range(ROW_COUNT)),
        "input_time_s_division_indices": [
            k for k in range(ROW_COUNT)
            if _bits(samples[k]["input_time_s"]) != _bits(k * 0.001)],
        "engine_before_s_matches_product_form": all(
            _bits(samples[k]["engine_before_s"]) == _bits(k * 0.001)
            for k in range(ROW_COUNT)),
        "call_number_equals_k_plus_one": all(
            samples[k]["call_number"] == k + 1 for k in range(ROW_COUNT)),
    }


# --------------------------------------------------------------------------
# Document construction
# --------------------------------------------------------------------------


def build_document(repo_root):
    """Pure function of the declared pin bytes; returns (document, blocks)."""
    repo_root = Path(repo_root)
    blocks = []
    tracked_paths = head_tree_paths(repo_root)
    observed_head = head_commit(repo_root)
    provenance, provenance_blocks = _anchor_provenance(
        repo_root, ANCESTOR, observed_head, PINNED_EVIDENCE_PATHS)
    blocks.extend(provenance_blocks)

    dependencies = []
    raw = {}
    for role, pin in (
        ("sealed_major_recorder_run", RECORD_PIN),
        ("compiled_contract", CONTRACT_PIN),
        ("companion_verification_record", COMPANION_VERIFICATION_PIN),
        ("companion_rejected_assumption", COMPANION_REJECTION_PIN),
        ("companion_reader", READER_PIN),
    ):
        entry, payload = _dependency_entry(repo_root, role, pin, tracked_paths)
        dependencies.append(entry)
        if payload is not None:
            raw[role] = payload

    conventions_entry, conventions_raw = _dependency_entry(
        repo_root, "time_conventions_note",
        {"path": CONVENTIONS_PIN["path"], "sha256": None, "size": None},
        tracked_paths)
    dependencies.append(conventions_entry)

    for entry in dependencies:
        if entry["required_tracked"] and not entry["tracked_at_head"]:
            blocks.append({
                "id": f"missing_tracked_input::{entry['role']}",
                "kind": "missing_tracked_evidence",
                "path": entry["path"],
                "expected_sha256": entry["expected_sha256"],
                "expected_size": entry["expected_size"],
                "reason": ("required evidence is not present in the HEAD tree; "
                           "this checker fails closed instead of inventing a "
                           "value"),
            })
        elif entry["available_on_disk"] and entry["hash_matches"] is False:
            blocks.append({
                "id": f"tracked_input_hash_mismatch::{entry['role']}",
                "kind": "hash_mismatch",
                "path": entry["path"],
                "expected_sha256": entry["expected_sha256"],
                "observed_sha256": entry["sha256"],
                "reason": "tracked evidence bytes drifted from the declared pin",
            })
        elif not entry["available_on_disk"]:
            blocks.append({
                "id": f"missing_tracked_input::{entry['role']}",
                "kind": "unreadable_tracked_evidence",
                "path": entry["path"],
                "expected_sha256": entry["expected_sha256"],
                "expected_size": entry["expected_size"],
                "reason": "declared tracked evidence is not readable on disk",
            })

    contract = None
    record_source = None
    companion = None
    reader_text = None
    samples = []
    recorder_end = None
    if "compiled_contract" in raw:
        try:
            contract = json.loads(raw["compiled_contract"].decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            blocks.append({
                "id": "contract_unparsable",
                "kind": "malformed_tracked_evidence",
                "path": CONTRACT_PIN["path"],
                "reason": f"tracked contract is not valid JSON: {error}",
            })
    if "sealed_major_recorder_run" in raw:
        try:
            records = [json.loads(line) for line
                       in raw["sealed_major_recorder_run"].splitlines()]
            samples = [record for record in records
                       if record.get("kind") == "major_recorder_sample"]
            starts = [record for record in records
                      if record.get("kind") == "major_recorder_start"]
            ends = [record for record in records
                    if record.get("kind") == "major_recorder_end"]
            record_source = starts[0].get("source") if starts else None
            recorder_end = ends[-1] if ends else None
            if len(samples) != ROW_COUNT:
                blocks.append({
                    "id": "sample_row_count_mismatch",
                    "kind": "malformed_tracked_evidence",
                    "path": RECORD_PIN["path"],
                    "reason": (f"sealed run carries {len(samples)} major "
                               f"recorder samples, expected {ROW_COUNT}"),
                })
            ordered_k = [sample.get("k") for sample in samples]
            if ordered_k != list(range(ROW_COUNT)):
                blocks.append({
                    "id": "sample_row_index_mismatch",
                    "kind": "malformed_tracked_evidence",
                    "path": RECORD_PIN["path"],
                    "reason": "sample k values are not exactly 0..500 in order",
                })
        except (ValueError, UnicodeDecodeError) as error:
            blocks.append({
                "id": "record_unparsable",
                "kind": "malformed_tracked_evidence",
                "path": RECORD_PIN["path"],
                "reason": f"sealed record is not valid JSONL: {error}",
            })
    if "companion_verification_record" in raw:
        try:
            companion = json.loads(raw["companion_verification_record"].decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            blocks.append({
                "id": "companion_unparsable",
                "kind": "malformed_tracked_evidence",
                "path": COMPANION_VERIFICATION_PIN["path"],
                "reason": f"companion verification record is not valid JSON: {error}",
            })
    if "companion_reader" in raw:
        reader_text = raw["companion_reader"].decode("utf-8", "replace")

    reader_constants = (_reader_constants(reader_text) if reader_text is not None
                        else {})
    for key, present in reader_constants.items():
        if not present:
            blocks.append({
                "id": f"reader_constant_absent::{key}",
                "kind": "reader_agreement_mismatch",
                "path": READER_PIN["path"],
                "reason": (f"the tracked reader does not pin {key}; the "
                           f"independent checker will not substitute a value"),
            })

    if record_source is not None:
        if record_source.get("original_cpp_sha256") != READER_PINNED["original_cpp_sha256"]:
            blocks.append({
                "id": "native_source_binding_mismatch",
                "kind": "reader_agreement_mismatch",
                "path": RECORD_PIN["path"],
                "reason": "sealed run native source SHA256 disagrees with the reader pin",
            })
        if record_source.get("insertion_line") != READER_PINNED["insertion_line"]:
            blocks.append({
                "id": "insertion_line_mismatch",
                "kind": "reader_agreement_mismatch",
                "path": RECORD_PIN["path"],
                "reason": "sealed run insertion line disagrees with the reader pin",
            })
    if contract is not None:
        identity = contract.get("identity", {})
        reference_revision = identity.get("reference_revision")
        if reference_revision != READER_PINNED["reference_revision"]:
            blocks.append({
                "id": "reference_revision_mismatch",
                "kind": "reader_agreement_mismatch",
                "path": CONTRACT_PIN["path"],
                "reason": (f"contract reference_revision {reference_revision!r} "
                           f"disagrees with {READER_PINNED['reference_revision']!r}"),
            })
        if companion is not None:
            if companion.get("reference_revision") != reference_revision:
                blocks.append({
                    "id": "companion_reference_revision_mismatch",
                    "kind": "reader_agreement_mismatch",
                    "path": COMPANION_VERIFICATION_PIN["path"],
                    "reason": "companion record reference revision drifted",
                })
            if companion.get("source") != record_source:
                blocks.append({
                    "id": "companion_source_binding_mismatch",
                    "kind": "reader_agreement_mismatch",
                    "path": COMPANION_VERIFICATION_PIN["path"],
                    "reason": ("companion record source block disagrees with "
                               "the sealed run source block"),
                })

    # -- untracked reference inputs --------------------------------------
    untracked = {}
    references = {}
    for key in sorted(UNTRACKED_INPUTS):
        rel_path, expected, expected_size, width, role = UNTRACKED_INPUTS[key]
        item = {
            "role": role,
            "path": rel_path,
            "tracked_at_head": False,
            "tracked_status": "untracked_gitignored",
            "expected_sha256": expected,
            "expected_size": expected_size,
            "expected_row_width": width,
            "expected_rows": ROW_COUNT,
            "available_on_disk": False,
            "hash_matches": None,
            "size_matches": None,
        }
        try:
            payload = _read_bytes(repo_root, rel_path)
        except OSError:
            blocks.append({
                "id": f"missing_untracked_input::{key}",
                "kind": "missing_raw_input",
                "path": rel_path,
                "expected_sha256": expected,
                "expected_size": expected_size,
                "expected_row_width": width,
                "expected_rows": ROW_COUNT,
                "reason": ("required raw reference input is not on disk and is "
                           "not repository-tracked; the checker fails closed "
                           "and invents no value for it"),
            })
            untracked[key] = item
            continue
        digest = _sha256(payload)
        item["available_on_disk"] = True
        item["sha256"] = digest
        item["size"] = len(payload)
        item["hash_matches"] = (digest == expected)
        item["size_matches"] = (len(payload) == expected_size)
        if not item["hash_matches"] or not item["size_matches"]:
            blocks.append({
                "id": f"raw_input_pin_mismatch::{key}",
                "kind": "hash_mismatch",
                "path": rel_path,
                "expected_sha256": expected,
                "observed_sha256": digest,
                "expected_size": expected_size,
                "observed_size": len(payload),
                "reason": "raw reference input drifted from its declared pin",
            })
        untracked[key] = item
        references[key] = (payload, width)

    slots = []
    if contract is not None:
        try:
            slots = _contract_schedule_slots(contract)
        except (ValueError, KeyError) as error:
            blocks.append({
                "id": "contract_slot_derivation_failed",
                "kind": "malformed_tracked_evidence",
                "path": CONTRACT_PIN["path"],
                "reason": f"cannot derive the three schedule_metadata slots: {error}",
            })

    # -- per-stream recomputation ----------------------------------------
    streams = []
    if samples and len(samples) == ROW_COUNT and slots:
        for slot in slots:
            key = f"{slot['array']}_{slot['slot']}"
            try:
                column = [sample["major_root_outputs"][slot["array"]][slot["slot"]]
                          for sample in samples]
            except (KeyError, IndexError, TypeError) as error:
                blocks.append({
                    "id": f"measured_column_unreadable::{key}",
                    "kind": "malformed_tracked_evidence",
                    "path": RECORD_PIN["path"],
                    "reason": f"cannot read the recorded column: {error}",
                })
                continue
            measured_width = len(samples[0]["major_root_outputs"][slot["array"]])
            structural = _stream_recomputation(
                [sample["major_root_outputs"][slot["array"]] for sample in samples],
                slot["slot"], slot["gain"])
            structural["measured_row_width"] = measured_width
            structural["measured_row_width_expected"] = slot["array_element_count"]
            structural["measured_row_width_matches_contract_order"] = (
                measured_width == slot["array_element_count"])
            structural["shifted_row_check"] = _shifted_row_check(
                [sample["major_root_outputs"][slot["array"]] for sample in samples],
                slot["slot"], slot["gain"])
            stream = {
                "id": key,
                "observable_id": slot["observable_id"],
                "array": slot["array"],
                "slot": slot["slot"],
                "unit": slot["unit"],
                "gain": slot["gain"],
                "semantic_status": slot["semantic_status"],
                "internal_rule": slot["internal_rule"],
                "contract_source": slot["contract_source"],
                "semantic_class": "scheduling_evidence",
                "rows": ROW_COUNT,
                "recomputed": structural,
                "reported_agreement": {
                    "rows": ROW_COUNT == CLAIMED_ROWS,
                    "measured_division_differs": (
                        structural["measured_division_differs_from_product"]
                        == CLAIMED_MEASURED_DIVISION_DIFFS[key]),
                },
                "claimed_rows": CLAIMED_ROWS,
                "claimed_division_diffs": CLAIMED_MEASURED_DIVISION_DIFFS[key],
                "column_sha256": _sha256(b"".join(
                    _bits(value) for value in column)),
            }
            streams.append(stream)

    # -- reference decomposition -----------------------------------------
    reference_blocks = {}
    if slots:
        for slot in slots:
            key = f"{slot['array']}_{slot['slot']}"
            reference_key = {
                "Vehicle60": "vehicle60_reference",
                "Sensor30": "sensor30_reference",
                "GPS30": "gps30_reference",
            }[slot["array"]]
            if reference_key not in references:
                continue
            payload, width = references[reference_key]
            entry, notes = _reference_recomputation(
                payload, width, slot["unit"])
            if notes:
                blocks.append({
                    "id": f"reference_decode_failed::{reference_key}",
                    "kind": "malformed_raw_input",
                    "path": UNTRACKED_INPUTS[reference_key][0],
                    "reason": "; ".join(notes),
                })
                continue
            reference_rows, _ = _decode_rows(payload, width, ROW_COUNT)
            entry["array_crosscheck"] = _reference_array_crosscheck(
                reference_rows, samples, slot, slot["gain"])
            entry["role"] = UNTRACKED_INPUTS[reference_key][4]
            entry["source_key"] = reference_key
            entry["claimed_division_rows_matched"] = (
                CLAIMED_REFERENCE_DIVISION_ROWS)
            entry["claimed_product_rows_matched"] = (
                CLAIMED_REFERENCE_PRODUCT_ROWS)
            entry["reported_agreement"] = {
                "product_rows_matched": (
                    entry["product_rows_matched"]
                    == CLAIMED_REFERENCE_PRODUCT_ROWS),
                "division_rows_matched": (
                    entry["division_rows_matched"]
                    == CLAIMED_REFERENCE_DIVISION_ROWS),
            }
            entry["time_column_sha256"] = _sha256(b"".join(
                _bits(struct.unpack_from("<d", payload, row * width * 8)[0])
                for row in range(ROW_COUNT)))
            reference_blocks[key] = entry

    gains = {slot["array"]: slot["gain"] for slot in slots}
    cross_stream = (_stream_measurements(samples, gains)
                    if samples and len(samples) == ROW_COUNT else None)
    if cross_stream is not None:
        sensor = next((slot for slot in slots if slot["array"] == "Sensor30"), None)
        gps = next((slot for slot in slots if slot["array"] == "GPS30"), None)
        if sensor is not None and gps is not None:
            sensor_column = [sample["major_root_outputs"]["Sensor30"][sensor["slot"]]
                             for sample in samples]
            gps_column = [sample["major_root_outputs"]["GPS30"][gps["slot"]]
                          for sample in samples]
            cross_stream["sensor30_slot_equals_gps30_slot"] = (
                all(_bits(a) == _bits(b) for a, b in zip(sensor_column, gps_column)))
            cross_stream["streams_with_nonzero_division_diff"] = sum(
                1 for stream in streams
                if stream["recomputed"]["measured_division_differs_from_product"] > 0)
            cross_stream["form_disagreement_indices_shared_by_all_streams"] = (
                len({tuple(stream["recomputed"]
                           ["form_disagreement_indices_first"])
                     for stream in streams}) == 1 if streams else False)

    if blocks:
        status = "blocked"
    else:
        status = "ok"

    document = {
        "schema": SCHEMA,
        "kind": KIND,
        "version": VERSION,
        "date": DATE,
        "issue": ISSUE,
        "title": TITLE,
        "work_class": WORK_CLASS,
        "layer": LAYER,
        "authority": AUTHORITY,
        "effective": False,
        "generator": GENERATOR,
        "generator_command": (
            "python -B tools/check_g6_time_field_forms.py "
            "--repo-root . --out validation/g6-time-field-forms-20260914.json"),
        "base_ancestor": ANCESTOR,
        "status": status,
        "block_reason_codes": sorted({block["id"] for block in blocks}),
        "r1_status": R1_STATUS,
        "g6_acceptance": False,
        "physical_accuracy": False,
        "issues_closed": False,
        "budget_approved": False,
        "pending_approvals": [],
        "open_items": [{"id": item, "state": state} for item, state in OPEN_ITEMS],
        "identity": {
            "model": "Exp1_MinModelTemp",
            "case": "C0",
            "reference_revision": READER_PINNED["reference_revision"],
            "reference_encoding": "little-endian binary64 rows with retained "
                                  "leading time column",
            "fixed_step_s": FIXED_STEP_S,
            "stop_time_s": STOP_TIME_S,
            "rows": ROW_COUNT,
            "row_index_domain": [0, ROW_COUNT - 1],
            "recorded_time_form_in_native_driver": DIVISION_FORM,
            "recorded_time_form_in_major_roots": PRODUCT_FORM,
        },
        "evidence_dependencies": {
            "tracked_evidence_only": True,
            "head_tree_available": bool(tracked_paths),
            "provenance": provenance,
            "dependencies": dependencies,
            "reader_pinned_constants_present": reader_constants,
            "reader_pinned_constants": dict(READER_PINNED),
            "conventions_note": {
                "path": CONVENTIONS_PIN["path"],
                "tracked_at_head": conventions_entry["tracked_at_head"],
                "sha256": conventions_entry["sha256"],
                "size": conventions_entry["size"],
            },
        },
        "form_under_test": {
            "product_form": PRODUCT_FORM,
            "product_form_id": PRODUCT_FORM_ID,
            "division_form": DIVISION_FORM,
            "division_form_id": DIVISION_FORM_ID,
            "comparison": "bit-exact binary64 equality of the packed 8-byte value",
            "product_form_attribution": (
                "native major root expressions as recorded by the frozen "
                "contract and the sealed run"),
            "division_form_attribution": (
                "native driver input_time_s, which is a different recorded "
                "quantity and must not be conflated with the major outputs"),
        },
        "contract_time_slots": slots,
        "recomputed": {
            "status": status,
            "streams": streams,
            "reference": reference_blocks,
            "cross_stream": cross_stream,
            "reported_counts_supported": {
                "rows_501": all(stream["recomputed"]["row_count"] == CLAIMED_ROWS
                                for stream in streams) and len(streams) == 3,
                "reference_product_501_of_501": all(
                    entry["reported_agreement"]["product_rows_matched"]
                    for entry in reference_blocks.values(
                    )) and len(reference_blocks) == 3,
                "reference_division_429_of_501": all(
                    entry["reported_agreement"]["division_rows_matched"]
                    for entry in reference_blocks.values(
                    )) and len(reference_blocks) == 3,
                "measured_division_diffs_72_61_61": all(
                    stream["reported_agreement"]["measured_division_differs"]
                    for stream in streams) and len(streams) == 3,
                "shifted_row_17_rejected": all(
                    stream["recomputed"]["shifted_row_check"]
                    ["only_shifted_row_rejected"] for stream in streams),
            },
        },
        "evidence_class_split": {
            "scheduling_evidence": [
                "the three schedule_metadata time fields and their row counts",
                "the product-form/division-form row structure per stream",
                "the retained leading time column of the split reference arrays",
            ],
            "dynamics_or_physical_budget": [
                "all 118 non-time slots of Vehicle60/Sensor30/GPS30",
                "any absolute or relative numerical error budget",
                "physical accuracy of any mapped observable",
            ],
            "evaluated_here": False,
            "note": ("this checker touches scheduling evidence only; it "
                     "neither evaluates nor approves any dynamics or physical "
                     "budget, and it computes no error magnitude"),
        },
        "untracked_inputs": {
            "tracked_evidence_only": False,
            "note": ("the split reference arrays are excluded from the index by "
                     "the .gitignore rule /validation/*/; they are raw inputs "
                     "bound by SHA256 and size and are never treated as tracked "
                     "evidence"),
            "inputs": untracked,
        },
        "missing_inputs": sorted(
            ({"id": block["id"], "path": block.get("path"),
              "expected_sha256": block.get("expected_sha256"),
              "expected_size": block.get("expected_size")}
             for block in blocks
             if block["kind"] in ("missing_tracked_evidence",
                                  "unreadable_tracked_evidence",
                                  "missing_raw_input")),
            key=lambda item: item["id"] or ""),
        "blockers": sorted(blocks, key=lambda block: block["id"]),
        "reproduce": {
            "inputs_are_env_specific": False,
            "required_tracked_paths": [
                RECORD_PIN["path"], CONTRACT_PIN["path"],
                COMPANION_VERIFICATION_PIN["path"],
                COMPANION_REJECTION_PIN["path"], READER_PIN["path"],
                CONVENTIONS_PIN["path"],
            ],
            "required_raw_paths": [
                UNTRACKED_INPUTS[key][0] for key in sorted(UNTRACKED_INPUTS)],
            "required_raw_sha256": {
                UNTRACKED_INPUTS[key][0]: UNTRACKED_INPUTS[key][1]
                for key in sorted(UNTRACKED_INPUTS)},
            "required_raw_sizes": {
                UNTRACKED_INPUTS[key][0]: UNTRACKED_INPUTS[key][2]
                for key in sorted(UNTRACKED_INPUTS)},
            "decoding": {
                "record": "one JSON object per line; kind=major_recorder_sample",
                "reference": (
                    "501 rows x (slots + 1) little-endian binary64; column 0 is "
                    "the retained time column"),
                "comparison": "bit-exact packed binary64 equality",
            },
            "record_source_identity": record_source,
            "recorder_end": recorder_end,
        },
        "nonclaims": list(NONCLAIMS),
        "scope_limits": list(SCOPE_LIMITS),
    }
    return document, blocks


def build_result(repo_root=None):
    repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
    document, _ = build_document(repo_root)
    return document


REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Deterministic serialization
# --------------------------------------------------------------------------


def dumps(document):
    """Byte-stable JSON text: fixed key order, 2-space indent, ASCII, LF."""
    return json.dumps(document, indent=2, ensure_ascii=True,
                      sort_keys=False) + "\n"


def write_document(document, out_path):
    """Create the output exclusively; never overwrite an existing file."""
    out_path = Path(out_path)
    data = dumps(document).encode("utf-8")
    if out_path.exists() or out_path.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing file: {out_path}")
    with out_path.open("xb") as handle:
        handle.write(data)
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Fail-closed structural validation
# --------------------------------------------------------------------------

REQUIRED_TOP_KEYS = frozenset({
    "schema", "kind", "version", "date", "issue", "title", "work_class",
    "layer", "authority", "effective", "generator", "generator_command",
    "base_ancestor", "status", "block_reason_codes", "r1_status",
    "g6_acceptance", "physical_accuracy", "issues_closed", "budget_approved",
    "pending_approvals", "open_items", "identity", "evidence_dependencies",
    "form_under_test", "contract_time_slots", "recomputed",
    "evidence_class_split", "untracked_inputs", "missing_inputs", "blockers",
    "reproduce", "nonclaims", "scope_limits",
})

REQUIRED_STREAM_KEYS = frozenset({
    "id", "observable_id", "array", "slot", "unit", "gain",
    "semantic_status", "internal_rule", "contract_source", "semantic_class",
    "rows", "recomputed", "reported_agreement", "claimed_rows",
    "claimed_division_diffs", "column_sha256",
})

REQUIRED_STREAM_RECOMPUTED_KEYS = frozenset({
    "row_count", "gain", "form_clock", "measured_product_rows_matched",
    "measured_product_rows_mismatch", "measured_product_mismatch_indices",
    "measured_division_rows_matched", "measured_division_differs_from_product",
    "measured_division_mismatch_indices", "form_disagreement_rows",
    "form_disagreement_indices_first", "form_disagreement_indices_count",
    "measured_row_width", "measured_row_width_expected",
    "measured_row_width_matches_contract_order", "shifted_row_check",
})

REQUIRED_REFERENCE_KEYS = frozenset({
    "role", "source_key", "row_count", "row_width", "unit",
    "leading_time_column_index", "gain_applied_to_clock", "array_columns",
    "array_columns_native_unit", "product_rows_matched", "division_rows_matched",
    "product_rows_mismatch", "division_rows_mismatch", "form_disagreement_rows",
    "form_disagreement_indices_first", "form_disagreement_indices_count",
    "claimed_division_rows_matched", "claimed_product_rows_matched",
    "reported_agreement", "array_crosscheck", "time_column_sha256",
})

EXPECTED_SLOTS = (
    ("Vehicle60", 2, "s", 1.0),
    ("Sensor30", 0, "us", 1000000.0),
    ("GPS30", 0, "us", 1000000.0),
)

FORBIDDEN_KEYS = frozenset({
    "budget", "budgets", "budget_request", "budget_approved_value",
    "approval", "approvals", "approved", "accepted", "acceptance",
    "error_budget", "numerical_budget", "physical_budget", "closure",
    "closed", "contract_freeze", "frozen_contract", "g6_accepted",
    "r1_passed", "g6_pass", "full_pass", "issue_closed", "signature",
    "signoff", "sign_off",
})


class ValidationError(Exception):
    """Raised when a document is malformed beyond structural reporting."""


def _is_int(value):
    return type(value) is int


def _int_list(value):
    return isinstance(value, list) and all(_is_int(item) for item in value)


def validate(document, repo_root=None, recompute=True):
    """Fail-closed structural validation of a time-field-forms document.

    Returns {"ok": bool, "codes": [sorted codes], "errors": [messages]}.
    """
    codes = set()
    errors = []

    def flag(code, message):
        codes.add(code)
        errors.append(message)

    if not isinstance(document, dict):
        return {"ok": False, "codes": ["payload_not_object"],
                "errors": ["time-field document must be a JSON object"]}

    if document.get("schema") != SCHEMA or document.get("kind") != KIND:
        flag("schema_or_kind_mismatch",
             f"schema/kind mismatch: {document.get('schema')!r}/"
             f"{document.get('kind')!r}")
    if document.get("version") != VERSION or not _is_int(document.get("version")):
        flag("version_mismatch",
             f"version must be integer {VERSION}, got {document.get('version')!r}")

    missing = sorted(REQUIRED_TOP_KEYS - set(document))
    if missing:
        flag("missing_key", f"missing required top-level keys: {missing}")

    # -- decision constants ----------------------------------------------
    if document.get("r1_status") != R1_STATUS:
        flag("r1_status_mismatch",
             f"r1_status must be {R1_STATUS!r}, got {document.get('r1_status')!r}")
    if document.get("g6_acceptance") is not False:
        flag("g6_acceptance_claim", "g6_acceptance must be false")
    if document.get("physical_accuracy") is not False:
        flag("physical_accuracy_claim", "physical_accuracy must be false")
    if document.get("issues_closed") is not False:
        flag("issue_closure_claim", "issues_closed must be false")
    if document.get("budget_approved") is not False:
        flag("budget_approval_claim", "budget_approved must be false")
    if document.get("pending_approvals") != []:
        flag("pending_approvals_present", "pending_approvals must be empty")
    if document.get("effective") is not False:
        flag("effective_claim", "effective must be false")
    if document.get("authority") != AUTHORITY:
        flag("authority_claim",
             f"authority must be {AUTHORITY!r}, got {document.get('authority')!r}")
    if document.get("work_class") != WORK_CLASS:
        flag("work_class_mismatch", f"work_class must be {WORK_CLASS!r}")

    open_items = document.get("open_items")
    if not isinstance(open_items, list) or not open_items:
        flag("open_items_missing", "open_items must be a non-empty list")
    else:
        states = {}
        for item in open_items:
            if not isinstance(item, dict) or set(item) != {"id", "state"}:
                flag("open_item_shape", f"malformed open item: {item!r}")
                continue
            states[item["id"]] = item["state"]
        for expected_id, expected_state in OPEN_ITEMS:
            if expected_id == "g6" and states.get("g6") != expected_state:
                flag("g6_not_open", "G6 must remain open")
                continue
            if expected_id == "full" and states.get("full") != expected_state:
                flag("full_not_open", "Full must remain open")
                continue
            if states.get(expected_id) != expected_state:
                flag("open_item_not_open",
                     f"open item {expected_id!r} must be {expected_state!r}, "
                     f"got {states.get(expected_id)!r}")

    # -- forbidden surface ------------------------------------------------
    for key in sorted(FORBIDDEN_KEYS & set(document)):
        flag("forbidden_key", f"forbidden key present: {key}")
    for container_key in ("evidence_class_split", "recomputed", "identity"):
        container = document.get(container_key)
        if isinstance(container, dict):
            for key in sorted(FORBIDDEN_KEYS & set(container)):
                flag("forbidden_key", f"forbidden key in {container_key}: {key}")

    # -- evidence dependencies -------------------------------------------
    dependencies = document.get("evidence_dependencies")
    dependency_by_role = {}
    if not isinstance(dependencies, dict):
        flag("evidence_dependencies_missing",
             "evidence_dependencies must be an object")
    else:
        if dependencies.get("tracked_evidence_only") is not True:
            flag("tracked_evidence_policy",
                 "evidence_dependencies.tracked_evidence_only must be true")
        items = dependencies.get("dependencies")
        if not isinstance(items, list) or not items:
            flag("evidence_dependencies_empty",
                 "evidence_dependencies.dependencies must be non-empty")
        else:
            for item in items:
                if not isinstance(item, dict):
                    flag("dependency_shape", f"malformed dependency: {item!r}")
                    continue
                role = item.get("role")
                dependency_by_role[role] = item
                if item.get("required_tracked") is not True:
                    continue
                if item.get("tracked_at_head") is not True:
                    flag("dependency_not_tracked",
                         f"required evidence {role!r} is not tracked at HEAD")
                if item.get("hash_matches") is False:
                    flag("dependency_hash_mismatch",
                         f"required evidence {role!r} sha256 drift")
                if item.get("size_matches") is False:
                    flag("dependency_size_mismatch",
                         f"required evidence {role!r} size drift")
                if item.get("expected_sha256") is None:
                    if role != "time_conventions_note":
                        flag("dependency_pin_absent",
                             f"required evidence {role!r} declares no sha256 pin")
                    if item.get("sha256") is None:
                        flag("dependency_hash_unrecorded",
                             f"required evidence {role!r} records no observed "
                             f"sha256")
        required_roles = {"sealed_major_recorder_run", "compiled_contract",
                          "companion_verification_record",
                          "companion_rejected_assumption", "companion_reader",
                          "time_conventions_note"}
        absent = sorted(required_roles - set(dependency_by_role))
        if absent:
            flag("dependency_missing",
                 f"evidence_dependencies misses roles: {absent}")
        constants = dependencies.get("reader_pinned_constants_present")
        if isinstance(constants, dict):
            for key, present in constants.items():
                if present is not True:
                    flag("reader_constant_absent",
                         f"tracked reader does not pin {key}")
        provenance = dependencies.get("provenance")
        if not isinstance(provenance, dict):
            flag("provenance_missing",
                 "evidence_dependencies.provenance must be an object")
        else:
            if provenance.get("base_ancestor") != ANCESTOR:
                flag("provenance_anchor_mismatch",
                     "provenance.base_ancestor must name the stable anchor")
            if provenance.get("observed_head_recording") != \
                    "deliberately_not_recorded":
                flag("provenance_observed_head_recorded",
                     "the observed HEAD must never be recorded in the document")
            if document.get("status") == "ok":
                if provenance.get("anchor_is_ancestor_of_observed_head") \
                        is not True:
                    flag("anchor_not_ancestor",
                         "status 'ok' requires the anchor to be an ancestor of "
                         "the observed HEAD")
                if provenance.get("evidence_paths_unchanged_since_anchor") \
                        is not True:
                    flag("pinned_path_overlap",
                         "status 'ok' requires every pinned evidence path to "
                         "be unchanged since the anchor")
                if provenance.get("changed_pinned_paths") != []:
                    flag("pinned_path_overlap",
                         "status 'ok' requires no changed pinned paths")

    # -- form under test --------------------------------------------------
    forms = document.get("form_under_test")
    if not isinstance(forms, dict):
        flag("form_under_test_missing", "form_under_test must be an object")
    else:
        if forms.get("product_form") != PRODUCT_FORM:
            flag("product_form_mismatch", f"product_form must be {PRODUCT_FORM!r}")
        if forms.get("division_form") != DIVISION_FORM:
            flag("division_form_mismatch", f"division_form must be {DIVISION_FORM!r}")

    # -- contract slots ---------------------------------------------------
    slots = document.get("contract_time_slots")
    if not isinstance(slots, list) or len(slots) != 3:
        flag("slot_set_mismatch", "contract_time_slots must list exactly 3 slots")
    else:
        observed = tuple((slot.get("array"), slot.get("slot"), slot.get("unit"),
                          slot.get("gain")) for slot in slots
                         if isinstance(slot, dict))
        if observed != EXPECTED_SLOTS:
            flag("slot_set_mismatch",
                 f"slot set {observed!r} != {EXPECTED_SLOTS!r}")
        for slot in slots:
            if not isinstance(slot, dict):
                flag("slot_shape", f"malformed slot: {slot!r}")
                continue
            if slot.get("semantic_status") != SLOT_STATUS:
                flag("slot_not_schedule_metadata",
                     f"{slot.get('array')} is not {SLOT_STATUS}")
            if slot.get("internal_rule") != "finite_binary64_value_equal":
                flag("slot_rule_mismatch",
                     f"{slot.get('array')} rule must be finite_binary64_value_equal")

    # -- recomputation block ---------------------------------------------
    recomputed = document.get("recomputed")
    streams_by_id = {}
    if not isinstance(recomputed, dict):
        flag("recomputed_missing", "recomputed must be an object")
        return _result(codes, errors)

    status = document.get("status")
    if status not in ("ok", "blocked"):
        flag("status_invalid", f"status must be 'ok' or 'blocked', got {status!r}")
    blockers = document.get("blockers")
    if status == "ok":
        if blockers != []:
            flag("blockers_present", "status 'ok' requires an empty blockers list")
        if document.get("block_reason_codes") != []:
            flag("block_reason_codes_present",
                 "status 'ok' requires empty block_reason_codes")
    else:
        if not isinstance(blockers, list) or not blockers:
            flag("blockers_missing",
                 "status 'blocked' requires a non-empty blockers list")
        else:
            for block in blockers:
                if not isinstance(block, dict) or "id" not in block:
                    flag("blocker_shape", f"malformed blocker: {block!r}")
                    continue
                if block.get("kind") in ("missing_tracked_evidence",
                                         "unreadable_tracked_evidence",
                                         "missing_raw_input"):
                    if not block.get("path"):
                        flag("blocker_path_missing",
                             f"blocker {block.get('id')!r} has no path")
                    if (block.get("expected_sha256") is None
                            and "time_conventions_note" not in str(block.get("id"))):
                        flag("blocker_identity_missing",
                             f"blocker {block.get('id')!r} has no expected sha256")
                if "value" in block or "assumed_value" in block:
                    flag("blocker_invented_value",
                         f"blocker {block.get('id')!r} carries an invented value")
            codes_seen = sorted({block.get("id") for block in blockers
                                 if isinstance(block, dict)})
            if document.get("block_reason_codes") != codes_seen:
                flag("block_reason_codes_mismatch",
                     "block_reason_codes must list the blocker ids")

    if recomputed.get("status") != status:
        flag("recomputed_status_mismatch",
             "recomputed.status must equal the top-level status")

    streams = recomputed.get("streams")
    if not isinstance(streams, list):
        flag("streams_missing", "recomputed.streams must be a list")
        streams = []
    if status == "ok" and len(streams) != 3:
        flag("stream_count_mismatch",
             f"status 'ok' requires exactly 3 recomputed streams, got {len(streams)}")
    for stream in streams:
        if not isinstance(stream, dict):
            flag("stream_shape", f"malformed stream: {stream!r}")
            continue
        absent = sorted(REQUIRED_STREAM_KEYS - set(stream))
        if absent:
            flag("stream_missing_key", f"stream misses keys: {absent}")
            continue
        stream_id = stream["id"]
        streams_by_id[stream_id] = stream
        if stream["semantic_class"] != "scheduling_evidence":
            flag("stream_class_mismatch",
                 f"{stream_id} must be classified as scheduling_evidence")
        if stream["semantic_status"] != SLOT_STATUS:
            flag("stream_not_schedule_metadata",
                 f"{stream_id} is not {SLOT_STATUS}")
        if stream["rows"] != ROW_COUNT or stream["claimed_rows"] != CLAIMED_ROWS:
            flag("stream_row_claim_mismatch",
                 f"{stream_id} rows must be {ROW_COUNT}/{CLAIMED_ROWS}")
        structural = stream["recomputed"]
        if not isinstance(structural, dict):
            flag("stream_recomputed_shape",
                 f"{stream_id} recomputed block must be an object")
            continue
        absent = sorted(REQUIRED_STREAM_RECOMPUTED_KEYS - set(structural))
        if absent:
            flag("stream_recomputed_missing_key",
                 f"{stream_id} recomputed misses keys: {absent}")
            continue
        if structural["row_count"] != ROW_COUNT:
            flag("stream_row_count_mismatch",
                 f"{stream_id} recomputed row_count must be {ROW_COUNT}")
        if structural["gain"] != stream["gain"]:
            flag("stream_gain_mismatch",
                 f"{stream_id} recomputed gain must match the contract gain")
        clocks = structural["form_clock"]
        if not isinstance(clocks, dict) or clocks.get(PRODUCT_FORM_ID) != "k * 0.001" \
                or clocks.get(DIVISION_FORM_ID) != "k / 1000":
            flag("stream_form_clock_mismatch",
                 f"{stream_id} form_clock must name both clock forms")
        product_mismatch = structural["measured_product_rows_mismatch"]
        division_diffs = structural["measured_division_differs_from_product"]
        if product_mismatch != 0:
            flag("product_form_unsupported",
                 f"{stream_id} does not match the product form on every row")
        if not _is_int(division_diffs) or division_diffs < 0:
            flag("stream_diff_count_invalid",
                 f"{stream_id} division diff count must be a non-negative int")
        for key in ("measured_product_mismatch_indices",
                    "measured_division_mismatch_indices",
                    "form_disagreement_indices_first"):
            value = structural[key]
            if not _int_list(value):
                flag("stream_index_list_invalid",
                     f"{stream_id}.{key} must be a list of integers")
            elif len(value) != len(set(value)) or value != sorted(value):
                flag("stream_index_list_order",
                     f"{stream_id}.{key} must be sorted and unique")
        if _int_list(structural["measured_product_mismatch_indices"]):
            if len(structural["measured_product_mismatch_indices"]) != product_mismatch:
                flag("stream_product_count_mismatch",
                     f"{stream_id} product mismatch count disagrees with its "
                     f"index list")
        if _int_list(structural["measured_division_mismatch_indices"]):
            if (len(structural["measured_division_mismatch_indices"])
                    != division_diffs):
                flag("stream_division_count_mismatch",
                     f"{stream_id} division diff count disagrees with its "
                     f"index list")
        if structural["form_disagreement_indices_count"] != \
                structural["form_disagreement_rows"]:
            flag("stream_disagreement_count_mismatch",
                 f"{stream_id} form disagreement count disagrees with its rows")
        if len(structural["form_disagreement_indices_first"]) > min(
                16, structural["form_disagreement_rows"]):
            flag("stream_disagreement_prefix_too_long",
                 f"{stream_id} disagreement index prefix exceeds its count")
        if structural["measured_division_rows_matched"] + division_diffs != ROW_COUNT:
            flag("stream_row_arithmetic",
                 f"{stream_id} matched + differing rows must total {ROW_COUNT}")
        if structural["measured_product_rows_matched"] + product_mismatch != ROW_COUNT:
            flag("stream_row_arithmetic",
                 f"{stream_id} product matched + mismatch must total {ROW_COUNT}")
        expected_width = structural["measured_row_width_expected"]
        if structural["measured_row_width"] != expected_width:
            flag("stream_row_width_mismatch",
                 f"{stream_id} recorded row width "
                 f"{structural['measured_row_width']} != contract order "
                 f"{expected_width}")
        if structural["measured_row_width_matches_contract_order"] is not True:
            flag("stream_row_width_flag",
                 f"{stream_id} row width flag must be true")
        shifted = structural["shifted_row_check"]
        if not isinstance(shifted, dict):
            flag("shifted_check_shape", f"{stream_id} shifted check malformed")
        else:
            if shifted.get("unshifted_mismatches") != []:
                flag("shifted_unshifted_mismatch",
                     f"{stream_id} unshifted column already mismatches")
            if shifted.get("shifted_mismatches") != [SHIFT_INDEX]:
                flag("shifted_row_not_rejected",
                     f"{stream_id} shifting row {SHIFT_INDEX} must reject "
                     f"exactly that row")
            if shifted.get("index") != SHIFT_INDEX:
                flag("shifted_index_mismatch",
                     f"{stream_id} shifted check index must be {SHIFT_INDEX}")
            if shifted.get("only_shifted_row_rejected") is not True:
                flag("shifted_flag_mismatch",
                     f"{stream_id} only_shifted_row_rejected must be true")
        claimed = stream["claimed_division_diffs"]
        if claimed != CLAIMED_MEASURED_DIVISION_DIFFS[stream_id]:
            flag("stream_claimed_diff_mismatch",
                 f"{stream_id} claimed diff count must use the recorded value")
        agreement = stream["reported_agreement"]
        if not isinstance(agreement, dict):
            flag("stream_agreement_shape",
                 f"{stream_id} reported_agreement must be an object")
        elif agreement.get("measured_division_differs") is not (
                division_diffs == claimed):
            flag("stream_agreement_flag",
                 f"{stream_id} reported agreement flag disagrees with the "
                 f"recomputed count")

    if status == "ok":
        if set(streams_by_id) != {f"{array}_{slot}" for array, slot, _, _ in
                                  EXPECTED_SLOTS}:
            flag("stream_set_mismatch",
                 f"stream ids {sorted(streams_by_id)} do not cover the three "
                 f"schedule_metadata slots")

    # -- reference decomposition -----------------------------------------
    reference = recomputed.get("reference")
    if not isinstance(reference, dict):
        flag("reference_missing", "recomputed.reference must be an object")
    elif status == "ok":
        if len(reference) != 3:
            flag("reference_count_mismatch",
                 "status 'ok' requires three reference decompositions")
        for key, entry in sorted(reference.items()):
            if not isinstance(entry, dict):
                flag("reference_shape", f"malformed reference entry {key!r}")
                continue
            absent = sorted(REQUIRED_REFERENCE_KEYS - set(entry))
            if absent:
                flag("reference_missing_key",
                     f"{key} reference entry misses keys: {absent}")
                continue
            if entry.get("row_count") != ROW_COUNT:
                flag("reference_rows_mismatch",
                     f"{key} reference row count must be {ROW_COUNT}")
            if entry.get("division_rows_matched") != CLAIMED_REFERENCE_DIVISION_ROWS:
                flag("reported_division_count_changed",
                     f"{key} division rows matched must still be "
                     f"{CLAIMED_REFERENCE_DIVISION_ROWS}")
            if entry.get("product_rows_matched") != CLAIMED_REFERENCE_PRODUCT_ROWS:
                flag("reported_product_count_changed",
                     f"{key} product rows matched must still be "
                     f"{CLAIMED_REFERENCE_PRODUCT_ROWS}")
            if entry.get("gain_applied_to_clock") != 1.0:
                flag("reference_clock_gain_changed",
                     f"{key} retained time column must be an unscaled seconds "
                     f"clock")
            if entry.get("unit") != "s":
                flag("reference_clock_unit_changed",
                     f"{key} retained time column must be recorded in seconds")
            if not _int_list(entry.get("form_disagreement_indices_first")):
                flag("reference_index_list_invalid",
                     f"{key} form_disagreement_indices_first must be integers")
            if entry.get("form_disagreement_indices_count") != \
                    entry.get("form_disagreement_rows"):
                flag("reference_disagreement_count_mismatch",
                     f"{key} disagreement count disagrees with its rows")
            if entry.get("leading_time_column_index") != 0:
                flag("reference_time_column_mismatch",
                     f"{key} retained time column must be index 0")
            if (entry.get("product_rows_mismatch", 0)
                    + entry.get("product_rows_matched", 0) != ROW_COUNT):
                flag("reference_row_arithmetic",
                     f"{key} product rows do not total {ROW_COUNT}")
            if (entry.get("division_rows_mismatch", 0)
                    + entry.get("division_rows_matched", 0) != ROW_COUNT):
                flag("reference_row_arithmetic",
                     f"{key} division rows do not total {ROW_COUNT}")
            crosscheck = entry.get("array_crosscheck")
            if not isinstance(crosscheck, dict):
                flag("reference_crosscheck_missing",
                     f"{key} array_crosscheck must be an object")
            else:
                if crosscheck.get("slot_reference_column_equals_clock_times_gain") \
                        is not True:
                    flag("reference_slot_not_product_form",
                         f"{key} reference time column does not match the "
                         f"product form")
                if crosscheck.get("slot_time_column_matches_measured_slot") is not True:
                    flag("reference_slot_unbound",
                         f"{key} reference time column does not bind to the "
                         f"measured slot")
                if not _int_list(crosscheck.get("columns_without_a_full_match")):
                    flag("reference_crosscheck_shape",
                         f"{key} columns_without_a_full_match must be integers")
                if crosscheck.get("clock_column", {}).get("index") != 0:
                    flag("reference_crosscheck_clock_index",
                         f"{key} crosscheck clock column must be index 0")

    # -- reported support flags ------------------------------------------
    supported = recomputed.get("reported_counts_supported")
    if not isinstance(supported, dict):
        flag("reported_support_missing",
             "recomputed.reported_counts_supported must be an object")
    elif status == "ok":
        # A blocked document legitimately cannot support these counts; only a
        # document that claims status 'ok' is required to support all of them.
        for key in ("rows_501", "reference_product_501_of_501",
                    "reference_division_429_of_501",
                    "measured_division_diffs_72_61_61",
                    "shifted_row_17_rejected"):
            if supported.get(key) is not True:
                flag("reported_count_unsupported",
                     f"recomputation no longer supports {key}")

    # -- evidence class split --------------------------------------------
    split = document.get("evidence_class_split")
    if not isinstance(split, dict):
        flag("evidence_class_split_missing",
             "evidence_class_split must be an object")
    else:
        if split.get("evaluated_here") is not False:
            flag("budget_evaluated",
                 "evidence_class_split.evaluated_here must be false")
        scheduling = split.get("scheduling_evidence")
        if not isinstance(scheduling, list) or not scheduling:
            flag("scheduling_evidence_missing",
                 "scheduling_evidence must be a non-empty list")
        others = split.get("dynamics_or_physical_budget")
        if not isinstance(others, list) or not others:
            flag("budget_class_missing",
                 "dynamics_or_physical_budget must be a non-empty list")

    # -- untracked inputs -------------------------------------------------
    untracked = document.get("untracked_inputs")
    if not isinstance(untracked, dict):
        flag("untracked_inputs_missing", "untracked_inputs must be an object")
    else:
        if untracked.get("tracked_evidence_only") is not False:
            flag("untracked_policy_mismatch",
                 "untracked_inputs.tracked_evidence_only must be false")
        inputs = untracked.get("inputs")
        if not isinstance(inputs, dict):
            flag("untracked_inputs_shape", "untracked_inputs.inputs must be an object")
        else:
            for key, item in sorted(inputs.items()):
                if not isinstance(item, dict):
                    flag("untracked_input_shape", f"malformed input {key!r}")
                    continue
                if item.get("tracked_at_head") is not False:
                    flag("untracked_input_claims_tracked",
                         f"{key} must not claim to be tracked at HEAD")
                if item.get("expected_sha256") is None:
                    flag("untracked_input_pin_absent",
                         f"{key} declares no expected sha256")
                if (item.get("available_on_disk") is True
                        and item.get("hash_matches") is not True
                        and status == "ok"):
                    flag("untracked_input_hash_mismatch",
                         f"{key} is available but does not match its pin")

    # -- missing inputs ---------------------------------------------------
    declared_missing = document.get("missing_inputs")
    missing_kinds = {"missing_tracked_evidence", "unreadable_tracked_evidence",
                     "missing_raw_input"}
    blocker_list = blockers if isinstance(blockers, list) else []
    has_missing_blocker = any(
        isinstance(block, dict) and block.get("kind") in missing_kinds
        for block in blocker_list)
    if status == "ok":
        if declared_missing not in ([], None) and declared_missing != []:
            flag("missing_inputs_present",
                 "status 'ok' requires an empty missing_inputs list")
    elif has_missing_blocker:
        if not isinstance(declared_missing, list) or not declared_missing:
            flag("missing_inputs_absent",
                 "status 'blocked' with missing inputs requires a non-empty "
                 "missing_inputs list")
    else:
        # A document blocked solely on provenance (non-ancestor anchor, pinned
        # path overlap, or an unavailable probe) has no missing inputs to list.
        if declared_missing not in ([], None) and declared_missing != []:
            flag("missing_inputs_present",
                 "no missing-input blockers but missing_inputs is non-empty")

    # -- nonclaims --------------------------------------------------------
    nonclaims = document.get("nonclaims")
    if not isinstance(nonclaims, list) or len(nonclaims) < 5:
        flag("nonclaims_insufficient", "nonclaims must list at least 5 items")
    else:
        blob = " ".join(str(item) for item in nonclaims).lower()
        for needle in ("g6", "r1", "physical", "closure", "budget"):
            if needle not in blob:
                flag("nonclaim_missing", f"nonclaims must address {needle!r}")

    # -- live recomputation of the declaration ---------------------------
    if recompute and repo_root is not None:
        live, live_blocks = build_document(repo_root)
        if live.get("status") != status:
            flag("live_status_mismatch",
                 f"declared status {status!r} but live recomputation reports "
                 f"{live.get('status')!r}")
        if status == "ok":
            live_streams = live["recomputed"]["streams"]
            for live_stream in live_streams:
                stream_id = live_stream["id"]
                declared = streams_by_id.get(stream_id)
                if declared is None:
                    flag("live_stream_absent",
                         f"live recomputation produced {stream_id} but the "
                         f"document does not declare it")
                    continue
                live_structural = live_stream["recomputed"]
                declared_structural = declared.get("recomputed", {})
                for field in ("row_count", "gain",
                              "measured_product_rows_matched",
                              "measured_product_rows_mismatch",
                              "measured_product_mismatch_indices",
                              "measured_division_rows_matched",
                              "measured_division_differs_from_product",
                              "measured_division_mismatch_indices",
                              "form_disagreement_rows",
                              "form_disagreement_indices_first",
                              "form_disagreement_indices_count",
                              "measured_row_width"):
                    if declared_structural.get(field) != live_structural.get(field):
                        flag("live_recomputation_mismatch",
                             f"{stream_id}.{field} does not match live "
                             f"recomputation")
                if declared_structural.get("shifted_row_check") != (
                        live_structural.get("shifted_row_check")):
                    flag("live_recomputation_mismatch",
                         f"{stream_id}.shifted_row_check does not match live "
                         f"recomputation")
                if declared.get("column_sha256") != live_stream.get("column_sha256"):
                    flag("live_recomputation_mismatch",
                         f"{stream_id}.column_sha256 does not match live "
                         f"recomputation")
            live_reference = live["recomputed"]["reference"]
            declared_reference = reference if isinstance(reference, dict) else {}
            if set(declared_reference) != set(live_reference):
                flag("live_recomputation_mismatch",
                     "reference keys do not match live recomputation")
            for key, live_entry in live_reference.items():
                declared_entry = declared_reference.get(key)
                if not isinstance(declared_entry, dict):
                    continue
                for field in ("product_rows_matched", "division_rows_matched",
                              "form_disagreement_rows",
                              "form_disagreement_indices_first",
                              "form_disagreement_indices_count",
                              "time_column_sha256"):
                    if declared_entry.get(field) != live_entry.get(field):
                        flag("live_recomputation_mismatch",
                             f"reference[{key}].{field} does not match live "
                             f"recomputation")
                declared_crosscheck = declared_entry.get("array_crosscheck")
                live_crosscheck = live_entry.get("array_crosscheck")
                if not isinstance(declared_crosscheck, dict) or not isinstance(
                        live_crosscheck, dict):
                    continue
                for field in ("slot_reference_column_equals_clock_times_gain",
                              "slot_time_column_matches_measured_slot",
                              "columns_with_a_full_match",
                              "columns_without_a_full_match", "contract_gain"):
                    if declared_crosscheck.get(field) != live_crosscheck.get(field):
                        flag("live_recomputation_mismatch",
                             f"reference[{key}].array_crosscheck.{field} does "
                             f"not match live recomputation")
        for role, item in dependency_by_role.items():
            live_item = next((candidate for candidate in
                              live["evidence_dependencies"]["dependencies"]
                              if candidate["role"] == role), None)
            if live_item is None:
                continue
            if item.get("tracked_at_head") is not live_item.get("tracked_at_head"):
                flag("live_dependency_tracked_drift",
                     f"dependency {role!r} tracked flag drifted")
            if item.get("sha256") != live_item.get("sha256"):
                flag("live_dependency_hash_drift",
                     f"dependency {role!r} sha256 drifted")
            if item.get("size") != live_item.get("size"):
                flag("live_dependency_size_drift",
                     f"dependency {role!r} size drifted")
        live_provenance = live["evidence_dependencies"].get("provenance", {})
        declared_provenance = (dependencies.get("provenance", {})
                               if isinstance(dependencies, dict) else {})
        for field in ("base_ancestor", "ancestor_check",
                      "anchor_is_ancestor_of_observed_head",
                      "evidence_paths_unchanged_since_anchor",
                      "changed_pinned_paths", "pinned_evidence_paths"):
            if declared_provenance.get(field) != live_provenance.get(field):
                flag("live_recomputation_mismatch",
                     f"evidence_dependencies.provenance.{field} does not match "
                     f"live recomputation")
        live_untracked = live["untracked_inputs"]["inputs"]
        declared_untracked = untracked.get("inputs", {}) if isinstance(
            untracked, dict) else {}
        for key in sorted(set(live_untracked) | set(declared_untracked)):
            live_item = live_untracked.get(key, {})
            declared_item = declared_untracked.get(key, {})
            if not isinstance(declared_item, dict):
                flag("live_untracked_drift", f"untracked input {key!r} missing")
                continue
            for field in ("available_on_disk", "sha256", "size", "hash_matches",
                          "size_matches"):
                if declared_item.get(field) != live_item.get(field):
                    flag("live_untracked_drift",
                         f"untracked input {key!r}.{field} drifted")
        if live_blocks and status == "ok":
            flag("live_blockers_absent",
                 f"live recomputation reports blockers but the document is "
                 f"declared {status!r}")

    _ = ValidationError  # documented type, kept for callers
    return _result(codes, errors)


def _result(codes, errors):
    ordered = sorted(codes)
    return {"ok": not ordered, "codes": ordered, "errors": sorted(errors)}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_BLOCKED = 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--out", type=Path, default=None,
                        help=f"output path (default: <repo-root>/{DEFAULT_OUT})")
    parser.add_argument("--validate", action="store_true",
                        help="validate the existing output instead of writing it")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="print the document to stdout and write nothing")
    parser.add_argument("--require-raw", action="store_true",
                        help="explicit CI form of the default fail-closed "
                             "policy: exit 3 when any declared input is "
                             "missing or mismatched (never writes output)")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    out_path = args.out if args.out is not None else repo_root / DEFAULT_OUT

    if args.validate:
        if not out_path.exists():
            print(json.dumps({"ok": False, "codes": ["output_absent"],
                              "errors": [f"no such output: {out_path}"]}, indent=2))
            return EXIT_INVALID
        document = json.loads(out_path.read_text(encoding="utf-8"))
        result = validate(document, repo_root=repo_root)
        print(json.dumps(result, indent=2))
        return EXIT_OK if result["ok"] else EXIT_INVALID

    document, blocks = build_document(repo_root)
    if args.print_only:
        sys.stdout.write(dumps(document))
        return EXIT_OK if not blocks else EXIT_BLOCKED

    if blocks:
        summary = {
            "output": None,
            "status": document["status"],
            "blockers": document["blockers"],
            "missing_inputs": document["missing_inputs"],
            "wrote": False,
        }
        print(json.dumps(summary, indent=2))
        return EXIT_BLOCKED

    result = validate(document, repo_root=repo_root)
    digest = write_document(document, out_path)
    summary = {
        "output": str(out_path),
        "sha256": digest,
        "size": out_path.stat().st_size,
        "status": document["status"],
        "valid": result["ok"],
        "codes": result["codes"],
    }
    print(json.dumps(summary, indent=2))
    return EXIT_OK if result["ok"] else EXIT_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
