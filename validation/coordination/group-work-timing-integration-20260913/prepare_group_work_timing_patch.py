"""Prepare (or revert) the removable timing-census patch for JointPhysics.

Pure text transformation on the frozen joint.py source (SHA-256 pinned); the
patched module is only ``ast.parse``-validated, NEVER imported or executed
(its constructor opens sockets).  The patch adds one keyword-only trailing
parameter ``timing_census=False`` (plain bool enforced at runtime); only True
turns the existing cpu_timing startup on and lifts both diagnostic sampling
conditions to a full census handed to the record callback.  False keeps the
old environment flag and threshold logic byte-for-byte; GC timing gating is
untouched.  No phase bracket, equation, clock advance, model RPC or wait is
modified.  Reverts must restore the original bytes verbatim (SHA-checked).

Usage:
    prepare_group_work_timing_patch.py apply  --input joint.py --output out.py
    prepare_group_work_timing_patch.py remove --input out.py  --output back.py
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

EXPECTED_INPUT_SHA256 = \
    "f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50"

# (original fragment, patched fragment); every original must occur exactly once
# in the frozen source and every patched fragment must be absent before apply.
PATCHES = (
    (
        "    def __init__(self, stack, clock, workers, health, record, *,"
        " terrain_feedback=None):",
        "    def __init__(self, stack, clock, workers, health, record, *,"
        " terrain_feedback=None, timing_census=False):",
    ),
    (
        "        self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING')"
        " == '1'\n        if self.cpu_timing:",
        "        self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING')"
        " == '1'\n"
        "        if type(timing_census) is not bool:\n"
        "            raise TypeError('timing_census must be a plain bool')\n"
        "        self.timing_census = timing_census\n"
        "        if timing_census:\n"
        "            self.cpu_timing = True\n"
        "        if self.cpu_timing:",
    ),
    (
        "            if marks[-1][0]-marks[0][0] > 2_000_000"
        " or tick % 250 == 0:",
        "            if self.timing_census or marks[-1][0]-marks[0][0]"
        " > 2_000_000 or tick % 250 == 0:",
    ),
    (
        "            if native_wall_ns > 2_000_000 or tick % 250 == 0:",
        "            if self.timing_census or native_wall_ns > 2_000_000"
        " or tick % 250 == 0:",
    ),
)


class PatchError(RuntimeError):
    """Anchor, duplication or reversibility failure; nothing is written."""


def _rewrite(text, pairs, direction):
    for original, patched in pairs:
        source, target = (original, patched) if direction == "apply" \
            else (patched, original)
        count = text.count(source)
        if count != 1:
            raise PatchError(
                f"anchor not unique ({count} occurrences): {source[:60]!r}")
        if text.count(target):
            raise PatchError(f"target fragment already present: {target[:60]!r}")
        text = text.replace(source, target, 1)
    return text


def apply_patch(source_bytes):
    """Return patched bytes; ast.parse-validated, never imported."""
    text = source_bytes.decode("utf-8")
    if "timing_census" in text:
        raise PatchError("timing_census already present: refusing double apply")
    patched = _rewrite(text, PATCHES, "apply")
    ast.parse(patched, filename="joint.py")
    return patched.encode("utf-8")


def remove_patch(patched_bytes):
    """Inverse of apply_patch; caller SHA-checks the restored bytes."""
    text = patched_bytes.decode("utf-8")
    restored = _rewrite(text, PATCHES, "remove")
    ast.parse(restored, filename="joint.py")
    return restored.encode("utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("apply", "remove"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    data = args.input.read_bytes()
    if args.mode == "apply":
        if _sha256(data) != EXPECTED_INPUT_SHA256:
            raise SystemExit("input SHA-256 is not the frozen joint.py "
                             f"snapshot {EXPECTED_INPUT_SHA256}")
        result = apply_patch(data)
    else:
        result = remove_patch(data)
        restored_sha = _sha256(result)
        if restored_sha != EXPECTED_INPUT_SHA256:
            raise SystemExit("revert is not byte-verbatim: restored SHA-256 "
                             f"{restored_sha} != {EXPECTED_INPUT_SHA256}")

    if args.output.exists():
        raise SystemExit(f"output already exists, refusing: {args.output}")
    with args.output.open("xb") as stream:
        stream.write(result)
    print(json.dumps({
        "mode": args.mode, "input": str(args.input), "output": str(args.output),
        "input_sha256": _sha256(data), "output_sha256": _sha256(result),
        "ast_parse": "ok", "module_executed": False,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
