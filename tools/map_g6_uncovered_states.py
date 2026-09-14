"""Deterministic offline 36-state G6 coverage map (tracked evidence only).

This tool inventories the flat continuous-state vector of the frozen R1/C3G
generated model (``nXc = 36``) and records, for every flat index 0..35:

* whether the index is inside the 13 mapped rigid-body states (6..18) or the
  23 unmapped states (0..5, 19..35);
* the block symbol that the tracked sources attribute to it, together with an
  explicit resolution status when the tracked sources disagree or when the
  binding needs the frozen model archive;
* the tracked documentation line/text bindings that carry the claim, with the
  SHA256 of the exact tracked bytes the text was read from;
* the entry class inside the mrdivide residual -> matrix -> result solve
  (supported only for the three flat indices 10, 11, 12, which the tracked
  evidence identifies as the solve numerator/output); nothing physical is
  inferred for the remaining indices.

Everything here is offline and read-only.  The tool never compiles, runs, or
simulates anything, never opens the frozen ZIP, never touches a model runtime,
and never modifies any existing trace, contract, or evidence byte.  It derives
its output only from repository-tracked bytes plus two named on-disk
provenance files (the generated ERT C and the pinned model archive identity),
whose absence is recorded as an unresolved field instead of being guessed.

Determinism: ``build_map()`` is a pure function of the on-disk bytes of the
declared pins; ``dumps()`` fixes key order, indentation, ASCII escaping and the
trailing newline, so regenerating from the same pins is byte-identical.

This map is a coverage inventory.  It is not a numerical acceptance, not a
physical-accuracy claim, and not G6/R1/Full passage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Frozen identity
# --------------------------------------------------------------------------

SCHEMA = "wksim.59-g6-uncovered-state-map.v1"
KIND = "g6_uncovered_state_map"
GENERATOR = "tools/map_g6_uncovered_states.py"
DEFAULT_OUT = "validation/g6-uncovered-state-map-20260914.json"
DATE = "2026-09-14"
ISSUE = "#59"

# The frozen anchor commit this map is pinned to.  The evidence tree and the
# tracked-membership flags are read at this anchor, so the recorded provenance
# is a pure function of the anchor tree plus the on-disk bytes and stays stable
# as the repository advances and once the slice is committed.  The live HEAD is
# observed only to prove the anchor is still an ancestor of it and that no
# pinned-evidence path changed in anchor..HEAD; the observed HEAD itself is
# never embedded in the document.
ANCHOR = "ee6eb88819cefe255f22e788c39a77c0bbab490e"
ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"

# r1_status and the open issue/G6/Full state are constants of the current
# frontier; this map neither advances nor closes any of them.  #84, G6 and Full
# remain open and r1_status remains numerical_failed.
R1_STATUS = "numerical_failed"
OPEN_ITEMS = (
    ("issue_84", "open"),
    ("g6", "open"),
    ("full", "open"),
)

TOTAL_STATES = 36
COVERED_LO = 6
COVERED_HI = 18
COVERED_COUNT = COVERED_HI - COVERED_LO + 1          # 13
UNCOVERED_COUNT = TOTAL_STATES - COVERED_COUNT       # 23

# Enum of supported entry classes inside the mrdivide (inertia solve) path.
ENTRY_RESIDUAL = "mrdivide_residual_input"
ENTRY_OUTPUT = "mrdivide_output"
ENTRY_OUTSIDE = "out_of_mrdivide_path"
ENTRY_CLASSES = (ENTRY_RESIDUAL, ENTRY_OUTPUT, ENTRY_OUTSIDE)

# Enum of symbol-resolution outcomes.
SYM_RESOLVED = "resolved"
SYM_CONFLICT_ARCHIVE = "conflicted_requires_archive_input"
SYM_UNRESOLVED_ARCHIVE = "unresolved_requires_archive_input"
SYM_STATUSES = (SYM_RESOLVED, SYM_CONFLICT_ARCHIVE, SYM_UNRESOLVED_ARCHIVE)

# Enum of source-line mapping outcomes.
LINE_UNTACKED_MAPPED = "mapped_via_untracked_generated_cpp"
LINE_ARCHIVE_REQUIRED = "unresolved_requires_archive_input"
LINE_STATUSES = (LINE_UNTACKED_MAPPED, LINE_ARCHIVE_REQUIRED)

# --------------------------------------------------------------------------
# Pins: repository-tracked evidence bytes
# --------------------------------------------------------------------------
# key -> relative path.  Whether a path is present in the anchor tree is read
# from the repository at build time via the index-independent `git ls-tree`
# (never assumed).  The map records anchor-tree membership only, so it is a pure
# function of that frozen tree plus the on-disk bytes and does not change with
# whatever a temporary index happens to hold or with later commits: the ten
# pre-existing evidence files and four existing tools are anchor-tracked, while
# the generator and the test file are recorded as absent from the anchor tree
# (they were added after the anchor).

EVIDENCE_PINS = {
    "agents": "AGENTS.md",
    "first_step_static_doc": "docs/coordination/g6-first-step-static-20260913.md",
    "pqr_derivative_path_doc": "docs/coordination/g6-pqr-derivative-path-20260913.md",
    "first_step_trace_doc": "docs/coordination/g6-first-step-trace-20260913.md",
    "first_divergence_doc": "docs/coordination/g6-first-divergence-20260913.md",
    "target_first_step_trace": (
        "validation/coordination/g6-target-first-step-20260913/first-step-trace.jsonl"),
    "comparison_v2": (
        "validation/coordination/g6-target-first-step-20260913/comparison-v2.json"),
    "source_index": (
        "validation/coordination/g6-first-step-static-20260913/source-index.json"),
    "reference_run03": (
        "validation/coordination/g6-reference-probe-20260913/run-03/reference-first-step.json"),
    "reference_block_map": (
        "validation/coordination/g6-reference-probe-20260913/block-map.json"),
}

DERIVED_PINS = {
    "build_first_step_trace": "tools/build_first_step_trace.py",
    "probe_reference_first_step": "tools/probe_reference_first_step.m",
    "compare_first_step_trace": "tools/compare_first_step_trace.py",
    "compare_g6_c3g_stage2": "tools/compare_g6_c3g_stage2.py",
    "map_generator": GENERATOR,
    "map_test": "validation/test_map_g6_uncovered_states.py",
}

# On-disk provenance that is deliberately NOT repository-tracked.  It is bound
# by SHA256 and size when present, and recorded as unreadable when absent; the
# map never depends on its bytes to decide a coverage or class claim.
UNTRACKED_PROVENANCE = {
    "generated_cpp": (
        "work/quad-parameters-source-review-20260909/Exp1_MinModelTemp.cpp",
        "a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019",
    ),
}

# The frozen model archive required to close the source-line/symbol mapping.
ARCHIVE = {
    "path": ("/mnt/e/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/"
             "e0_MinModelTemp/MulticopterModel.zip"),
    "sha256": "d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed",
    "cpp_member": "e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp",
    "header_member": "e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.h",
    "original_cpp_sha256": "a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019",
    "required_for": [
        "authoritative flat-index -> state-name layout from the generated header",
        "authoritative per-flat-index source-line mapping",
        "resolution of the TransferFcn and MotorNonlinearDynamic symbol-order conflict",
    ],
}

# --------------------------------------------------------------------------
# Tracked line/text bindings
# --------------------------------------------------------------------------
# (source_pin, line_start, line_end)  1-based, inclusive, over the tracked file.
LINE_BINDINGS = {
    "residual_index_1": ("pqr_derivative_path_doc", 18, 18),
    "first_step_timeline": ("first_step_static_doc", 16, 21),
    "mrdivide_call": ("pqr_derivative_path_doc", 28, 28),
    "uncovered_note": ("pqr_derivative_path_doc", 36, 36),
    "output_encoding": ("first_step_static_doc", 41, 51),
    "solver_observation": ("first_step_static_doc", 69, 74),
    "static_boundary": ("first_step_static_doc", 113, 115),
    "build_trace_scope": ("first_step_trace_doc", 1, 12),
    "divergence_scope": ("first_divergence_doc", 1, 16),
}

# Symbol evidence keys used by the index map.
SYM_Q = "q0..q3"
SYM_PQR = "p,q,r"
SYM_POS = "xe,ye,ze"
SYM_VEL = "ub,vb,wb"
SYM_RESIDUAL = "residual_vector:rtb_IntegratorSecondOrderLimi_d[0..2]"
SYM_OUTPUT = "mrdivide_output:Exp1_MinModelTemp_B.Product2[0..2]"
SYM_CS = "IntegratorSecondOrderLimited_CS"
SYM_INTN = "IntegratorSecondOrderLimited__n"
SYM_TRANSFER = "TransferFcn4/1/2_CSTATE"
SYM_MOTOR = "MotorNonlinearDynamic8..1 .x"

# Symbol evidence per range: (lo, hi, symbol).  The flat-index -> block-symbol
# layout is transcribed from the tracked builder STATE_LAYOUT table.
SYM_TABLE = (
    (0, 5, SYM_CS),
    (6, 9, SYM_Q),
    (10, 12, SYM_PQR),
    (13, 15, SYM_POS),
    (16, 18, SYM_VEL),
    (19, 24, SYM_INTN),
    (25, 27, SYM_TRANSFER),
    (28, 35, SYM_MOTOR),
)

# The four ranges whose endpoints are bound by the tracked 13-state comparison
# and the tracked reference probe integrator paths.
COMPARISON_MAPPED_SYMBOLS = (SYM_Q, SYM_PQR, SYM_POS, SYM_VEL)
# The contiguous 19..35 span whose block ownership the tracked sources disagree
# about: the builder STATE_LAYOUT places IntegratorSecondOrderLimited__n at
# 19..24 and TransferFcn4/1/2_CSTATE at 25..27, while the requirement text
# (g6-pqr-derivative-path-20260913.md:36) assigns 19..27 to TransferFcn.  The
# disagreement covers indices 19..24 and is never resolved here.
ORDER_CONFLICT_SYMBOLS = (SYM_INTN, SYM_TRANSFER, SYM_MOTOR)

# Per flat index: which line-binding keys and doc refs carry its claim.
INDEX_REFS = {
    10: {
        "doc_refs": ["residual_index_1", "mrdivide_call"],
        "line_bindings": ["residual_index_1", "mrdivide_call"],
    },
    11: {
        "doc_refs": ["residual_index_1", "mrdivide_call", "uncovered_note"],
        "line_bindings": ["residual_index_1", "mrdivide_call", "uncovered_note"],
    },
    12: {
        "doc_refs": ["residual_index_1", "mrdivide_call"],
        "line_bindings": ["residual_index_1", "mrdivide_call"],
    },
}

# The Q-derivative divergence pair, recorded verbatim from the tracked trace and
# the tracked comparison (hex only; no physical interpretation).
TRACE_DIVERGENCE = {
    "index": 11,
    "stage": 2,
    "target_trace_hex": "bc56d4db33a987b9",
    "comparison_v2_reference_hex": "bc56d4db33a987b8",
    "comparison_v2_target_hex": "bc56d4db33a987b9",
    "ulp": 1,
    "note": ("stage-2 p,q,r derivatives index 1 (q); the tracked comparison "
             "records exactly 1 ULP. This is divergence evidence, not an "
             "acceptance result and not a root cause."),
}

# The stage-2 p,q,r derivative slice (flat indices 10..12), recorded verbatim
# from the pinned target trace deriv_hex[10..12] (hex only; no physical
# interpretation).  Index 11 (q) is the documented 1 ULP divergence above.
TRACE_STAGE2_PQR_HEX = (
    "3c47b1ebce4a1e30",   # flat index 10 (p)
    "bc56d4db33a987b9",   # flat index 11 (q)
    "36f8ccceed35d6fd",   # flat index 12 (r)
)

# --------------------------------------------------------------------------
# Repository access
# --------------------------------------------------------------------------


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _git_text(repo_root, *args):
    """Run one read-only git command; return (exit_code, stdout_text).

    This is the only child-process call in the tool.  ``exit_code`` is None
    when git itself could not be launched."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(repo_root), capture_output=True, check=False)
    except OSError:
        return None, ""
    return result.returncode, result.stdout.decode("utf-8", "replace")


