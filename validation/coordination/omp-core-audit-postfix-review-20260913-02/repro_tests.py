"""Adversarial post-fix review repro for tools/audit_core_no_vendor_dll.py.

Pure AST + temporary-directory fixtures.  This script never loads a native
library, never touches .so/.dll bytes, never starts ROS/flight-control/model/
UE/MATLAB, and never spawns a process.  Every case writes the REAL pinned
source texts into a temp dir (so pinned line numbers/hashes hold), applies one
textual mutation, and runs audit_mod.audit on the fixture root.

A case is a BYPASS when the audit reports status=="pass" although the mutated
semantics break the invariant the P1 fix claims to enforce (expected "failed").
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from validation import test_audit_core_no_vendor_dll as t  # noqa: E402

audit_mod = t.audit_mod
PERF = "Simulator/wksim_runtime/perf_capture.py"
NETNS = "Simulator/wksim_runtime/netns_handoff.py"
PERF_LINES = t.PERF_CAPTURE_PY.splitlines()
NETNS_LINES = t.NETNS_HANDOFF_PY.splitlines()
assert "ctypes.CDLL(str(library), use_errno=True)" in PERF_LINES[50]
assert "ctypes.CDLL(None, use_errno=True)" in NETNS_LINES[182]


def run_audit(extra_files):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        with mock.patch.object(audit_mod, "KNOWN_VENDOR_REFERENCES", t.MOCK_ALLOWLIST):
            report = audit_mod.audit(t._fixture(root, extra_files=extra_files))
    return report


def perf_case(text):
    lines = text.splitlines()
    assert lines[50] == PERF_LINES[50], "pinned perf_capture line 51 must hold"
    return {PERF: text}


def netns_case(text):
    lines = text.splitlines()
    assert lines[182] == NETNS_LINES[182], "pinned netns_handoff line 183 must hold"
    return {NETNS: text}


def wrap_gates_in_dead_def(text):
    """Move every gate/digest token into a never-called nested function."""
    lines = text.splitlines()
    block = [
        "        def _verify(library, library_sha256):",
        "            if not library.is_absolute() or library.suffix != '.so' or not library.is_file(): raise PerfCaptureError('path')",
        "            if not isinstance(library_sha256, str) or len(library_sha256) != 64 or any(c not in '0123456789abcdef' for c in library_sha256): raise PerfCaptureError('sha')",
        "            digest = hashlib.sha256()",
        "            with library.open('rb') as stream:",
        "                for chunk in iter(lambda: stream.read(1024 * 1024), b''):",
        "                    digest.update(chunk)",
        "            if digest.hexdigest() != library_sha256: raise PerfCaptureError('mismatch')",
        "        # filler 1",
        "        # filler 2",
        "        # filler 3",
    ]
    assert len(block) == 11
    new = lines[:29] + block + lines[40:]
    assert new[50] == PERF_LINES[50], "pinned line must land on line 51"
    return "\n".join(new) + "\n"


def swallow_digest_gate(text):
    """Keep the digest gate text but swallow its raise in a try/except."""
    lines = text.splitlines()
    block = [
        "        try:",
        "            if digest.hexdigest() != library_sha256: raise PerfCaptureError('Perf library SHA256 mismatch')",
        "        except PerfCaptureError:",
        "            pass",
    ]
    merged_a = "        self.library_path = str(library); self.library_sha256 = library_sha256"
    merged_b = "        self.raw_path, self.meta_path = map(str, outputs); self.owner_pid, self.owner_tid = _owner()"
    new = lines[:38] + block + lines[40:46] + [merged_a, merged_b] + lines[50:]
    assert new[50] == PERF_LINES[50], "pinned line must land on line 51"
    return "\n".join(new) + "\n"


CASES = []


def case(name, surface, mutation_desc, extra_files):
    CASES.append((name, surface, mutation_desc, extra_files))


# --- controls -------------------------------------------------------------
case("control_baseline", "control", "unmodified fixture", {})
control_cdll = t.PERF_CAPTURE_PY + "\ndef extra():\n    return ctypes.CDLL('vendor/x.so')\n"
case("control_second_cdll", "control", "append a second ctypes.CDLL loader",
     {PERF: control_cdll})

# --- surface 1: gate effectiveness / lexical ordering ----------------------
case("A1_digest_gate_unreachable_raise", "gates",
     "line 40 raise -> `if False: raise ...` (Raise node survives, never fires)",
     perf_case(t._replace_line(t.PERF_CAPTURE_PY, 40,
                               "            if False: raise PerfCaptureError('Perf library SHA256 mismatch')")))
case("A2_path_gate_unreachable_raise", "gates",
     "line 31 raise -> `if False: raise ...`",
     perf_case(t._replace_line(t.PERF_CAPTURE_PY, 31,
                               "            if False: raise PerfCaptureError('An existing absolute .so path is required')")))
case("A3_sha_gate_unreachable_raise", "gates",
     "line 34 raise -> `if False: raise ...`",
     perf_case(t._replace_line(t.PERF_CAPTURE_PY, 34,
                               "            if False: raise PerfCaptureError('An exact lowercase SHA256 is required')")))
b39 = t._replace_line(t.PERF_CAPTURE_PY, 39, "        if False:")
case("B_digest_gate_under_dead_outer_if", "gates",
     "digest gate nested under an outer `if False:` (line count unchanged)",
     perf_case(t._replace_line(
         b39, 40,
         "            if digest.hexdigest() != library_sha256: raise PerfCaptureError('Perf library SHA256 mismatch')")))
case("F_gates_inside_dead_nested_def", "gates",
     "all gates + digest moved into a never-called nested def, load stays bare",
     perf_case(wrap_gates_in_dead_def(t.PERF_CAPTURE_PY)))
case("G_digest_gate_raise_swallowed", "gates",
     "digest gate inside try/except PerfCaptureError: pass",
     perf_case(swallow_digest_gate(t.PERF_CAPTURE_PY)))

# --- surface 2: digest/path data flow --------------------------------------
case("C_vacuous_read_zero", "dataflow",
     "line 37 read(1024*1024) -> read(0): loop never feeds, digest = empty hash",
     perf_case(t._replace_line(t.PERF_CAPTURE_PY, 37,
                               "            for chunk in iter(lambda: stream.read(0), b''):")))
case("D_path_rebound_after_verify", "dataflow",
     "line 47 += `; library = Path('/tmp/evil.so')`: verify good file, load evil",
     perf_case(t._replace_line(t.PERF_CAPTURE_PY, 47,
                               "        self.library_path = str(library); library = Path('/tmp/evil.so')")))
case("E_digest_rebound_during_feed", "dataflow",
     "line 38 += `; digest = hashlib.sha256()`: gate compares a fresh empty digest",
     perf_case(t._replace_line(t.PERF_CAPTURE_PY, 38,
                               "                digest.update(chunk); digest = hashlib.sha256()")))

# --- surface 3: CDLL(None) handle escape -----------------------------------
case("H1_handle_escape_walrus", "handle",
     "insert `(h := libc).system(b'id')` at line 186",
     netns_case(t._insert_line(t.NETNS_HANDOFF_PY, 186, "            (h := libc).system(b'id')")))
case("H2_handle_escape_container", "handle",
     "insert `[libc][0].system(b'id')` at line 186",
     netns_case(t._insert_line(t.NETNS_HANDOFF_PY, 186, "            [libc][0].system(b'id')")))
case("H3_handle_escape_lambda", "handle",
     "insert `(lambda: libc)().system(b'id')` at line 186",
     netns_case(t._insert_line(t.NETNS_HANDOFF_PY, 186, "            (lambda: libc)().system(b'id')")))
case("H4_handle_escape_return", "handle",
     "line 194 `return dict(...)` -> `return libc` (caller receives the handle)",
     netns_case(t._replace_line(t.NETNS_HANDOFF_PY, 194, "            return libc")))
case("H5_handle_escape_container_dlopen", "handle",
     "insert `[libc][0].dlopen(b'/tmp/x.so', 2)` at line 186 (real loader via container)",
     netns_case(t._insert_line(t.NETNS_HANDOFF_PY, 186, "            [libc][0].dlopen(b'/tmp/x.so', 2)")))
case("H6_handle_escape_comprehension", "handle",
     "insert `[x.system(b'id') for x in [libc]]` at line 186",
     netns_case(t._insert_line(t.NETNS_HANDOFF_PY, 186, "            [x.system(b'id') for x in [libc]]")))


def main():
    results = []
    for name, surface, desc, extra in CASES:
        report = run_audit(extra)
        status = report["status"]
        expected = "pass" if name == "control_baseline" else "failed"
        bypass = (status != expected)
        results.append({
            "case": name,
            "surface": surface,
            "mutation": desc,
            "expected": expected,
            "actual": status,
            "bypass": bypass,
            "first_violations": report["violations"][:2],
        })
    print(json.dumps(results, indent=2, ensure_ascii=False))
    n_bypass = sum(1 for r in results if r["bypass"])
    print(f"\n{len(results)} cases, {n_bypass} unexpected results "
          f"(bypass = audit outcome contradicts the claimed invariant)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
