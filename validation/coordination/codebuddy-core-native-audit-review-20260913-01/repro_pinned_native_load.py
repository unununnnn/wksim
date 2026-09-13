"""Pure-Python adversarial repros for the pinned native load-site audit.

Reads the real core sources and the audit tool, builds throwaway fixtures in the
system temp directory, mutates only in-memory text, and runs the static audit.
No native library, build, ROS, flight-control, model, UE or MATLAB code is
executed; no process is spawned; no repository file is modified.

Run:  python -B repro_pinned_native_load.py
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # validation/coordination/<dir> -> repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import audit_core_no_vendor_dll as audit_mod  # noqa: E402

PERF = (ROOT / "Simulator/wksim_runtime/perf_capture.py").read_text(encoding="utf-8")
NETNS = (ROOT / "Simulator/wksim_runtime/netns_handoff.py").read_text(encoding="utf-8")
TELEMETRY = (ROOT / "Simulator/wksim_runtime/telemetry_dialect.py").read_text(encoding="utf-8")

MODEL_PY = '"""fixture"""\nimport ctypes\nfrom pathlib import Path\n\n\nclass Model:\n    def __init__(self, library):\n        self.library = ctypes.CDLL(str(Path(library).resolve()))\n'
CONFIG_PY = '"""fixture"""\ndef validate_config(data):\n    return dict(data)\n'
EXAMPLE = {"kind": "session", "model_library": "/x/libwksim_model.so"}
CAP_INDEX = {"baselines": {"ap": {"message_packages": {}}},
             "resource_locations": {"model": "/p/libwksim_model.so"}}
JOINT = {"profiles": [{"id": "p", "model_library": "/p/libwksim_model.so"}]}
MOCK_ALLOWLIST = (
    ("Simulator/wksim_core/model.py", 1, audit_mod._line_sha256('"""fixture"""'), '"""fixture"""', "dummy1"),
    ("Simulator/wksim_runtime/config.py", 1, audit_mod._line_sha256('"""fixture"""'), '"""fixture"""', "dummy2"),
)


def replace_line(text, number, replacement):
    lines = text.splitlines()
    lines[number - 1] = replacement
    return "\n".join(lines) + "\n"


def insert_line(text, number, inserted):
    lines = text.splitlines()
    lines.insert(number - 1, inserted)
    return "\n".join(lines) + "\n"


def fixture(root, perf=PERF, netns=NETNS):
    core = root / "Simulator/wksim_core"
    runtime = root / "Simulator/wksim_runtime"
    planning = root / "Simulator/wksim_planning"
    for d in (core, runtime / "examples", planning):
        d.mkdir(parents=True, exist_ok=True)
    (core / "model.py").write_text(MODEL_PY, encoding="utf-8")
    (core / "__init__.py").write_text("", encoding="utf-8")
    (runtime / "__init__.py").write_text("", encoding="utf-8")
    (runtime / "config.py").write_text(CONFIG_PY, encoding="utf-8")
    (runtime / "joint_config.py").write_text(CONFIG_PY, encoding="utf-8")
    (runtime / "telemetry_dialect.py").write_text(TELEMETRY, encoding="utf-8")
    (runtime / "perf_capture.py").write_text(perf, encoding="utf-8")
    (runtime / "netns_handoff.py").write_text(netns, encoding="utf-8")
    (planning / "__init__.py").write_text("", encoding="utf-8")
    for name in ("arducopter-session.json", "px4-session.json"):
        (runtime / "examples" / name).write_text(json.dumps(EXAMPLE), encoding="utf-8")
    (runtime / "capability-index.json").write_text(json.dumps(CAP_INDEX), encoding="utf-8")
    (runtime / "joint-profiles.json").write_text(json.dumps(JOINT), encoding="utf-8")
    return root


def run(root, perf=PERF, netns=NETNS):
    with tempfile.TemporaryDirectory() as tmp:
        fixture(Path(tmp), perf=perf, netns=netns)
        with mock.patch.object(audit_mod, "KNOWN_VENDOR_REFERENCES", MOCK_ALLOWLIST):
            return audit_mod.audit(Path(tmp))


def load_precedes_gate():
    """Keep the pinned CDLL statement on physical line 51 but defer the SHA gate."""
    o = PERF.splitlines()
    a = o[25:29]          # 26-29 def/platform-if/raise/library=
    b = o[29:34]          # 30-34 path guard + sha-shape guard
    out = o[40:46]        # 41-46 outputs checks
    attrs = o[46:50]      # 47-50 attribute copies
    assert len(a) + len(b) + len(out) + len(attrs) == 19
    filler = ["        # deferred SHA256 gate: load now precedes verification"] * 6
    line51 = o[50]
    assert "ctypes.CDLL(str(library), use_errno=True)" in line51
    digest_block = o[34:40]   # 35-40 digest compute + gate
    new = o[:25] + a + b + out + attrs + filler + [line51] + digest_block + o[51:]
    assert new[50] == line51, "pinned line must land on line 51"
    return "\n".join(new) + "\n"


CASES = [
    ("baseline_unchanged", PERF, NETNS, "pass"),
    ("sha_gate_condition_neutralized_AND_False",
     replace_line(PERF, 39, "        if digest.hexdigest() != library_sha256 and False:"),
     NETNS, "pass"),
    ("sha_gate_raise_replaced_by_pass",
     replace_line(PERF, 40, "            pass"),
     NETNS, "pass"),
    ("path_gate_condition_neutralized_AND_False",
     replace_line(PERF, 30, "        if (not library.is_absolute() or library.suffix != '.so' or not library.is_file()) and False:"),
     NETNS, "pass"),
    ("digest_not_bound_to_loaded_file",
     replace_line(PERF, 38, "                digest.update(b'')"),
     NETNS, "pass"),
    ("load_precedes_sha_gate", load_precedes_gate(), NETNS, "pass"),
    ("libc_handle_reused_for_arbitrary_symbol",
     PERF, insert_line(NETNS, 186, "            libc.system(b'id')"), "pass"),
    ("libc_handle_used_for_file_open",
     PERF, insert_line(NETNS, 186, "            libc.open(b'/etc/passwd', 0)"), "pass"),
    ("libc_handle_reused_as_dlopen_loader",
     PERF, insert_line(NETNS, 186, "            libc.dlopen(b'/tmp/x.so', 2)"), "pass"),
    ("hash_decoy_open_hashes_other_file",
     replace_line(PERF, 36, "        with (library.open('rb'), Path('/etc/hostname').open('rb'))[1] as stream:"),
     NETNS, "pass"),
    ("sha_shape_guard_neutralized_AND_False",
     replace_line(PERF, 33, "                or any(c not in '0123456789abcdef' for c in library_sha256)) and False:"),
     NETNS, "pass"),
    ("control_appended_extra_cdll_must_fail",
     PERF + "\n\ndef extra():\n    return ctypes.CDLL('vendor/x.so')\n",
     NETNS, "failed"),
]


def main():
    results = []
    for name, perf, netns, expected in CASES:
        report = run(ROOT, perf=perf, netns=netns)
        row = {"case": name, "expected": expected,
               "status": report["status"], "violations": report["violations"]}
        row["bypass_confirmed"] = (expected == "pass" and report["status"] == "pass")
        results.append(row)
        print(f"[{report['status']:6}] {name}")
        for v in report["violations"]:
            print(f"          - {v}")
    print("\n=== SUMMARY ===")
    for r in results:
        if r["expected"] == "pass":
            verdict = "BYPASS" if r["status"] == "pass" else "rejected"
        else:
            verdict = "rejected(correct)" if r["status"] == "failed" else "FALSE-PASS"
        print(f"{verdict:18} {r['case']}")
    with open(HERE / "repro_output.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(results, handle, indent=2, sort_keys=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