def anchor_tree_paths(repo_root):
    """Repository paths present in the frozen anchor tree, read via the
    index-independent `git ls-tree`.  Returns an empty set when git or the
    anchor commit is unavailable.  Membership is evaluated at the anchor (not
    at the live HEAD) so the recorded flags stay stable across later commits."""
    names = set(EVIDENCE_PINS.values()) | set(DERIVED_PINS.values())
    rc, out = _git_text(repo_root, "ls-tree", "-r", "--name-only", "-z", ANCHOR)
    if rc != 0:
        return set()
    tracked = set(out.split("\0"))
    return {name for name in names if name in tracked}


def _ancestor_state(rc):
    """Map a `merge-base --is-ancestor` exit code to True/False/None."""
    if rc is None or rc not in (0, 1):
        return None
    return rc == 0


def anchor_status(repo_root):
    """Observed relationship between the frozen anchor and the live HEAD.

    Returns a dict with ``anchor_is_ancestor`` / ``base_is_ancestor``
    (True/False, or None when it cannot be determined) and
    ``drifted_evidence`` (sorted pinned-evidence paths changed in anchor..HEAD,
    or None when the diff cannot be computed).  The live HEAD is observed here
    only; it is never embedded in the document."""
    anchor_rc, _ = _git_text(
        repo_root, "merge-base", "--is-ancestor", ANCHOR, "HEAD")
    base_rc, _ = _git_text(
        repo_root, "merge-base", "--is-ancestor", ANCESTOR, "HEAD")
    diff_rc, diff_out = _git_text(
        repo_root, "diff", "--name-only", ANCHOR, "HEAD", "--",
        *sorted(EVIDENCE_PINS.values()))
    drifted = None
    if diff_rc == 0:
        drifted = sorted(line for line in diff_out.splitlines() if line.strip())
    return {
        "anchor_is_ancestor": _ancestor_state(anchor_rc),
        "base_is_ancestor": _ancestor_state(base_rc),
        "drifted_evidence": drifted,
    }


def read_pin(repo_root, rel_path):
    """Read a declared pin exactly once and return (bytes, sha256, size)."""
    raw = (Path(repo_root) / rel_path).read_bytes()
    return raw, _sha256(raw), len(raw)


def _line_texts(repo_root, rel_path, start, end):
    """Decoded text of 1-based inclusive line span [start, end]."""
    lines = (Path(repo_root) / rel_path).read_text(encoding="utf-8").splitlines()
    if start < 1 or end < start or end > len(lines):
        raise ValueError(
            f"line span {start}-{end} outside {rel_path} ({len(lines)} lines)")
    return [lines[i] for i in range(start - 1, end)]


def build_bindings(repo_root):
    """Resolve the declared line bindings against the tracked bytes."""
    bindings = {}
    for key in sorted(LINE_BINDINGS):
        source, start, end = LINE_BINDINGS[key]
        rel_path = EVIDENCE_PINS[source]
        raw, digest, size = read_pin(repo_root, rel_path)
        bindings[key] = {
            "key": key,
            "source": source,
            "path": rel_path,
            "tracked_at_anchor": True,
            "sha256": digest,
            "size": size,
            "line_start": start,
            "line_end": end,
            "text": _line_texts(repo_root, rel_path, start, end),
        }
    return bindings


# --------------------------------------------------------------------------
# Map construction
# --------------------------------------------------------------------------


def _doc_refs_from_bindings(bindings):
    """The doc_refs summary array derived from resolved line bindings.

    Shared by build_map() and validate() so the committed array is checked
    against a recomputation from the same tracked bytes."""
    return [{
        "key": key,
        "source": bindings[key]["source"],
        "path": bindings[key]["path"],
        "sha256": bindings[key]["sha256"],
        "line_start": bindings[key]["line_start"],
        "line_end": bindings[key]["line_end"],
    } for key in sorted(bindings)]


def _section_for(index):
    for lo, hi, symbol in SYM_TABLE:
        if lo <= index <= hi:
            return dict(lo=lo, hi=hi, symbol=symbol)
    raise ValueError(f"index {index} outside 0..{TOTAL_STATES - 1}")


def _coverage(index):
    return COVERED_LO <= index <= COVERED_HI


def _entry(repo_root, bindings, index, untracked_available):
    section = _section_for(index)
    covered = _coverage(index)
    lo, hi, symbol = section["lo"], section["hi"], section["symbol"]

    # -- symbol resolution ------------------------------------------------
    if symbol in COMPARISON_MAPPED_SYMBOLS:
        symbol_resolution = SYM_RESOLVED
        symbol_evidence = "tracked_comparison_v2_target_indices"
        symbol_note = (
            "range endpoints bound by tracked evidence: "
            "validation/coordination/g6-target-first-step-20260913/comparison-v2.json "
            f"target_indices places this block at flat indices {lo}..{hi}, and "
            "the tracked reference probe state_integrator_paths registers "
            "listeners on the same named rigid-body integrators")
    elif symbol in ORDER_CONFLICT_SYMBOLS:
        symbol_resolution = SYM_CONFLICT_ARCHIVE
        symbol_evidence = "tracked_builder_state_layout_plus_requirement_text"
        symbol_note = (
            "two tracked sources disagree on the block owning the low end of "
            "this range: tools/build_first_step_trace.py STATE_LAYOUT places "
            "IntegratorSecondOrderLimited__n at 19..24 and "
            "TransferFcn4/1/2_CSTATE at 25..27, while the requirement text "
            "docs/coordination/g6-pqr-derivative-path-20260913.md:36 assigns "
            "19..27 to TransferFcn; the ownership of indices 19..24 and the "
            "authoritative layout need the frozen archive header input")
    else:
        symbol_resolution = SYM_RESOLVED
        symbol_evidence = "tracked_builder_state_layout"
        symbol_note = (
            "symbol text transcribed from the tracked builder state_layout "
            "table; no tracked comparison maps this range, so the endpoints are "
            "builder-attested only, and the authoritative layout still needs "
            "the frozen archive header input")

    # -- entry class ------------------------------------------------------
    if index in (10, 11, 12):
        entry_class = ENTRY_RESIDUAL
        entry_kind = "mrdivide_numerator_vector"
        entry_reason = (
            "tracked evidence binds this flat index to the mrdivide numerator "
            "rtb_IntegratorSecondOrderLimi_d[0..2] (residual_input)"
            + ("; flat index 11 is the q component named explicitly in "
               "docs/coordination/g6-pqr-derivative-path-20260913.md:16,18"
               if index == 11 else ""))
    elif covered:
        entry_class = ENTRY_OUTSIDE
        entry_kind = "mapped_reference_compared_state"
        entry_reason = (
            "covered by the tracked 13-state comparison-v2 mapping and the "
            "tracked reference probe events; the tracked evidence does not "
            "bind this index to any mrdivide operand or result")
    else:
        entry_class = ENTRY_OUTSIDE
        entry_kind = "unmapped_state"
        entry_reason = (
            "not mapped on the reference side by any tracked source; the "
            "tracked evidence does not bind this index to any mrdivide operand "
            "or result")

    # The mrdivide output indices are the same three flat indices; the solve
    # result feeds the p,q,r derivative slice, so 10..12 are classified as the
    # residual input, with the output encoding recorded separately below.
    refs = INDEX_REFS.get(index, {})
    doc_refs = list(refs.get("doc_refs", []))
    line_keys = list(refs.get("line_bindings", []))
    if covered and not doc_refs:
        doc_refs = ["first_step_timeline", "output_encoding"]
        line_keys = ["first_step_timeline"]

    entry = {
        "index": index,
        "covered": covered,
        "block_symbol": symbol,
        "block_symbol_range": [lo, hi],
        "symbol_resolution": symbol_resolution,
        "symbol_evidence": symbol_evidence,
        "symbol_source": symbol,
        "symbol_note": symbol_note,
        "entry_class": entry_class,
        "entry_kind": entry_kind,
        "entry_reason": entry_reason,
        "source_line_mapping": (
            LINE_UNTACKED_MAPPED if index in (10, 11, 12)
            else LINE_ARCHIVE_REQUIRED),
        "tracked_doc_refs": doc_refs,
        "tracked_line_bindings": [
            dict(bindings[key]) for key in line_keys
        ],
        "trace_source": (
            "validation/coordination/g6-target-first-step-20260913/"
            "first-step-trace.jsonl" if covered else None),
        "reference_source": (
            "validation/coordination/g6-reference-probe-20260913/run-03/"
            "reference-first-step.json" if covered else None),
    }
    if index in (10, 11, 12):
        entry["untracked_provenance"] = {
            "path": UNTRACKED_PROVENANCE["generated_cpp"][0],
            "sha256": UNTRACKED_PROVENANCE["generated_cpp"][1],
            "available_on_disk": untracked_available,
            "tracked_at_anchor": False,
            "line_spans": {
                "residual_components": [5506, 5528],
                "selector2_matrix": [5529, 5540],
                "mrdivide_call": [5546, 5547],
            },
            "note": ("line anchors read from the untracked on-disk generated "
                     "ERT C; the frozen archive member is required to make the "
                     "source-line mapping independently reproducible"),
        }
    if index == 11:
        entry["mrdivide_output_evidence"] = dict(TRACE_DIVERGENCE)
        entry["output_encoding"] = {
            "kind": ENTRY_OUTPUT,
            "symbol": SYM_OUTPUT,
            "result_equals_derivative_slice": [10, 13],
            "hex_stage2": list(TRACE_STAGE2_PQR_HEX),
            "note": ("the solve result vector is recorded as the p,q,r "
                     "derivative slice of the same stage; the three stage-2 "
                     "derivative bytes are transcribed from the pinned target "
                     "trace deriv[10..12], with index 11 (q) the recorded 1 "
                     "ULP divergence; recorded as encoding, with no physical "
                     "interpretation"),
        }
    return entry


def _pin_block(repo_root, table, tracked_paths):
    block = {}
    for key in sorted(table):
        rel_path = table[key]
        tracked = rel_path in tracked_paths
        try:
            raw, digest, size = read_pin(repo_root, rel_path)
            block[key] = {
                "path": rel_path,
                "tracked_at_anchor": tracked,
                "sha256": digest,
                "size": size,
            }
        except OSError:
            block[key] = {
                "path": rel_path,
                "tracked_at_anchor": tracked,
                "sha256": None,
                "size": None,
                "unreadable": True,
            }
    return block


def _untracked_block(repo_root):
    block = {}
    for key in sorted(UNTRACKED_PROVENANCE):
        rel_path, expected = UNTRACKED_PROVENANCE[key]
        item = {
            "path": rel_path,
            "tracked_at_anchor": False,
            "expected_sha256": expected,
            "available_on_disk": False,
            "sha256": None,
            "matches_expected": None,
        }
        try:
            raw, digest, size = read_pin(repo_root, rel_path)
        except OSError:
            block[key] = item
            continue
        item["available_on_disk"] = True
        item["sha256"] = digest
        item["size"] = size
        item["matches_expected"] = (digest == expected)
        block[key] = item
    return block


def unresolved_items(repo_root, untracked_available):
    """The unresolved fields this map refuses to guess."""
    items = [
        {
            "id": "archive_source_line_mapping",
            "scope": "all 36 flat indices",
            "status": "unresolved",
            "requires": "model_archive",
            "requires_path": ARCHIVE["path"],
            "requires_sha256": ARCHIVE["sha256"],
            "requires_member": ARCHIVE["cpp_member"],
            "reason": ("individual flat-index source-line mapping is only "
                       "readable from the frozen archive member; the "
                       "repository does not track generated vendor source"),
        },
        {
            "id": "authoritative_state_layout",
            "scope": "all 36 flat indices",
            "status": "unresolved",
            "requires": "model_archive",
            "requires_path": ARCHIVE["path"],
            "requires_sha256": ARCHIVE["sha256"],
            "requires_member": ARCHIVE["header_member"],
            "reason": ("the flat-index -> state-name layout used here comes "
                       "from the untracked builder state_layout table; the "
                       "authoritative source is the generated header inside "
                       "the archive"),
        },
        {
            "id": "transferfcn_motor_symbol_order",
            "scope": "indices 19..35",
            "status": "unresolved",
            "requires": "model_archive",
            "requires_path": ARCHIVE["path"],
            "requires_sha256": ARCHIVE["sha256"],
            "requires_member": ARCHIVE["header_member"],
            "reason": ("the tracked builder STATE_LAYOUT places "
                       "IntegratorSecondOrderLimited__n at 19..24 and "
                       "TransferFcn4/1/2_CSTATE at 25..27, while the tracked "
                       "requirement text g6-pqr-derivative-path-20260913.md:36 "
                       "assigns 19..27 to TransferFcn; the ownership of "
                       "indices 19..24 and the authoritative per-index layout "
                       "are recorded as conflicted and never guessed"),
        },
        {
            "id": "unmapped_reference_states",
            "scope": "indices 0..5, 19..35",
            "status": "unresolved",
            "requires": "reference_probe_extension",
            "requires_path": (
                "validation/coordination/g6-reference-probe-20260913/"
                "run-03/reference-first-step.json"),
            "requires_sha256": (
                "99fc1ec84a110bea1e5998a97b4f9c66231966474268ba74bfc343b584e03f85"),
            "requires_member": None,
            "reason": ("the tracked reference probe registered listeners on "
                       "only the four rigid-body 6DOF integrators, so the 23 "
                       "unmapped states have no reference-side observation"),
        },
    ]
    for index in (10, 12):
        items.append({
            "id": f"residual_component_binding_{index}",
            "scope": f"index {index}",
            "status": "unresolved",
            "requires": "model_archive",
            "requires_path": ARCHIVE["path"],
            "requires_sha256": ARCHIVE["sha256"],
            "requires_member": ARCHIVE["cpp_member"],
            "reason": ("the flat index is attested as a member of the "
                       "3-vector mrdivide numerator, but the per-component "
                       "source-line expression for this component is not "
                       "bound by tracked line evidence"),
        })
    if not untracked_available:
        items.append({
            "id": "untracked_generated_cpp_absent",
            "scope": "indices 10..12 line anchors",
            "status": "unresolved",
            "requires": "generated_cpp_on_disk",
            "requires_path": UNTRACKED_PROVENANCE["generated_cpp"][0],
            "requires_sha256": UNTRACKED_PROVENANCE["generated_cpp"][1],
            "requires_member": None,
            "reason": ("the generated ERT C used for the provisional line "
                       "anchors is not present on disk"),
        })
    items.sort(key=lambda item: item["id"])
    return items


NONCLAIMS = [
    "no numerical acceptance: no trace was replayed, compared, or recomputed",
    "no physical-accuracy claim: state names, units and vehicle semantics are "
    "transcribed from tracked text only and are not verified here",
    "no G6 passage and no R1 passage; r1_status remains numerical_failed",
    "no issue closure: #84, G6 and Full remain open",
    "no budget, approval, acceptance, or contract freeze is proposed, "
    "requested, or recorded",
    "no source-line mapping claim for flat indices outside 10..12",
    "no claim that the 13 covered indices are numerically conformant; they are "
    "inventory coverage, and index 11 is a recorded 1 ULP divergence",
    "no model-runtime, simulator, avionics, visual, or issue-83 execution",
    "no edit to any existing trace, contract, comparator, or evidence byte",
]


def build_map(repo_root):
    """Pure function of the on-disk pin bytes; returns the map document."""
    repo_root = Path(repo_root)
    tracked_paths = anchor_tree_paths(repo_root)
    bindings = build_bindings(repo_root)
    untracked = _untracked_block(repo_root)
    untracked_available = bool(
        untracked["generated_cpp"]["available_on_disk"])

    entries = [_entry(repo_root, bindings, index, untracked_available)
               for index in range(TOTAL_STATES)]

    covered = [e["index"] for e in entries if e["covered"]]
    uncovered = [e["index"] for e in entries if not e["covered"]]
    if covered != list(range(COVERED_LO, COVERED_HI + 1)):
        raise ValueError("covered index block is not exactly 6..18")
    if uncovered != list(range(0, COVERED_LO)) + list(range(COVERED_HI + 1, TOTAL_STATES)):
        raise ValueError("uncovered indices are not exactly 0..5,19..35")

    doc_refs = _doc_refs_from_bindings(bindings)

    document = {
        "schema": SCHEMA,
        "kind": KIND,
        "version": 1,
        "date": DATE,
        "issue": ISSUE,
        "title": "G6 36-state offline coverage map (tracked evidence only)",
        "work_class": "new-development",
        "layer": "evidence_inventory",
        "authority": "none",
        "effective": False,
        "generator": GENERATOR,
        "generator_command": (
            "python -B tools/map_g6_uncovered_states.py "
            "--repo-root . --out validation/g6-uncovered-state-map-20260914.json"),
        "anchor": ANCHOR,
        "base_ancestor": ANCESTOR,
        "anchor_policy": {
            "anchor": ANCHOR,
            "anchor_is_ancestor_of_head_required": True,
            "pinned_evidence_unchanged_since_anchor": True,
            "observed_head_embedded": False,
            "note": ("the map is pinned to the frozen anchor tree; the live "
                     "HEAD is observed only to prove the anchor is still an "
                     "ancestor of it and that no pinned-evidence path changed "
                     "in anchor..HEAD, and the observed HEAD is never recorded"),
        },
        "r1_status": R1_STATUS,
        "g6_acceptance": False,
        "physical_accuracy": False,
        "issues_closed": False,
        "budget_approved": False,
        "pending_approvals": [],
        "open_items": [{"id": item, "state": state} for item, state in OPEN_ITEMS],
        "identity": {
            "model": "Exp1_MinModelTemp",
            "case": "C3G",
            "solver": "ode4",
            "fixed_step_s": 0.001,
            "stop_time_s": 0.001,
            "nXc": TOTAL_STATES,
            "flat_index_domain": [0, TOTAL_STATES - 1],
        },
        "counts": {
            "total_states": TOTAL_STATES,
            "covered_states": COVERED_COUNT,
            "uncovered_states": UNCOVERED_COUNT,
            "covered_block": [COVERED_LO, COVERED_HI],
            "covered_indices": covered,
            "uncovered_indices": uncovered,
        },
        "evidence_policy": {
            "tracked_evidence_only": True,
            "requires_tracked_at_anchor": sorted(EVIDENCE_PINS),
            "untracked_inputs_never_decide_claims": True,
            "frozen_archive_required": True,
            "archive": dict(ARCHIVE),
        },
        "pins": _pin_block(repo_root, EVIDENCE_PINS, tracked_paths),
        "derived_pins": _pin_block(repo_root, DERIVED_PINS, tracked_paths),
        "untracked_provenance": untracked,
        "symbol_conflicts": [
            {
                "id": "transferfcn_motor_order",
                "scope": "indices 19..35",
                "observed_a": (
                    "builder_state_layout: IntegratorSecondOrderLimited__n at "
                    "19..24, TransferFcn4/1/2_CSTATE at 25..27, then "
                    "MotorNonlinearDynamic8..1 at 28..35"),
                "observed_b": (
                    "docs/coordination/g6-pqr-derivative-path-20260913.md:36 "
                    "requires text: '19-27(TransferFcn)、28-35"
                    "(MotorNonlinearDynamic，约 12.05)'"),
                "resolution": SYM_CONFLICT_ARCHIVE,
                "requires": "model_archive",
                "requires_member": ARCHIVE["header_member"],
                "source_a": "tools/build_first_step_trace.py STATE_LAYOUT",
                "source_b": "docs/coordination/g6-pqr-derivative-path-20260913.md",
            },
        ],
        "entry_classes": {
            "supported": [ENTRY_RESIDUAL, ENTRY_OUTPUT, ENTRY_OUTSIDE],
            "mrdivide_residual_input_indices": [10, 11, 12],
            "mrdivide_output_indices": [10, 11, 12],
            "physical_semantics_inferred": False,
        },
        "divergence_pair": dict(TRACE_DIVERGENCE),
        "index_map": entries,
        "line_bindings": [dict(bindings[key]) for key in sorted(bindings)],
        "doc_refs": doc_refs,
        "unresolved": unresolved_items(repo_root, untracked_available),
        "nonclaims": list(NONCLAIMS),
        "scope_limits": [
            "one case (C3G), one step (k=0->1), one sample set",
            "13 of 36 flat continuous states carry a tracked comparison",
            "coverage is inventory, not conformance and not acceptance",
        ],
    }
    return document


# --------------------------------------------------------------------------
# Deterministic serialization
# --------------------------------------------------------------------------


def dumps(document):
    """Byte-stable JSON text: fixed key order, 2-space indent, ASCII, LF."""
    return json.dumps(document, indent=2, ensure_ascii=True,
                      sort_keys=False) + "\n"


def write_map(document, out_path):
    """Create the output exclusively; never overwrite an existing file."""
    out_path = Path(out_path)
    data = dumps(document).encode("utf-8")
    if out_path.exists() or out_path.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing file: {out_path}")
    with out_path.open("xb") as handle:
        handle.write(data)
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Validation (fail-closed structural checker used by the offline tests)
# --------------------------------------------------------------------------

REQUIRED_TOP_KEYS = frozenset({
    "schema", "kind", "version", "date", "issue", "title", "work_class",
    "layer", "authority", "effective", "generator", "generator_command",
    "anchor", "base_ancestor", "anchor_policy", "r1_status", "g6_acceptance",
    "physical_accuracy", "issues_closed", "budget_approved",
    "pending_approvals", "open_items", "identity", "counts",
    "evidence_policy", "pins", "derived_pins", "untracked_provenance",
    "symbol_conflicts", "entry_classes", "divergence_pair", "index_map",
    "line_bindings", "doc_refs", "unresolved", "nonclaims", "scope_limits",
})

REQUIRED_ENTRY_KEYS = frozenset({
    "index", "covered", "block_symbol", "block_symbol_range",
    "symbol_resolution", "symbol_evidence", "symbol_source", "symbol_note",
    "entry_class", "entry_kind", "entry_reason", "source_line_mapping",
    "tracked_doc_refs", "tracked_line_bindings", "trace_source",
    "reference_source",
})

FORBIDDEN_KEYS = frozenset({
    "budget", "budgets", "budget_request", "budget_approved",
    "approval", "approvals", "approved", "accepted", "acceptance",
    "closure", "closed", "contract_freeze", "frozen_contract",
    "g6_accepted", "r1_passed", "g6_pass", "full_pass", "issue_closed",
})


def _is_int(value):
    return type(value) is int


def _trace_stage2(repo_root):
    """Return ``(stage2_deriv_hex, pqr_stage2_index1_pair)`` read from the
    pinned target trace and the pinned comparison, or ``(None, None)`` when
    either is unreadable.  Read-only; validate() uses these to bind the
    recorded hex against the tracked evidence bytes."""
    deriv = None
    pair = None
    try:
        rows = [json.loads(line) for line in
                (Path(repo_root) / EVIDENCE_PINS["target_first_step_trace"])
                .read_text(encoding="utf-8").splitlines() if line.strip()]
        stage2 = next(row for row in rows
                      if row.get("kind") == "ode4_stage"
                      and row.get("stage") == 2)
        deriv = [str(h).lower().replace("0x", "") for h in stage2["deriv_hex"]]
    except (OSError, ValueError, KeyError, IndexError, StopIteration):
        deriv = None
    try:
        comparison = json.loads(
            (Path(repo_root) / EVIDENCE_PINS["comparison_v2"])
            .read_text(encoding="utf-8"))
        pqr = next(b for b in comparison["blocks"] if b["block"] == "p,q,r")
        pair = next(d for d in pqr["stage_differences"]
                    if d["stage"] == 2 and d["index"] == 1)
    except (OSError, ValueError, KeyError, IndexError, StopIteration):
        pair = None
    return deriv, pair


def validate(document, repo_root=None, recompute_pins=True):
    """Fail-closed structural validation of a map document.

    Returns {"ok": bool, "codes": [sorted error codes], "errors": [messages]}.
    """
    codes = set()
    errors = []

    def flag(code, message):
        codes.add(code)
        errors.append(message)

    if not isinstance(document, dict):
        return {"ok": False, "codes": ["payload_not_object"],
                "errors": ["map payload must be a JSON object"]}

    if document.get("schema") != SCHEMA or document.get("kind") != KIND:
        flag("schema_or_kind_mismatch",
             f"schema/kind mismatch: {document.get('schema')!r}/{document.get('kind')!r}")
    if document.get("version") != 1 or not _is_int(document.get("version")):
        flag("version_mismatch", f"version must be integer 1, got {document.get('version')!r}")

    missing = sorted(REQUIRED_TOP_KEYS - set(document))
    if missing:
        flag("missing_key", f"missing required top-level keys: {missing}")

    # -- anchor / provenance identity --------------------------------------
    if document.get("anchor") != ANCHOR:
        flag("anchor_mismatch",
             f"anchor must be {ANCHOR!r}, got {document.get('anchor')!r}")
    if document.get("base_ancestor") != ANCESTOR:
        flag("base_ancestor_mismatch",
             f"base_ancestor must be {ANCESTOR!r}, "
             f"got {document.get('base_ancestor')!r}")
    anchor_policy = document.get("anchor_policy")
    if not isinstance(anchor_policy, dict):
        flag("anchor_policy_missing", "anchor_policy must be an object")
    else:
        if anchor_policy.get("anchor") != ANCHOR:
            flag("anchor_policy_anchor",
                 "anchor_policy.anchor must match the frozen anchor")
        if anchor_policy.get("anchor_is_ancestor_of_head_required") is not True:
            flag("anchor_policy_ancestry",
                 "anchor_is_ancestor_of_head_required must be true")
        if anchor_policy.get("pinned_evidence_unchanged_since_anchor") is not True:
            flag("anchor_policy_drift",
                 "pinned_evidence_unchanged_since_anchor must be true")
        if anchor_policy.get("observed_head_embedded") is not False:
            flag("anchor_policy_head_embedded",
                 "observed_head_embedded must be false (HEAD is never recorded)")

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
    if document.get("authority") != "none":
        flag("authority_claim", f"authority must be 'none', got {document.get('authority')!r}")

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
            if states.get(expected_id) != expected_state:
                flag("open_item_not_open",
                     f"open item {expected_id!r} must be {expected_state!r}, "
                     f"got {states.get(expected_id)!r}")
        if "g6" in states and states["g6"] != "open":
            flag("g6_not_open", "G6 must remain open")
        if "full" in states and states["full"] != "open":
            flag("full_not_open", "Full must remain open")

    # -- forbidden surface ------------------------------------------------
    for key in sorted(FORBIDDEN_KEYS & set(document)):
        if key == "budget_approved":
            continue  # handled above as a required false flag
        flag("forbidden_key", f"forbidden key present: {key}")
    for container_key in ("derived_pins", "pins"):
        container = document.get(container_key)
        if isinstance(container, dict):
            for key in sorted(FORBIDDEN_KEYS & set(container)):
                flag("forbidden_key", f"forbidden key in {container_key}: {key}")

    # -- index map --------------------------------------------------------
    entries = document.get("index_map")
    if not isinstance(entries, list):
        flag("index_map_not_list", "index_map must be a list")
        return _result(codes, errors)
    indices = []
    for entry in entries:
        if not isinstance(entry, dict):
            flag("index_entry_shape", f"index entry must be an object: {entry!r}")
            continue
        index = entry.get("index")
        if not _is_int(index):
            flag("index_not_integer", f"index must be an exact integer: {index!r}")
            continue
        indices.append(index)
        if not 0 <= index <= TOTAL_STATES - 1:
            flag("index_out_of_domain", f"index {index} outside 0..35")
        extra = sorted(set(entry) - REQUIRED_ENTRY_KEYS - {
            "untracked_provenance", "mrdivide_output_evidence", "output_encoding"})
        if extra:
            flag("index_entry_extra_key", f"index {index} has extra keys: {extra}")
        absent = sorted(REQUIRED_ENTRY_KEYS - set(entry))
        if absent:
            flag("index_entry_missing_key", f"index {index} misses keys: {absent}")
            continue
        if entry["covered"] is not _coverage(index):
            flag("coverage_flag_mismatch",
                 f"index {index} coverage flag {entry['covered']!r} disagrees "
                 f"with the 6..18 rule")
        if entry["symbol_resolution"] not in SYM_STATUSES:
            flag("unknown_symbol_resolution",
                 f"index {index} has unknown symbol_resolution "
                 f"{entry['symbol_resolution']!r}")
        if entry["source_line_mapping"] not in LINE_STATUSES:
            flag("unknown_source_line_status",
                 f"index {index} has unknown source_line_mapping "
                 f"{entry['source_line_mapping']!r}")
        if entry["entry_class"] not in ENTRY_CLASSES:
            flag("unknown_entry_class",
                 f"index {index} has unknown entry_class {entry['entry_class']!r}")
        span = entry["block_symbol_range"]
        if (not isinstance(span, list) or len(span) != 2
                or not all(_is_int(v) for v in span) or span[0] > span[1]
                or not span[0] <= index <= span[1]):
            flag("block_symbol_range_invalid",
                 f"index {index} block_symbol_range {span!r} does not contain it")
        if (entry["symbol_resolution"] == SYM_RESOLVED
                and entry["symbol_evidence"] not in
                ("tracked_comparison_v2_target_indices",
                 "tracked_builder_state_layout")):
            flag("resolved_symbol_without_exact_source",
                 f"index {index} claims resolved with evidence "
                 f"{entry['symbol_evidence']!r}")
        if (entry["symbol_resolution"] != SYM_RESOLVED
                and entry["symbol_evidence"] ==
                "tracked_comparison_v2_target_indices"):
            flag("conflicted_symbol_with_tracked_comparison",
                 f"index {index} claims a conflict while carrying the tracked "
                 f"comparison mapping")
        if (entry["symbol_resolution"] == SYM_CONFLICT_ARCHIVE
                and entry["symbol_evidence"] !=
                "tracked_builder_state_layout_plus_requirement_text"):
            flag("conflicted_symbol_without_conflict_evidence",
                 f"index {index} claims a conflict with evidence "
                 f"{entry['symbol_evidence']!r}")
        if 19 <= index <= TOTAL_STATES - 1:
            if entry["symbol_resolution"] != SYM_CONFLICT_ARCHIVE:
                flag("conflict_range_not_conflicted",
                     f"index {index} in 19..35 must be {SYM_CONFLICT_ARCHIVE!r}")
        elif entry["symbol_resolution"] == SYM_CONFLICT_ARCHIVE:
            flag("conflict_outside_range",
                 f"index {index} outside 19..35 must not be conflicted")
        if (not entry["covered"]
                and entry["entry_class"] != ENTRY_OUTSIDE):
            flag("uncovered_class_not_outside",
                 f"index {index} is uncovered but classified "
                 f"{entry['entry_class']!r}")
    if indices != list(range(TOTAL_STATES)):
        if len(indices) != len(set(indices)):
            flag("duplicate_index", "index_map has duplicate indices")
        if indices != sorted(indices):
            flag("index_order", "index_map is not in ascending order")
        if sorted(indices) != list(range(TOTAL_STATES)):
            flag("index_domain_incomplete",
                 "index_map does not cover exactly 0..35 once each")

    # -- counts -----------------------------------------------------------
    counts = document.get("counts")
    expected_counts = {
        "total_states": TOTAL_STATES,
        "covered_states": COVERED_COUNT,
        "uncovered_states": UNCOVERED_COUNT,
        "covered_block": [COVERED_LO, COVERED_HI],
        "covered_indices": list(range(COVERED_LO, COVERED_HI + 1)),
        "uncovered_indices": list(range(0, COVERED_LO)) + list(range(COVERED_HI + 1, TOTAL_STATES)),
    }
    if not isinstance(counts, dict):
        flag("counts_missing", "counts must be an object")
    else:
        for key, expected in expected_counts.items():
            if counts.get(key) != expected:
                flag("count_mismatch",
                     f"counts[{key!r}] must be {expected!r}, got {counts.get(key)!r}")
        observed_covered = sum(1 for e in entries
                               if isinstance(e, dict) and e.get("covered") is True)
        observed_uncovered = sum(1 for e in entries
                                 if isinstance(e, dict) and e.get("covered") is False)
        if counts.get("covered_states") != observed_covered:
            flag("covered_count_disagrees",
                 "declared covered_states disagrees with the entries")
        if counts.get("uncovered_states") != observed_uncovered:
            flag("uncovered_count_disagrees",
                 "declared uncovered_states disagrees with the entries")
        if observed_covered != COVERED_COUNT:
            flag("covered_block_size", f"expected {COVERED_COUNT} covered entries")
        if observed_uncovered != UNCOVERED_COUNT:
            flag("uncovered_block_size", f"expected {UNCOVERED_COUNT} uncovered entries")

    # -- entry-class section ---------------------------------------------
    classes = document.get("entry_classes")
    if not isinstance(classes, dict):
        flag("entry_classes_missing", "entry_classes must be an object")
    else:
        if classes.get("mrdivide_residual_input_indices") != [10, 11, 12]:
            flag("residual_indices_mismatch",
                 "mrdivide residual input indices must be [10, 11, 12]")
        if classes.get("mrdivide_output_indices") != [10, 11, 12]:
            flag("output_indices_mismatch",
                 "mrdivide output indices must be [10, 11, 12]")
        if classes.get("physical_semantics_inferred") is not False:
            flag("physical_semantics_claim",
                 "physical_semantics_inferred must be false")
        if sorted(classes.get("supported", [])) != sorted(ENTRY_CLASSES):
            flag("entry_class_enum_mismatch",
                 f"supported classes must be {sorted(ENTRY_CLASSES)}")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("index") in (10, 11, 12):
            if entry.get("entry_class") != ENTRY_RESIDUAL:
                flag("residual_class_mismatch",
                     f"index {entry.get('index')} must be {ENTRY_RESIDUAL}")
            if "untracked_provenance" not in entry:
                flag("residual_provenance_missing",
                     f"index {entry.get('index')} lacks untracked provenance")

    # -- index-11 mrdivide output encoding (fail-closed) -------------------
    entry11 = None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("index") == 11:
            entry11 = entry
            break
    if entry11 is not None:
        encoding = entry11.get("output_encoding")
        if not isinstance(encoding, dict):
            flag("output_encoding_missing",
                 "index 11 must carry an output_encoding object")
        else:
            if encoding.get("kind") != ENTRY_OUTPUT:
                flag("output_encoding_kind",
                     f"output_encoding.kind must be {ENTRY_OUTPUT!r}")
            if encoding.get("symbol") != SYM_OUTPUT:
                flag("output_encoding_symbol", "output_encoding.symbol drift")
            if encoding.get("result_equals_derivative_slice") != [10, 13]:
                flag("output_encoding_slice",
                     "result_equals_derivative_slice must be [10, 13]")
            if encoding.get("hex_stage2") != list(TRACE_STAGE2_PQR_HEX):
                flag("output_encoding_hex_value",
                     "hex_stage2 must equal the pinned stage-2 p,q,r "
                     "derivative slice")
        output_evidence = entry11.get("mrdivide_output_evidence")
        if not isinstance(output_evidence, dict):
            flag("mrdivide_output_evidence_missing",
                 "index 11 must carry mrdivide_output_evidence")
        else:
            if (output_evidence.get("index") != 11
                    or output_evidence.get("stage") != 2
                    or output_evidence.get("ulp") != 1):
                flag("mrdivide_output_evidence_content",
                     "mrdivide_output_evidence must record index 11 stage 2 "
                     "ulp 1")
            if (output_evidence.get("target_trace_hex")
                    != TRACE_DIVERGENCE["target_trace_hex"]):
                flag("mrdivide_output_evidence_hex",
                     "mrdivide_output_evidence target hex drift")

    # -- symbol-conflict scope (fail-closed) -------------------------------
    conflicts = document.get("symbol_conflicts")
    if not isinstance(conflicts, list) or not conflicts:
        flag("symbol_conflicts_missing", "symbol_conflicts must be a non-empty list")
    else:
        tfm = [item for item in conflicts
               if isinstance(item, dict) and item.get("id") == "transferfcn_motor_order"]
        if not tfm:
            flag("symbol_conflict_missing",
                 "symbol_conflicts must record transferfcn_motor_order")
        else:
            if tfm[0].get("scope") != "indices 19..35":
                flag("conflict_scope_mismatch",
                     "transferfcn_motor_order scope must be indices 19..35")
            if tfm[0].get("resolution") != SYM_CONFLICT_ARCHIVE:
                flag("conflict_resolution_mismatch",
                     "transferfcn_motor_order must stay conflicted")

    divergence = document.get("divergence_pair")
    if not isinstance(divergence, dict) or divergence.get("index") != 11:
        flag("divergence_pair_mismatch",
             "divergence_pair must record flat index 11")
    else:
        if divergence.get("ulp") != 1:
            flag("divergence_ulp_mismatch", "divergence_pair ulp must be 1")
        if divergence.get("target_trace_hex") == divergence.get("comparison_v2_reference_hex"):
            flag("divergence_pair_equal",
                 "divergence_pair records identical target/reference hex")

    # -- unresolved -------------------------------------------------------
    unresolved = document.get("unresolved")
    if not isinstance(unresolved, list) or not unresolved:
        flag("unresolved_missing", "unresolved must be a non-empty list")
    else:
        required_ids = {
            "archive_source_line_mapping", "authoritative_state_layout",
            "transferfcn_motor_symbol_order", "unmapped_reference_states",
        }
        ids = {item.get("id") for item in unresolved if isinstance(item, dict)}
        if not required_ids <= ids:
            flag("unresolved_incomplete",
                 f"unresolved misses {sorted(required_ids - ids)}")
        for item in unresolved:
            if not isinstance(item, dict):
                flag("unresolved_shape", f"unresolved entry malformed: {item!r}")
                continue
            if item.get("status") != "unresolved":
                flag("unresolved_status", f"{item.get('id')} must stay unresolved")
            if item.get("requires") == "model_archive":
                if item.get("requires_sha256") != ARCHIVE["sha256"]:
                    flag("unresolved_archive_identity",
                         f"{item.get('id')} archive sha256 mismatch")
            if (item.get("id") == "transferfcn_motor_symbol_order"
                    and item.get("scope") != "indices 19..35"):
                flag("conflict_scope_mismatch",
                     "transferfcn_motor_symbol_order scope must be "
                     "indices 19..35")
    if document.get("evidence_policy", {}).get("frozen_archive_required") is not True:
        flag("archive_not_required", "evidence_policy.frozen_archive_required must be true")

    nonclaims = document.get("nonclaims")
    if not isinstance(nonclaims, list) or len(nonclaims) < 5:
        flag("nonclaims_insufficient", "nonclaims must list at least 5 items")
    else:
        blob = " ".join(str(item) for item in nonclaims).lower()
        for needle in ("g6", "r1", "physical", "closure", "budget"):
            if needle not in blob:
                flag("nonclaim_missing", f"nonclaims must address {needle!r}")

    # -- line_bindings (structural, fail-closed) ---------------------------
    line_bindings = document.get("line_bindings")
    if not isinstance(line_bindings, list):
        flag("line_bindings_not_list", "line_bindings must be a list")
    else:
        binding_keys = sorted(
            item.get("key") for item in line_bindings if isinstance(item, dict))
        if (len(line_bindings) != len(LINE_BINDINGS)
                or binding_keys != sorted(LINE_BINDINGS)):
            flag("line_bindings_keys_mismatch",
                 "line_bindings must carry exactly the declared binding keys")
        for item in line_bindings:
            if not isinstance(item, dict):
                flag("line_binding_shape",
                     f"line binding must be an object: {item!r}")
                continue
            required_fields = ("key", "source", "path", "tracked_at_anchor",
                               "sha256", "size", "line_start", "line_end",
                               "text")
            absent_fields = [f for f in required_fields if f not in item]
            if absent_fields:
                flag("line_binding_missing_field",
                     f"line binding {item.get('key')!r} misses {absent_fields}")

    # -- pins -------------------------------------------------------------
    if recompute_pins and repo_root is not None:
        tracked_paths = anchor_tree_paths(repo_root)
        for container_key, table in (("pins", EVIDENCE_PINS),
                                     ("derived_pins", DERIVED_PINS)):
            container = document.get(container_key)
            if not isinstance(container, dict):
                flag("pins_missing", f"{container_key} must be an object")
                continue
            for key, rel_path in sorted(table.items()):
                item = container.get(key)
                if not isinstance(item, dict):
                    flag("pin_missing", f"{container_key}[{key!r}] missing")
                    continue
                if item.get("path") != rel_path:
                    flag("pin_path_mismatch",
                         f"{container_key}[{key!r}] path drift")
                tracked = rel_path in tracked_paths
                if item.get("tracked_at_anchor") is not tracked:
                    flag("pin_tracked_flag_mismatch",
                         f"{container_key}[{key!r}] tracked_at_anchor drift: "
                         f"recorded {item.get('tracked_at_anchor')!r}, HEAD "
                         f"tree says {tracked!r}")
                try:
                    raw, digest, size = read_pin(repo_root, rel_path)
                except OSError as error:
                    flag("pin_unreadable",
                         f"{container_key}[{key!r}] unreadable: {error}")
                    continue
                if item.get("sha256") != digest:
                    flag("pin_hash_mismatch",
                         f"{container_key}[{key!r}] sha256 drift")
                if item.get("size") != size:
                    flag("pin_size_mismatch",
                         f"{container_key}[{key!r}] size drift")
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    for binding in entry.get("tracked_line_bindings", []) or []:
                        if binding.get("source") == key:
                            if binding.get("sha256") != digest:
                                flag("line_binding_hash_mismatch",
                                     f"index {entry.get('index')} binding "
                                     f"{binding.get('key')} hash drift")
                            if binding.get("tracked_at_anchor") is not True:
                                flag("line_binding_not_tracked",
                                     f"index {entry.get('index')} binding "
                                     f"{binding.get('key')} not tracked")

        # -- live anchor relationship (fail-closed on drift) ---------------
        status = anchor_status(repo_root)
        if status["anchor_is_ancestor"] is not True:
            flag("anchor_not_ancestor",
                 "the frozen anchor is not an ancestor of the observed HEAD "
                 "(or this cannot be verified)")
        if status["base_is_ancestor"] is not True:
            flag("base_ancestor_not_ancestor",
                 "the base ancestor is not an ancestor of the observed HEAD "
                 "(or this cannot be verified)")
        if status["drifted_evidence"] is None:
            flag("evidence_drift_unverifiable",
                 "could not compute the anchor..HEAD pinned-evidence diff")
        elif status["drifted_evidence"]:
            flag("evidence_drift",
                 "pinned evidence changed since the anchor: "
                 f"{status['drifted_evidence']}")

        # -- line_bindings / doc_refs recomputation (fail-closed) ----------
        try:
            expected_bindings = build_bindings(repo_root)
        except OSError:
            expected_bindings = None
        if expected_bindings is not None:
            if (isinstance(line_bindings, list)
                    and line_bindings != [expected_bindings[key]
                                          for key in sorted(expected_bindings)]):
                flag("line_bindings_mismatch",
                     "line_bindings do not match the tracked bytes")
            if (document.get("doc_refs")
                    != _doc_refs_from_bindings(expected_bindings)):
                flag("doc_refs_mismatch",
                     "doc_refs do not match the tracked bytes")

        # -- trace-bound hex (fail-closed) ---------------------------------
        deriv, pair = _trace_stage2(repo_root)
        if deriv is not None and isinstance(entry11, dict):
            encoding = entry11.get("output_encoding")
            if (isinstance(encoding, dict)
                    and isinstance(encoding.get("hex_stage2"), list)
                    and encoding["hex_stage2"] != deriv[10:13]):
                flag("output_encoding_hex_mismatch",
                     "hex_stage2 contradicts the pinned trace deriv[10..12]")
        divergence = document.get("divergence_pair")
        if isinstance(divergence, dict) and divergence.get("index") == 11:
            if (deriv is not None
                    and divergence.get("target_trace_hex") != deriv[11]):
                flag("divergence_target_hex_mismatch",
                     "divergence_pair.target_trace_hex contradicts the "
                     "pinned trace")
            if pair is not None:
                if (divergence.get("comparison_v2_reference_hex")
                        != pair["reference_hex"]):
                    flag("divergence_reference_hex_mismatch",
                         "divergence_pair reference hex contradicts "
                         "comparison-v2")
                if (divergence.get("comparison_v2_target_hex")
                        != pair["target_hex"]):
                    flag("divergence_comparison_target_hex_mismatch",
                         "divergence_pair target hex contradicts "
                         "comparison-v2")

    return _result(codes, errors)


def _result(codes, errors):
    ordered = sorted(codes)
    return {"ok": not ordered, "codes": ordered, "errors": sorted(errors)}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=None,
                        help=f"output path (default: <repo-root>/{DEFAULT_OUT})")
    parser.add_argument("--validate", action="store_true",
                        help="validate the existing output instead of writing it")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="print the map to stdout and write nothing")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    out_path = args.out if args.out is not None else repo_root / DEFAULT_OUT

    document = build_map(repo_root)
    result = validate(document, repo_root=repo_root)

    if args.print_only:
        sys.stdout.write(dumps(document))
        return 0

    if args.validate:
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    digest = write_map(document, out_path)
    summary = {
        "output": str(out_path),
        "sha256": digest,
        "size": out_path.stat().st_size,
        "counts": document["counts"],
        "valid": result["ok"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
