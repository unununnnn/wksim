"""Pure offline tests for the no-vendor-DLL core audit (#75 supporting gate)."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import audit_core_no_vendor_dll as audit_mod

MODEL_PY = '''"""fixture"""
import ctypes
from pathlib import Path


class Model:
    def __init__(self, library):
        self.library = ctypes.CDLL(str(Path(library).resolve()))
'''
CONFIG_PY = '''"""fixture"""
def validate_config(data):
    return dict(data)
'''
EXAMPLE = {"kind": "session", "model_library": "/x/libwksim_model.so"}
CAP_INDEX = {"baselines": {"ap": {"message_packages": {}}},
             "resource_locations": {"model": "/p/libwksim_model.so"}}
JOINT = {"profiles": [{"id": "p", "model_library": "/p/libwksim_model.so"}]}


TELEMETRY_DIALECT_PY = (ROOT / "Simulator/wksim_runtime/telemetry_dialect.py").read_text(encoding="utf-8")
# The fixture must carry the real pinned native load sites, so that a drifted or
# borrowed exception is exercised by the same audit path the repository uses.
PERF_CAPTURE_PY = (ROOT / "Simulator/wksim_runtime/perf_capture.py").read_text(encoding="utf-8")
NETNS_HANDOFF_PY = (ROOT / "Simulator/wksim_runtime/netns_handoff.py").read_text(encoding="utf-8")


def _replace_line(text, number, replacement):
    """Replace one 1-based line, keeping every other line number in place."""
    lines = text.splitlines()
    lines[number - 1] = replacement
    return "\n".join(lines) + "\n"


def _insert_line(text, number, inserted):
    lines = text.splitlines()
    lines.insert(number - 1, inserted)
    return "\n".join(lines) + "\n"


def _callable_source_sha(text, owner, function_name):
    tree = ast.parse(text)
    body = tree.body
    if owner is not None:
        owner_node = next(node for node in body
                          if isinstance(node, ast.ClassDef) and node.name == owner)
        body = owner_node.body
    function = next(node for node in body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == function_name)
    lines = text.splitlines()
    return audit_mod._line_sha256(
        "\n".join(lines[function.lineno - 1:function.end_lineno]))


def _load_precedes_gate(text):
    """Keep the pinned CDLL statement on physical line 51 but defer the SHA gate."""
    lines = text.splitlines()
    head = lines[25:29]          # 26-29 def/platform-if/raise/library=
    guards = lines[29:34]        # 30-34 path guard + sha-shape guard
    outputs = lines[40:46]       # 41-46 outputs checks
    attrs = lines[46:50]         # 47-50 attribute copies
    line51 = lines[50]
    digest_block = lines[34:40]  # 35-40 digest compute + gate
    assert "ctypes.CDLL(str(library), use_errno=True)" in line51
    filler = ["        # deferred SHA256 gate: load now precedes verification"] * 6
    new = lines[:25] + head + guards + outputs + attrs + filler + [line51] + digest_block + lines[51:]
    assert new[50] == line51, "pinned line must land on line 51"
    return "\n".join(new) + "\n"


def _fixture(root, model_py=MODEL_PY, extra_files=None, cap=None, joint=None,
             example=None, omit=()):
    core = root / "Simulator/wksim_core"
    runtime = root / "Simulator/wksim_runtime"
    planning = root / "Simulator/wksim_planning"
    for directory in (core, runtime / "examples", planning):
        directory.mkdir(parents=True, exist_ok=True)
    (core / "model.py").write_text(model_py, encoding="utf-8")
    (core / "__init__.py").write_text("", encoding="utf-8")
    (runtime / "__init__.py").write_text("", encoding="utf-8")
    (runtime / "config.py").write_text(CONFIG_PY, encoding="utf-8")
    (runtime / "joint_config.py").write_text(CONFIG_PY, encoding="utf-8")
    (runtime / "telemetry_dialect.py").write_text(TELEMETRY_DIALECT_PY, encoding="utf-8")
    (runtime / "perf_capture.py").write_text(PERF_CAPTURE_PY, encoding="utf-8")
    (runtime / "netns_handoff.py").write_text(NETNS_HANDOFF_PY, encoding="utf-8")
    (planning / "__init__.py").write_text("", encoding="utf-8")
    for name in ("arducopter-session.json", "px4-session.json"):
        (runtime / "examples" / name).write_text(
            json.dumps(example or EXAMPLE), encoding="utf-8")
    (runtime / "capability-index.json").write_text(
        json.dumps(cap or CAP_INDEX), encoding="utf-8")
    (runtime / "joint-profiles.json").write_text(
        json.dumps(joint or JOINT), encoding="utf-8")
    for relative, text in (extra_files or {}).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for relative in omit:
        path = root / relative
        if path.is_file():
            path.unlink()
    return root


MOCK_ALLOWLIST = (
    ("Simulator/wksim_core/model.py", 1, audit_mod._line_sha256('"""fixture"""'), '"""fixture"""', "dummy1"),
    ("Simulator/wksim_runtime/config.py", 1, audit_mod._line_sha256('"""fixture"""'), '"""fixture"""', "dummy2"),
)


class NoVendorDllAuditTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def audit(self, **kwargs):
        with mock.patch.object(audit_mod, "KNOWN_VENDOR_REFERENCES", MOCK_ALLOWLIST):
            return audit_mod.audit(_fixture(self.root, **kwargs))

    def test_fixture_passes(self):
        report = self.audit()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["violations"], [])

    def test_first_class_module_escape_cannot_hide_in_object_flow(self):
        samples = [
            'class C: pass\ndef f():\n c=C()\n c.module=ctypes\n return c\nf().module.CDLL("x")\n',
            'class C:\n @property\n def module(self): return ctypes\nC().module.CDLL("x")\n',
            'class C: pass\na=C()\nb=a\na.module=ctypes\nb.module.CDLL("x")\n',
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                report = self.audit(extra_files={"Simulator/wksim_core/probe.py":
                                                'import ctypes\n' + sample})
                self.assertEqual(report["status"], "failed")
                self.assertTrue(any("first-class ctypes module escape" in item
                                    for item in report["violations"]))

    def test_local_module_alias_keeps_ctypes_type_usage(self):
        report = self.audit(extra_files={"Simulator/wksim_core/probe.py":
                                        'import ctypes as C\nmodule=C\nx=module.c_double(2)\n'})
        self.assertEqual(report["status"], "pass")

    def test_extra_load_site_rejected(self):
        extra = {"Simulator/wksim_core/worker.py":
                 "import ctypes\nctypes.WinDLL('x')\n"}
        report = self.audit(extra_files=extra)
        self.assertTrue(any("unexpected dynamic-load" in v for v in report["violations"]))

    def test_missing_allowed_site_rejected(self):
        report = self.audit(model_py='"""no load"""\n')
        self.assertTrue(any("exactly one allowed CDLL" in v for v in report["violations"]))

    def test_vendor_reference_rejected(self):
        report = self.audit(model_py=MODEL_PY + "\nDLL = 'vendor/model.dll'\n")
        self.assertTrue(any("vendor artifact reference" in v for v in report["violations"]))

    def test_allowlist_entry_must_match_exact_line(self):
        bad_allowlist = (
            ("Simulator/wksim_core/model.py", 99, "0" * 64, "model.dll", "x"),
            ("Simulator/wksim_runtime/config.py", 1, audit_mod._line_sha256('"""fixture"""'), '"""fixture"""', "dummy2"),
        )
        with mock.patch.object(audit_mod, "KNOWN_VENDOR_REFERENCES", bad_allowlist):
            _fixture(self.root,
                     model_py=MODEL_PY + "\nDLL = 'vendor/model.dll'\n")
            report = audit_mod.audit(self.root)
        kinds = [v for v in report["violations"]]
        self.assertTrue(any("vendor artifact reference" in v for v in kinds))
        self.assertTrue(any("missing, moved or edited" in v for v in kinds))

    def test_allowlist_count_pinned_at_two(self):
        with mock.patch.object(audit_mod, "KNOWN_VENDOR_REFERENCES", ()):
            report0 = audit_mod.audit(_fixture(self.root))
            self.assertTrue(any("allowlist count must be exactly 2" in v for v in report0["violations"]))

        three_items = MOCK_ALLOWLIST + (("Simulator/wksim_planning/__init__.py", 1, "0" * 64, "x", "y"),)
        with mock.patch.object(audit_mod, "KNOWN_VENDOR_REFERENCES", three_items):
            report3 = audit_mod.audit(_fixture(self.root))
            self.assertTrue(any("allowlist count must be exactly 2" in v for v in report3["violations"]))

    def test_dll_config_field_rejected(self):
        report = self.audit(example={"kind": "session", "vendor_dll": "/x/y.dll"})
        self.assertTrue(any("vendor/DLL config fields" in v for v in report["violations"]))

    def test_config_value_string_vendor_token_rejected(self):
        report1 = self.audit(example={"kind": "session", "custom_exe": "CopterSim.exe"})
        self.assertTrue(any("forbidden vendor/loader token in config value" in v for v in report1["violations"]))

        report2 = self.audit(example={"kind": "session", "plugin_path": "/opt/vendor.dll"})
        self.assertTrue(any("forbidden vendor/loader token in config value" in v for v in report2["violations"]))

    def test_config_error_clean_violation(self):
        bad_validator = '"""fixture"""\ndef validate_config(data):\n    raise ValueError("invalid schema")\n'
        report = self.audit(extra_files={"Simulator/wksim_runtime/config.py": bad_validator})
        self.assertTrue(any("config schema validation error" in v for v in report["violations"]))

    def test_dll_model_pin_rejected(self):
        report = self.audit(joint={"profiles": [{"model_library": "/p/model.dll"}]})
        self.assertTrue(any("DLL model pin" in v for v in report["violations"]))

    def test_non_project_so_pin_rejected(self):
        report = self.audit(cap={"x": "/p/libother_model.so"})
        self.assertTrue(any("non-project model library" in v for v in report["violations"]))


@unittest.skipUnless((ROOT / "Simulator/wksim_core/model.py").is_file(), "repo core absent")
class RealRepositoryTests(unittest.TestCase):
    def test_real_core_passes(self):
        report = audit_mod.audit(ROOT)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["status"], "pass")

    def test_allowlist_entries_still_match_real_lines(self):
        for path, line, line_sha, token, _ in audit_mod.KNOWN_VENDOR_REFERENCES:
            text = (ROOT / path).read_text(encoding="utf-8").splitlines()[line - 1]
            self.assertIn(token, text)
            self.assertEqual(audit_mod._line_sha256(text), line_sha)

    def test_cli_exit_codes(self):
        ok = subprocess.run([sys.executable, "-B",
                             str(ROOT / "tools/audit_core_no_vendor_dll.py")],
                            capture_output=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stderr.decode())
        report = json.loads(ok.stdout.decode())
        self.assertIn("not the #75", " ".join(report["non_claims"]))


class AdversarialHardeningTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def audit(self, **kwargs):
        with mock.patch.object(audit_mod, "KNOWN_VENDOR_REFERENCES", MOCK_ALLOWLIST):
            return audit_mod.audit(_fixture(self.root, **kwargs))

    def test_from_import_cdll_bypass_rejected(self):
        sneaky = '"""fixture"""\nfrom ctypes import CDLL\nCDLL("vendor/x.dll")\n'
        report = self.audit(extra_files={"Simulator/wksim_core/worker.py": sneaky})
        self.assertTrue(any("forbidden ctypes loader import" in v or "unexpected dynamic-load" in v for v in report["violations"]))

    def test_getattr_cdll_bypass_rejected(self):
        sneaky = '"""fixture"""\nimport ctypes\ngetattr(ctypes, "CD" "LL")("x")\n'
        report = self.audit(extra_files={"Simulator/wksim_core/worker.py": sneaky})
        self.assertTrue(any("forbidden getattr" in v or "unexpected dynamic-load" in v for v in report["violations"]))

    def test_loader_assignment_alias_rejected(self):
        code1 = '"""fixture"""\nimport ctypes\nloader = ctypes.CDLL\nloader("vendor.dll")\n'
        report1 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code1})
        self.assertTrue(any("forbidden dynamic loader assignment alias" in v or "unexpected dynamic-load" in v for v in report1["violations"]))

        code2 = '"""fixture"""\nimport ctypes\nloader = ctypes.WinDLL\nloader("vendor.dll")\n'
        report2 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code2})
        self.assertTrue(any("forbidden dynamic loader assignment alias" in v or "unexpected dynamic-load" in v for v in report2["violations"]))

    def test_subscript_loader_rejected(self):
        code1 = '"""fixture"""\nimport ctypes\nlib = ctypes.cdll["vendor.dll"]\n'
        report1 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code1})
        self.assertTrue(any("forbidden ctypes loader subscript access" in v for v in report1["violations"]))

        code2 = '"""fixture"""\nimport ctypes\nlib = ctypes.windll["vendor.dll"]\n'
        report2 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code2})
        self.assertTrue(any("forbidden ctypes loader subscript access" in v for v in report2["violations"]))

    def test_attribute_loader_rejected(self):
        code1 = '"""fixture"""\nimport ctypes\nlib = ctypes.cdll.foo\n'
        report1 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code1})
        self.assertTrue(any("forbidden ctypes loader module access" in v or "attribute access" in v for v in report1["violations"]))

        code2 = '"""fixture"""\nimport ctypes\nlib = ctypes.windll.foo\n'
        report2 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code2})
        self.assertTrue(any("forbidden ctypes loader module access" in v or "attribute access" in v for v in report2["violations"]))

    def test_dynamic_import_getattr_rejected(self):
        code = '"""fixture"""\nmod = __import__("ctypes")\nloader = getattr(mod, "CDLL")\nloader("x")\n'
        report = self.audit(extra_files={"Simulator/wksim_core/worker.py": code})
        self.assertTrue(any("forbidden dynamic __import__" in v or "forbidden getattr" in v for v in report["violations"]))

        code_importlib = '"""fixture"""\nimport importlib\nmod = importlib.import_module("ctypes")\nloader = getattr(mod, "CDLL")\n'
        report2 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code_importlib})
        self.assertTrue(any("forbidden dynamic importlib" in v or "forbidden getattr" in v for v in report2["violations"]))

    def test_hardcoded_literal_in_allowed_model_call_rejected(self):
        bad = ('"""fixture"""\nimport ctypes\nfrom pathlib import Path\n\n'
               'class Model:\n    def __init__(self, library):\n'
               '        self.a = ctypes.CDLL(str(Path(library).resolve()))\n'
               '        self.b = ctypes.CDLL("vendor/x.dll")\n')
        report = self.audit(model_py=bad)
        self.assertTrue(any("hardcoded library literal" in v for v in report["violations"])
                        or any("unexpected dynamic-load" in v for v in report["violations"]))

    def test_symlink_inside_core_package_rejected(self):
        _fixture(self.root)
        target = self.root / "Simulator/wksim_core/model.py"
        link = self.root / "Simulator/wksim_core/evil.py"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("symlink privilege unavailable")
        report = audit_mod.audit(self.root)
        self.assertTrue(any("symlink inside core package" in v
                            for v in report["violations"]))

    def test_symlinked_or_missing_root_rejected(self):
        report = audit_mod.audit(self.root / "absent")
        self.assertTrue(any("audit root" in v for v in report["violations"]))

    def test_duplicate_json_key_and_nan_rejected(self):
        cap = '{"x": "/p/libwksim_model.so", "x": 1}'
        report = self.audit()
        # write raw duplicates directly
        path = self.root / "Simulator/wksim_runtime/capability-index.json"
        path.write_text(cap, encoding="utf-8")
        report = audit_mod.audit(self.root)
        self.assertTrue(any("duplicate JSON key" in v for v in report["violations"]))
        path.write_text('{"x": NaN}', encoding="utf-8")
        report = audit_mod.audit(self.root)
        self.assertTrue(any("disallowed JSON constant" in v for v in report["violations"]))

    def test_deleted_model_identity_entry_fails_per_file(self):
        # 1. capability-index missing pin alone fails
        report_cap = self.audit(cap={"baselines": {}})
        self.assertTrue(any("capability-index.json: model library identity set differs" in v
                            for v in report_cap["violations"]))

        # 2. joint-profiles missing pin alone fails
        report_joint = self.audit(joint={"profiles": [{"id": "p"}]})
        self.assertTrue(any("joint-profiles.json: model library identity set differs" in v
                            for v in report_joint["violations"]))

    def test_unreadable_core_source_clean_violation(self):
        _fixture(self.root)
        bad = self.root / "Simulator/wksim_core/bad.py"
        bad.write_bytes(b"\xff\xfe\x00\x00")
        report = self.audit()
        self.assertTrue(any("unreadable core source" in v for v in report["violations"]))

    def test_nested_package_relative_path(self):
        nested = {"Simulator/wksim_core/subpkg/worker.py": "import ctypes\nctypes.WinDLL('x')\n"}
        report = self.audit(extra_files=nested)
        self.assertTrue(any("Simulator/wksim_core/subpkg/worker.py" in v for v in report["violations"]))

    def test_ctypes_dict_subscript_loader_rejected(self):
        code1 = '"""fixture"""\nimport ctypes\nloader = ctypes.__dict__["CDLL"]\n'
        report1 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code1})
        self.assertTrue(any("forbidden ctypes __dict__ access" in v or "loader subscript access" in v for v in report1["violations"]))

        code2 = '"""fixture"""\nimport ctypes\nloader = ctypes.__dict__["cdll"]\n'
        report2 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code2})
        self.assertTrue(any("forbidden ctypes __dict__ access" in v or "loader subscript access" in v for v in report2["violations"]))

    def test_ctypes_dict_attribute_access_rejected(self):
        code = '"""fixture"""\nimport ctypes\nd = ctypes.__dict__\n'
        report = self.audit(extra_files={"Simulator/wksim_core/worker.py": code})
        self.assertTrue(any("forbidden ctypes __dict__ access" in v for v in report["violations"]))

    def test_vars_ctypes_dynamic_access_rejected(self):
        code1 = '"""fixture"""\nimport ctypes\nv = vars(ctypes)\n'
        report1 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code1})
        self.assertTrue(any("forbidden vars(ctypes) dynamic access" in v for v in report1["violations"]))

        code2 = '"""fixture"""\nimport ctypes\nx = vars(ctypes)["CDLL"]\n'
        report2 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code2})
        self.assertTrue(any("forbidden vars(ctypes)" in v or "loader subscript access" in v for v in report2["violations"]))

    def test_loader_dict_get_rejected(self):
        code1 = '"""fixture"""\nimport ctypes\nx = ctypes.__dict__.get("CDLL")\n'
        report1 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code1})
        self.assertTrue(any("forbidden loader dictionary lookup via .get()" in v for v in report1["violations"]))

        code2 = '"""fixture"""\nimport ctypes\nx = vars(ctypes).get("cdll")\n'
        report2 = self.audit(extra_files={"Simulator/wksim_core/worker.py": code2})
        self.assertTrue(any("forbidden loader dictionary lookup via .get()" in v for v in report2["violations"]))

    def test_unallowlisted_eval_rejected(self):
        code = '"""fixture"""\neval("1 + 1")\n'
        report = self.audit(extra_files={"Simulator/wksim_core/worker.py": code})
        self.assertTrue(any("forbidden dynamic code execution call (eval)" in v for v in report["violations"]))

    def test_unallowlisted_exec_rejected(self):
        code = '"""fixture"""\nexec("x = 1")\n'
        report = self.audit(extra_files={"Simulator/wksim_core/worker.py": code})
        self.assertTrue(any("forbidden dynamic code execution call (exec)" in v for v in report["violations"]))

    def test_unallowlisted_compile_rejected(self):
        code = '"""fixture"""\ncompile("x = 1", "<string>", "exec")\n'
        report = self.audit(extra_files={"Simulator/wksim_core/worker.py": code})
        self.assertTrue(any("forbidden dynamic code execution call (compile)" in v for v in report["violations"]))

    def test_builtins_eval_import_rejected(self):
        code = '"""fixture"""\nfrom builtins import eval\neval("1")\n'
        report = self.audit(extra_files={"Simulator/wksim_core/worker.py": code})
        self.assertTrue(any("forbidden dynamic code execution import (eval)" in v for v in report["violations"]))

    def test_dynamic_exec_allowlist_count_pinned(self):
        with mock.patch.object(audit_mod, "KNOWN_DYNAMIC_EXEC", ()):
            report0 = audit_mod.audit(_fixture(self.root))
            self.assertTrue(any("dynamic exec allowlist count must be exactly 1" in v for v in report0["violations"]))

        two_items = audit_mod.KNOWN_DYNAMIC_EXEC + (("Simulator/wksim_runtime/extra.py", 1, "0" * 64, "exec", "dummy"),)
        with mock.patch.object(audit_mod, "KNOWN_DYNAMIC_EXEC", two_items):
            report2 = audit_mod.audit(_fixture(self.root))
            self.assertTrue(any("dynamic exec allowlist count must be exactly 1" in v for v in report2["violations"]))

    def test_dynamic_exec_allowlist_tampered_sha_rejected(self):
        bad_entry = (("Simulator/wksim_runtime/telemetry_dialect.py", 20, "0" * 64, "exec", "tampered"),)
        with mock.patch.object(audit_mod, "KNOWN_DYNAMIC_EXEC", bad_entry):
            report = audit_mod.audit(_fixture(self.root))
            self.assertTrue(any("allowlisted dynamic exec reference missing, moved or edited" in v for v in report["violations"]))

    def test_dynamic_exec_allowlist_line_drift_rejected(self):
        drifted = '"""fixture"""\n\n' + TELEMETRY_DIALECT_PY  # shifts line 20 down
        report = self.audit(extra_files={"Simulator/wksim_runtime/telemetry_dialect.py": drifted})
        self.assertTrue(any("allowlisted dynamic exec reference missing, moved or edited" in v
                            or "dynamic exec allowlist observation mismatch" in v
                            for v in report["violations"]))

    def test_dynamic_exec_allowlist_missing_call_rejected(self):
        no_call = '"""fixture"""\n' + "\n" * 30
        report = self.audit(extra_files={"Simulator/wksim_runtime/telemetry_dialect.py": no_call})
        self.assertTrue(any("allowlisted dynamic exec reference missing, moved or edited" in v
                            or "dynamic exec allowlist observation mismatch" in v
                            for v in report["violations"]))

    def test_loadable_binary_dll_rejected(self):
        _fixture(self.root)
        dll_path = self.root / "Simulator/wksim_core/vendor.dll"
        dll_path.write_bytes(b"MZfake")
        report = audit_mod.audit(self.root)
        self.assertTrue(any("forbidden loadable binary artifact inside core package: Simulator/wksim_core/vendor.dll" in v
                            for v in report["violations"]))

    def test_loadable_binary_so_rejected(self):
        _fixture(self.root)
        so_path = self.root / "Simulator/wksim_runtime/libnative.so"
        so_path.write_bytes(b"\x7fELFfake")
        report = audit_mod.audit(self.root)
        self.assertTrue(any("forbidden loadable binary artifact inside core package: Simulator/wksim_runtime/libnative.so" in v
                            for v in report["violations"]))

    def test_loadable_binary_pyd_rejected(self):
        _fixture(self.root)
        pyd_path = self.root / "Simulator/wksim_planning/ext.pyd"
        pyd_path.write_bytes(b"MZfake")
        report = audit_mod.audit(self.root)
        self.assertTrue(any("forbidden loadable binary artifact inside core package: Simulator/wksim_planning/ext.pyd" in v
                            for v in report["violations"]))

    def test_stray_bytecode_outside_pycache_rejected(self):
        _fixture(self.root)
        pyc_path = self.root / "Simulator/wksim_core/stray.pyc"
        pyc_path.write_bytes(b"fakebytecode")
        report = audit_mod.audit(self.root)
        self.assertTrue(any("forbidden stray bytecode artifact outside __pycache__: Simulator/wksim_core/stray.pyc" in v
                            for v in report["violations"]))

        pyo_path = self.root / "Simulator/wksim_runtime/stray.pyo"
        pyo_path.write_bytes(b"fakebytecode")
        report2 = audit_mod.audit(self.root)
        self.assertTrue(any("forbidden stray bytecode artifact outside __pycache__: Simulator/wksim_runtime/stray.pyo" in v
                            for v in report2["violations"]))

    def test_orphaned_bytecode_in_pycache_rejected(self):
        _fixture(self.root)
        cache_dir = self.root / "Simulator/wksim_core/__pycache__"
        cache_dir.mkdir(parents=True, exist_ok=True)
        orphan = cache_dir / "orphan.cpython-310.pyc"
        orphan.write_bytes(b"fakebytecode")
        report = audit_mod.audit(self.root)
        self.assertTrue(any("forbidden orphaned bytecode artifact without source: Simulator/wksim_core/__pycache__/orphan.cpython-310.pyc" in v
                            for v in report["violations"]))

    def test_non_bytecode_in_pycache_rejected(self):
        _fixture(self.root)
        cache_dir = self.root / "Simulator/wksim_core/__pycache__"
        cache_dir.mkdir(parents=True, exist_ok=True)
        trojan = cache_dir / "notes.txt"
        trojan.write_text("evil", encoding="utf-8")
        report = audit_mod.audit(self.root)
        self.assertTrue(any("forbidden non-bytecode file inside __pycache__: Simulator/wksim_core/__pycache__/notes.txt" in v
                            for v in report["violations"]))

    def test_legitimate_pycache_with_source_passes(self):
        _fixture(self.root)
        cache_dir = self.root / "Simulator/wksim_core/__pycache__"
        cache_dir.mkdir(parents=True, exist_ok=True)
        valid_pyc = cache_dir / "model.cpython-310.pyc"
        valid_pyc.write_bytes(b"fakebytecode")
        report = audit_mod.audit(self.root)
        self.assertFalse(any("model.cpython-310.pyc" in v for v in report["violations"]))

    def test_fixed_report_schema(self):
        report = self.audit()
        self.assertEqual(report["schema"], "wksim.core-no-vendor-dll.v1")
        self.assertEqual(report["non_claims"], [
            "static audit only; not the #75 fresh-directory run",
            "does not approve or load any vendor ABI",
            "does not prove physics, rate or flight acceptance",
        ])


class ReflectionBypassTests(unittest.TestCase):
    """ctypes.__dict__/vars/attrgetter bypass interception without false positives."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def audit_snippet(self, source):
        _fixture(self.root,
                 extra_files={"Simulator/wksim_core/worker.py": source})
        with mock.patch.object(audit_mod, "KNOWN_VENDOR_REFERENCES", ()):
            return audit_mod.audit(self.root)

    def test_dict_vars_attrgetter_bypasses_caught(self):
        for label, source in (
            ("dict", 'import ctypes\nctypes.__dict__["CDLL"]("x")\n'),
            ("vars", 'import ctypes\nvars(ctypes)["CDLL"]("x")\n'),
            ("alias_dict", 'import ctypes as c\nc.__dict__["CDLL"]("x")\n'),
            ("alias_vars", 'import ctypes as c\nvars(c)["CDLL"]("x")\n'),
            ("dict_get", 'import ctypes\nctypes.__dict__.get("CDLL")("x")\n'),
            ("attrgetter", 'import operator, ctypes\noperator.attrgetter("CDLL")(ctypes)("x")\n'),
            ("assign_alias", 'import ctypes\nx = ctypes.__dict__["CDLL"]\n'),
            ("vars_assign", 'import ctypes\nx = vars(ctypes)["CDLL"]\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("worker.py" in v for v in report["violations"]),
                                report["violations"])

    def test_plain_dict_vars_attrgetter_not_flagged(self):
        for label, source in (
            ("dict", 'd = {"CDLL": 1}\nx = d["CDLL"]\n'),
            ("dict_assign", 'd = {}\nd["CDLL"] = 1\n'),
            ("vars", 'x = 1\nvars()\n'),
            ("attrgetter", 'import operator\noperator.attrgetter("real")(1j)\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertFalse(any("worker.py" in v for v in report["violations"]),
                                 report["violations"])
    def test_pydll_alias_and_importlib_loader_bypasses_caught(self):
        for label, source in (
            ("pydll", 'import ctypes\nctypes.PyDLL("x")\n'),
            ("module_alias_dict", 'import ctypes\nm = ctypes\nd = m.__dict__\nd["CDLL"]("x")\n'),
            ("module_alias_vars", 'import ctypes\nm = ctypes\nvars(m)["CDLL"]("x")\n'),
            ("extension_loader", 'import importlib.machinery as im\nim.ExtensionFileLoader("x", "/v/x.pyd")\n'),
            ("sourceless_loader", 'from importlib.machinery import SourcelessFileLoader\nSourcelessFileLoader("x", "/v/x.pyc")\n'),
            ("pythonapi", 'import ctypes\nctypes.pythonapi.Py_None\n'),
            ("user_getattr_eval_name", 'class G:\n    eval = 1\ng = G()\nx = getattr(g, "eval")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("worker.py" in v for v in report["violations"]),
                                report["violations"])

    def test_owner_named_loader_attrs_stay_clean(self):
        for label, source in (
            ("class_attr_cdll", 'class Foo:\n    CDLL = 1\nx = Foo.CDLL\n'),
            ("user_getattr_cdll", 'class G:\n    CDLL = 1\ng = G()\nx = getattr(g, "CDLL")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertFalse(any("worker.py" in v for v in report["violations"]),
                                 report["violations"])

    def test_carrier_propagation_bypasses_caught(self):
        for label, source in (
            ("container", 'import ctypes\nf = [ctypes.CDLL][0]\nf("/tmp/v.dll")\n'),
            ("tuple_unpack", 'import ctypes\nf, g = ctypes.CDLL, 1\nf("x")\n'),
            ("annassign", 'import ctypes\nf: object = ctypes.CDLL\nf("x")\n'),
            ("return", 'import ctypes\ndef g():\n    return ctypes.CDLL\ng()("x")\n'),
            ("lambda", 'import ctypes\nh = lambda: ctypes.CDLL\nh()("x")\n'),
            ("for_target", 'import ctypes\nfor f in [ctypes.CDLL]:\n    f("x")\n'),
            ("dict_carrier", 'import ctypes\nd = {"f": ctypes.CDLL}\nd["f"]("x")\n'),
            ("attrgetter_alias", 'import operator\nag = operator.attrgetter\nag("CDLL")(__import__("ctypes"))("x")\n'),
            ("attrgetter_static_join", 'import operator, ctypes\noperator.attrgetter("".join(("C", "DLL")))(ctypes)("x")\n'),
            ("dict_get_ctypes", 'import ctypes\nctypes.__dict__.get("CDLL")("x")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("worker.py" in v for v in report["violations"]),
                                report["violations"])

    def test_return_attribute_default_and_comprehension_carriers_rejected(self):
        for label, source in (
            ("function_return", 'import ctypes\n'
             'def factory():\n    return ctypes\n'
             'factory().CDLL("x")\n'),
            ("closure_return", 'import ctypes\n'
             'def outer():\n    module = ctypes\n'
             '    def inner():\n        return module\n'
             '    return inner\n'
             'outer()().CDLL("x")\n'),
            ("lambda_return", 'import ctypes\n'
             'factory = lambda: ctypes\n'
             'factory().CDLL("x")\n'),
            ("factory_chain", 'import ctypes\n'
             'def first(): return ctypes\n'
             'def second(): return first()\n'
             'second().CDLL("x")\n'),
            ("default_capture", 'import ctypes\n'
             'def load(module=ctypes):\n    module.CDLL("x")\n'
             'load()\n'),
            ("kw_default_capture", 'import ctypes\n'
             'def load(*, module=ctypes):\n    module.CDLL("x")\n'
             'load()\n'),
            ("named_expression", 'import ctypes\n'
             '(module := ctypes).CDLL("x")\n'),
            ("list_comprehension", 'import ctypes\n'
             '[ctypes for _ in [0]][0].CDLL("x")\n'),
            ("dict_comprehension", 'import ctypes\n'
             '{"module": ctypes for _ in [0]}["module"].CDLL("x")\n'),
            ("set_comprehension", 'import ctypes\n'
             'next(iter({ctypes for _ in [0]})).CDLL("x")\n'),
            ("generator_expression", 'import ctypes\n'
             'next((ctypes for _ in [0])).CDLL("x")\n'),
            ("class_attribute_carrier", 'import ctypes\n'
             'class Holder:\n    module = ctypes\n'
             'Holder.module.CDLL("x")\n'),
            ("instance_attribute_carrier", 'import ctypes\n'
             'class Holder: pass\n'
             'holder = Holder()\n'
             'holder.module = ctypes\n'
             'holder.module.CDLL("x")\n'),
            ("class_attribute_assignment", 'import ctypes\n'
             'class Holder: pass\n'
             'Holder.module = ctypes\n'
             'Holder.module.CDLL("x")\n'),
            ("setattr_instance_carrier", 'import ctypes\n'
             'class Holder: pass\n'
             'holder = Holder()\n'
             'setattr(holder, "module", ctypes)\n'
             'holder.module.CDLL("x")\n'),
            ("unknown_factory_fail_closed", 'def factory():\n    return unknown_module()\n'
             'factory().CDLL("x")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("worker.py" in v for v in report["violations"]),
                                report["violations"])

    def test_ordinary_attribute_carriers_and_ctypes_types_stay_clean(self):
        for label, source in (
            ("ordinary_class_attribute", 'class Holder:\n'
             '    @staticmethod\n'
             '    def CDLL(value): return value\n'
             'Holder.CDLL("x")\n'),
            ("ordinary_instance_attribute", 'class Holder: pass\n'
             'holder = Holder()\n'
             'holder.CDLL = lambda value: value\n'
             'holder.CDLL("x")\n'),
            ("ctypes_type_defaults", 'import ctypes\n'
             'def parameter(value=ctypes.c_double): return value(1.0)\n'
             'parameter()\n'),
            ("ordinary_import_module", 'import importlib\n'
             'importlib.import_module("json")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertFalse(any("worker.py" in v for v in report["violations"]),
                                 report["violations"])

    def test_plain_container_and_dict_get_stay_clean(self):
        for label, source in (
            ("plain_get", 'd = {}\nx = d.get("CDLL")\n'),
            ("plain_container", 'f = [len][0]\nf("x")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertFalse(any("worker.py" in v for v in report["violations"]),
                                 report["violations"])

    def test_builtin_container_and_parameter_reflection_bypasses_rejected(self):
        for label, source in (
            ("builtins_getattr", 'import ctypes\n'
             '__builtins__["getattr"](ctypes, "CDLL")("x")\n'),
            ("builtins_import", 'm = __builtins__["__import__"]("ctypes")\n'
             'm.CDLL("x")\n'),
            ("globals_builtins_importlib", 'm = globals()["__builtins__"]["__import__"]("importlib")\n'
             'm.import_module("importlib.machinery").ExtensionFileLoader("x", "x.pyd")\n'),
            ("dict_module", 'import ctypes\nd = {"m": ctypes}\n'
             'd["m"].CDLL("x")\n'),
            ("list_module", 'import ctypes\nd = [ctypes]\n'
             'd[0].CDLL("x")\n'),
            ("tuple_getattr", 'import ctypes\nt = (getattr,)\n'
             't[0](ctypes, "CDLL")("x")\n'),
            ("dict_attrgetter", 'import ctypes, operator\n'
             'd = {"g": operator.attrgetter}\n'
             'd["g"]("CDLL")(ctypes)("x")\n'),
            ("dict_import_module", 'import importlib\n'
             'd = {"i": importlib.import_module}\n'
             'd["i"]("importlib.machinery").ExtensionFileLoader("x", "x.pyd")\n'),
            ("parameter_getattr", 'import ctypes\n'
             'def f(g):\n    return g(ctypes, "CDLL")("x")\n'
             'f(getattr)\n'),
            ("parameter_import", 'def f(i):\n    return i("ctypes").CDLL("x")\n'
             'f(__import__)\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("worker.py" in v for v in report["violations"]),
                                report["violations"])

    def test_sensitive_carrier_false_positive_boundaries(self):
        for label, source in (
            ("ordinary_getattr", 'class G:\n    CDLL = 1\n'
             'g = G()\nx = getattr(g, "CDLL")\n'),
            ("ordinary_attrgetter", 'import operator\noperator.attrgetter("real")(1j)\n'),
            ("ordinary_import_module", 'import importlib\nimportlib.import_module("json")\n'),
            ("ctypes_constants", 'import ctypes\nvalues = (ctypes.c_double, ctypes.c_int)\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertFalse(any("worker.py" in v for v in report["violations"]),
                                 report["violations"])

    def test_model_loader_allowlist_requires_model_init_context(self):
        model = ('"""fixture"""\nimport ctypes\nfrom pathlib import Path\n\n'
                 'def unrelated(library):\n'
                 '    return ctypes.CDLL(str(Path(library).resolve()))\n')
        _fixture(self.root, model_py=model)
        with mock.patch.object(audit_mod, "KNOWN_VENDOR_REFERENCES", MOCK_ALLOWLIST):
            report = audit_mod.audit(self.root)
        self.assertTrue(any("outside the pinned call" in v for v in report["violations"]))
        self.assertTrue(any("exactly one allowed CDLL site" in v for v in report["violations"]))

    def test_importlib_loader_reflection_and_import_module_aliases_rejected(self):
        for label, source in (
            ("from_import_module", 'from importlib import import_module\n'
             'm = import_module("importlib.machinery")\n'
             'getattr(m, "ExtensionFileLoader")("x", "x.pyd")\n'),
            ("module_import_module", 'import importlib\n'
             'm = importlib.import_module("importlib.machinery")\n'
             'vars(m)["SourcelessFileLoader"]("x", "x.pyc")\n'),
            ("machinery_from_import", 'from importlib import machinery as m\n'
             'm["ExtensionFileLoader"]("x", "x.pyd")\n'),
            ("machinery_getattr", 'from importlib import machinery as m\n'
             'getattr(m, "SourcelessFileLoader")("x", "x.pyc")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("worker.py" in v for v in report["violations"]),
                                report["violations"])

    def test_attrgetter_import_alias_chain_and_dynamic_name_rejected(self):
        for label, source in (
            ("from_import", 'import ctypes\nfrom operator import attrgetter\n'
             'attrgetter("CDLL")(ctypes)("x")\n'),
            ("second_alias", 'import ctypes, operator\ng = operator.attrgetter\n'
             'h = g\nh("CDLL")(ctypes)("x")\n'),
            ("getattr_alias", 'import ctypes, operator\n'
             'g = getattr(operator, "attrgetter")\n'
             'g("CDLL")(ctypes)("x")\n'),
            ("unknown_name", 'import ctypes, operator\nname = "CDLL"\n'
             'operator.attrgetter(name)(ctypes)("x")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("attrgetter" in v for v in report["violations"]),
                                report["violations"])

    def test_ctypes_vars_alias_and_tuple_module_alias_rejected(self):
        for label, source in (
            ("vars_alias", 'import ctypes\nv = vars\nv(ctypes)["CDLL"]("x")\n'),
            ("tuple_module_alias", 'import ctypes\nm, other = ctypes, 1\n'
             'getattr(m, "CDLL")("x")\n'),
            ("tuple_subscript_alias", 'import ctypes\nm, = (ctypes,)\n'
             'm.__dict__.get("CDLL")("x")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("worker.py" in v for v in report["violations"]),
                                report["violations"])

    def test_getattr_alias_and_getattribute_reflection_rejected(self):
        for label, source in (
            ("getattr_alias", 'import ctypes\ng = getattr\n'
             'g(ctypes, "CDLL")("x")\n'),
            ("ctypes_getattribute", 'import ctypes\n'
             'ctypes.__getattribute__("CDLL")("x")\n'),
            ("object_getattribute", 'import ctypes\n'
             'object.__getattribute__(ctypes, "CDLL")("x")\n'),
            ("object_getattribute_alias", 'import ctypes\n'
             'g = object.__getattribute__\n'
             'g(ctypes, "CDLL")("x")\n'),
            ("ctypes_getattribute_alias", 'import ctypes\n'
             'g = ctypes.__getattribute__\n'
             'g("CDLL")("x")\n'),
            ("getattr_importlib_alias", 'import importlib\ng = getattr\n'
             'm = g(importlib, "import_module")\n'
             'm("ctypes")\n'),
            ("import_alias", 'from builtins import __import__ as imp\n'
             'imp("ctypes")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("worker.py" in v for v in report["violations"]),
                                report["violations"])

    def test_ctypes_and_importlib_wildcard_imports_rejected(self):
        for label, source in (
            ("ctypes_star", 'from ctypes import *\nCDLL("x")\n'),
            ("importlib_star", 'from importlib import *\nimport_module("ctypes")\n'),
            ("machinery_star", 'from importlib.machinery import *\n'
             'ExtensionFileLoader("x", "x.pyd")\n'),
            ("operator_star", 'from operator import *\n'
             'attrgetter("CDLL")(__import__("ctypes"))("x")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("wildcard" in v for v in report["violations"]),
                                report["violations"])

    def test_dynamic_import_module_name_fails_closed_before_loader_access(self):
        for label, source in (
            ("input_name", 'from importlib import import_module\n'
             'name = input()\nm = import_module(name)\n'
             'getattr(m, "ExtensionFileLoader")("x", "x.pyd")\n'),
            ("concatenated_name", 'from importlib import import_module\n'
             'name = "importlib." + "machinery"\n'
             'm = import_module(name)\n'
             'm["ExtensionFileLoader"]("x", "x.pyd")\n'),
            ("importlib_dict", 'import importlib\n'
             'f = importlib.__dict__["import_module"]\n'
             'f("ctypes")\n'),
            ("import_module_attribute_alias", 'import importlib\n'
             'f = importlib.import_module\n'
             'f("ctypes")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("worker.py" in v for v in report["violations"]),
                                report["violations"])

    def test_operator_attrgetter_reflection_aliases_rejected(self):
        for label, source in (
            ("nested_getattr", 'import operator, ctypes\n'
             'getattr(operator, "attrgetter")("CDLL")(ctypes)("x")\n'),
            ("operator_dict", 'import operator, ctypes\n'
             'g = operator.__dict__["attrgetter"]\n'
             'g("CDLL")(ctypes)("x")\n'),
            ("operator_vars", 'import operator, ctypes\n'
             'g = vars(operator)["attrgetter"]\n'
             'g("CDLL")(ctypes)("x")\n'),
            ("operator_getattribute", 'import operator, ctypes\n'
             'operator.__getattribute__("attrgetter")("CDLL")(ctypes)("x")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertTrue(any("worker.py" in v for v in report["violations"]),
                                report["violations"])

    def test_non_loader_ctypes_from_import_stays_clean(self):
        for label, source in (
            ("c_double", 'from ctypes import c_double\nx = c_double(1.0)\n'),
            ("structure", 'from ctypes import Structure\n'
             'class X(Structure):\n    pass\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertFalse(any("worker.py" in v for v in report["violations"]),
                                 report["violations"])

    def test_user_owned_cdll_calls_stay_clean(self):
        for label, source in (
            ("class_owner", 'class Foo:\n'
             '    @staticmethod\n'
             '    def CDLL(value):\n'
             '        return value\n'
             'Foo.CDLL("x")\n'),
            ("custom_module", 'from mymodule import CDLL\nCDLL("x")\n'),
        ):
            with self.subTest(label=label):
                report = self.audit_snippet(source)
                self.assertFalse(any("worker.py" in v for v in report["violations"]),
                                 report["violations"])

    def test_config_surface_restores_import_state(self):
        import sys as _sys
        before_path = list(_sys.path)
        before_modules = {n for n in _sys.modules if n == "Simulator" or n.startswith("Simulator.")}
        _fixture(self.root)
        audit_mod._check_config_surface(self.root, {"violations": []})
        self.assertEqual(list(_sys.path), before_path)
        after_modules = {n for n in _sys.modules if n == "Simulator" or n.startswith("Simulator.")}
        self.assertEqual(after_modules, before_modules)


class PinnedNativeLoadSiteTests(unittest.TestCase):
    """Two non-model native load sites are pinned; nothing may borrow either.

    The recorder CDLL is legitimate only because the caller supplies an absolute
    ``.so`` path that is hashed and compared against a caller-supplied exact
    lowercase SHA256 before the load.  The handoff CDLL is legitimate only
    because it takes the current-process image (``None``) and only calls the
    Linux ``setns`` syscall.  Every test below tries to widen one of those two
    exceptions: another file, another loader attribute, another argument, another
    enclosing callable, a drifted line or a removed guard.
    """

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def audit(self, **kwargs):
        with mock.patch.object(audit_mod, "KNOWN_VENDOR_REFERENCES", MOCK_ALLOWLIST):
            return audit_mod.audit(_fixture(self.root, **kwargs))

    def assertFailsAt(self, report, path, number):
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(path in item and f":{number}" in item
                            for item in report["violations"]), report["violations"])

    def test_pinned_native_load_table_is_frozen(self):
        self.assertEqual(audit_mod.EXPECTED_PINNED_NATIVE_LOAD_SITES, 2)
        observed = {(pin[0], pin[1], pin[6]) for pin in audit_mod.KNOWN_NATIVE_LOAD_SITES}
        self.assertEqual(observed, {
            ("Simulator/wksim_runtime/perf_capture.py", 51,
             audit_mod.PINNED_RECORDER_SHAPE),
            ("Simulator/wksim_runtime/netns_handoff.py", 183,
             audit_mod.PINNED_LIBC_SHAPE),
        })
        callable_keys = {(pin[0], pin[4], pin[5])
                         for pin in audit_mod.KNOWN_NATIVE_LOAD_SITES}
        self.assertEqual(set(audit_mod.PINNED_NATIVE_CALLABLE_SHA256), callable_keys)
        for path, number, line_sha, call_text, owner, function, _, _ in audit_mod.KNOWN_NATIVE_LOAD_SITES:
            source = (ROOT / path).read_text(encoding="utf-8")
            line = source.splitlines()[number - 1]
            self.assertIn(call_text, line, path)
            self.assertEqual(audit_mod._line_sha256(line), line_sha, path)
            self.assertEqual(
                _callable_source_sha(source, owner, function),
                audit_mod.PINNED_NATIVE_CALLABLE_SHA256[(path, owner, function)],
                path,
            )
            self.assertTrue(owner is None or owner.isidentifier(), path)
            self.assertTrue(function.isidentifier(), path)

    def test_fixture_with_real_pinned_sites_passes(self):
        report = self.audit()
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["status"], "pass")

    def test_real_core_needs_the_pinned_exception(self):
        with mock.patch.object(audit_mod, "KNOWN_NATIVE_LOAD_SITES", ()):
            report = audit_mod.audit(ROOT)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("perf_capture.py:51" in v for v in report["violations"]),
                        report["violations"])
        self.assertTrue(any("netns_handoff.py:183" in v for v in report["violations"]),
                        report["violations"])

    def test_adjacent_file_cannot_borrow_the_recorder_exception(self):
        for label, relative in (
            ("sibling", "Simulator/wksim_runtime/perf_capture_copy.py"),
            ("nested", "Simulator/wksim_runtime/sub/perf_capture.py"),
            ("core_package", "Simulator/wksim_core/perf_capture.py"),
        ):
            with self.subTest(label=label):
                report = self.audit(extra_files={relative: PERF_CAPTURE_PY})
                self.assertEqual(report["status"], "failed")
                self.assertTrue(any(f"unexpected dynamic-load site: {relative}:51" in v
                                    for v in report["violations"]), report["violations"])

    def test_adjacent_file_cannot_borrow_the_libc_exception(self):
        relative = "Simulator/wksim_runtime/netns_handoff_copy.py"
        report = self.audit(extra_files={relative: NETNS_HANDOFF_PY})
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(f"unexpected dynamic-load site: {relative}:183" in v
                            for v in report["violations"]), report["violations"])

    def test_recorder_line_drift_rejected(self):
        drifted = _insert_line(PERF_CAPTURE_PY, 1, "# drift")
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": drifted})
        self.assertTrue(any("pinned native load site missing, moved or edited" in v
                            and "perf_capture.py:51" in v for v in report["violations"]),
                        report["violations"])

    def test_libc_line_drift_rejected(self):
        drifted = _insert_line(NETNS_HANDOFF_PY, 1, "# drift")
        report = self.audit(extra_files={"Simulator/wksim_runtime/netns_handoff.py": drifted})
        self.assertTrue(any("pinned native load site missing, moved or edited" in v
                            and "netns_handoff.py:183" in v for v in report["violations"]),
                        report["violations"])

    def test_recorder_sha_gate_removal_rejected(self):
        # Blanking the digest comparison keeps line 51 in place: only the
        # caller-path+SHA256 guard is gone, and the site must fail closed.
        weakened = _replace_line(PERF_CAPTURE_PY, 39, "        if False:")
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": weakened})
        self.assertTrue(any("pinned native load site shape drift (caller_path_sha256)" in v
                            for v in report["violations"]), report["violations"])

    def test_recorder_path_gate_removal_rejected(self):
        weakened = _replace_line(PERF_CAPTURE_PY, 30, "        if False:")
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": weakened})
        self.assertTrue(any("pinned native load site shape drift (caller_path_sha256)" in v
                            for v in report["violations"]), report["violations"])

    def test_recorder_sha_gate_neutralized_and_false_rejected(self):
        # Token-preserving weakening: the comparison stays but ``and False``
        # makes the digest gate unable to fire; it must fail closed.
        weakened = _replace_line(PERF_CAPTURE_PY, 39,
                                 "        if digest.hexdigest() != library_sha256 and False:")
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": weakened})
        self.assertFailsAt(report, "perf_capture.py", 51)

    def test_recorder_sha_gate_raise_removed_rejected(self):
        # The comparison stays but the rejecting branch is gone.
        weakened = _replace_line(PERF_CAPTURE_PY, 40, "            pass")
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": weakened})
        self.assertFailsAt(report, "perf_capture.py", 51)

    def test_recorder_path_gate_neutralized_and_false_rejected(self):
        weakened = _replace_line(
            PERF_CAPTURE_PY, 30,
            "        if (not library.is_absolute() or library.suffix != '.so'"
            " or not library.is_file()) and False:")
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": weakened})
        self.assertFailsAt(report, "perf_capture.py", 51)

    def test_recorder_sha_shape_gate_neutralized_and_false_rejected(self):
        weakened = _replace_line(
            PERF_CAPTURE_PY, 33,
            "                or any(c not in '0123456789abcdef' for c in library_sha256)) and False:")
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": weakened})
        self.assertFailsAt(report, "perf_capture.py", 51)

    def test_recorder_load_preceding_sha_gate_rejected(self):
        # The pinned load stays on line 51 but the digest gate is deferred
        # below it, so the gate no longer dominates the load.
        reordered = _load_precedes_gate(PERF_CAPTURE_PY)
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": reordered})
        self.assertFailsAt(report, "perf_capture.py", 51)

    def test_recorder_digest_decoupled_from_loaded_file_rejected(self):
        # The digest degenerates to the empty-input hash while the gate stays.
        weakened = _replace_line(PERF_CAPTURE_PY, 38, "                digest.update(b'')")
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": weakened})
        self.assertFailsAt(report, "perf_capture.py", 51)

    def test_recorder_decoy_open_hashes_other_file_rejected(self):
        # ``library.open('rb')`` survives as a decoy while the hashed stream
        # comes from a different file; the load still targets ``library``.
        weakened = _replace_line(
            PERF_CAPTURE_PY, 36,
            "        with (library.open('rb'), Path('/etc/hostname').open('rb'))[1] as stream:")
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": weakened})
        self.assertFailsAt(report, "perf_capture.py", 51)

    def test_recorder_callable_pin_rejects_dead_guard_and_path_rebinding(self):
        lines = PERF_CAPTURE_PY.splitlines()
        lines[29] = "        if False:"
        lines[30] = (
            "            if not library.is_absolute() or library.suffix != '.so' "
            "or not library.is_file(): raise PerfCaptureError('path rejected')"
        )
        dead_guard = "\n".join(lines) + "\n"
        rebound = _replace_line(
            PERF_CAPTURE_PY,
            47,
            "        self.library_path = str(library); library = Path('/tmp/evil.so')",
        )
        for label, weakened in (("dead_guard", dead_guard), ("path_rebound", rebound)):
            with self.subTest(label=label):
                report = self.audit(
                    extra_files={"Simulator/wksim_runtime/perf_capture.py": weakened})
                self.assertFailsAt(report, "perf_capture.py", 51)

    def test_recorder_wrong_enclosing_callable_rejected(self):
        renamed = PERF_CAPTURE_PY.replace("    def __init__(self, library_path",
                                          "    def initialize(self, library_path")
        self.assertNotEqual(renamed, PERF_CAPTURE_PY)
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": renamed})
        self.assertTrue(any("pinned native load site callable drift" in v
                            for v in report["violations"]), report["violations"])

    def test_recorder_argument_variants_rejected(self):
        for label, line in (
            ("missing_use_errno", "        self._library = ctypes.CDLL(str(library))"),
            ("hardcoded_path",
             "        self._library = ctypes.CDLL('/opt/vendor.so', use_errno=True)"),
            ("literal_path",
             "        self._library = ctypes.CDLL(str('/tmp/x.so'), use_errno=True)"),
            ("other_loader",
             "        self._library = ctypes.PyDLL(str(library), use_errno=True)"),
            ("win_loader",
             "        self._library = ctypes.WinDLL(str(library), use_errno=True)"),
        ):
            with self.subTest(label=label):
                modified = _replace_line(PERF_CAPTURE_PY, 51, line)
                report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": modified})
                self.assertFailsAt(report, "perf_capture.py", 51)

    def test_recorder_second_load_site_rejected(self):
        appended = PERF_CAPTURE_PY + "\n\ndef extra():\n    return ctypes.CDLL(None, use_errno=True)\n"
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": appended})
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(v.startswith("unexpected dynamic-load site: "
                                         "Simulator/wksim_runtime/perf_capture.py")
                            for v in report["violations"]), report["violations"])

    def test_recorder_loader_alias_rejected(self):
        appended = PERF_CAPTURE_PY + "\n\nloader = ctypes.CDLL\n"
        report = self.audit(extra_files={"Simulator/wksim_runtime/perf_capture.py": appended})
        self.assertTrue(any("forbidden dynamic loader assignment alias" in v
                            for v in report["violations"]), report["violations"])

    def test_libc_flag_constant_drift_rejected(self):
        drifted = _replace_line(NETNS_HANDOFF_PY, 19, "CLONE_NEWNET = 0x40000001")
        report = self.audit(extra_files={"Simulator/wksim_runtime/netns_handoff.py": drifted})
        self.assertTrue(any("pinned native load site shape drift (libc_setns)" in v
                            for v in report["violations"]), report["violations"])

    def test_libc_setns_call_drift_rejected(self):
        drifted = _replace_line(NETNS_HANDOFF_PY, 186,
                                "            if libc.setns(received[0], 0) != 0:")
        report = self.audit(extra_files={"Simulator/wksim_runtime/netns_handoff.py": drifted})
        self.assertTrue(any("pinned native load site shape drift (libc_setns)" in v
                            for v in report["violations"]), report["violations"])

    def test_libc_argument_variants_rejected(self):
        for label, line in (
            ("path_argument",
             "            libc = ctypes.CDLL('libc.so.6', use_errno=True)"),
            ("resolved_path",
             "            libc = ctypes.CDLL(str(Path('/tmp/x').resolve()), use_errno=True)"),
            ("missing_use_errno", "            libc = ctypes.CDLL(None)"),
            ("other_loader",
             "            libc = ctypes.WinDLL(None, use_errno=True)"),
            ("unbound_handle", "            ctypes.CDLL(None, use_errno=True)"),
        ):
            with self.subTest(label=label):
                modified = _replace_line(NETNS_HANDOFF_PY, 183, line)
                report = self.audit(extra_files={"Simulator/wksim_runtime/netns_handoff.py": modified})
                self.assertFailsAt(report, "netns_handoff.py", 183)

    def test_libc_loader_alias_rejected(self):
        appended = NETNS_HANDOFF_PY + "\n\nloader = ctypes.CDLL\n"
        report = self.audit(extra_files={"Simulator/wksim_runtime/netns_handoff.py": appended})
        self.assertTrue(any("forbidden dynamic loader assignment alias" in v
                            for v in report["violations"]), report["violations"])

    def test_pinned_site_file_missing_rejected(self):
        report = self.audit(omit=("Simulator/wksim_runtime/netns_handoff.py",))
        self.assertTrue(any("pinned native load site file missing or not a core .py: "
                            "Simulator/wksim_runtime/netns_handoff.py" in v
                            for v in report["violations"]), report["violations"])

    def test_pinned_native_load_allowlist_count_locked(self):
        with mock.patch.object(audit_mod, "KNOWN_NATIVE_LOAD_SITES", ()):
            report = audit_mod.audit(_fixture(self.root))
            self.assertTrue(any("pinned native load site count must be exactly 2" in v
                                for v in report["violations"]), report["violations"])

        three = audit_mod.KNOWN_NATIVE_LOAD_SITES + (
            ("Simulator/wksim_runtime/extra.py", 1, "0" * 64, "ctypes.CDLL('x')",
             None, "f", audit_mod.PINNED_RECORDER_SHAPE, "dummy"),)
        with mock.patch.object(audit_mod, "KNOWN_NATIVE_LOAD_SITES", three):
            report3 = audit_mod.audit(_fixture(self.root))
            self.assertTrue(any("pinned native load site count must be exactly 2" in v
                                for v in report3["violations"]), report3["violations"])

    def test_libc_handle_other_symbol_rejected(self):
        # Borrowing the pinned handle for any symbol other than setns —
        # including the real dlopen loader — must fail closed.
        for label, inserted in (
            ("system", "            libc.system(b'id')"),
            ("open", "            libc.open(b'/etc/passwd', 0)"),
            ("dlopen", "            libc.dlopen(b'/tmp/x.so', 2)"),
        ):
            with self.subTest(label=label):
                modified = _insert_line(NETNS_HANDOFF_PY, 186, inserted)
                report = self.audit(extra_files={"Simulator/wksim_runtime/netns_handoff.py": modified})
                self.assertFailsAt(report, "netns_handoff.py", 183)

    def test_libc_handle_alias_rejected(self):
        # Copying the pinned handle would let an alias escape the symbol check.
        modified = _insert_line(NETNS_HANDOFF_PY, 186, "            shadow = libc")
        report = self.audit(extra_files={"Simulator/wksim_runtime/netns_handoff.py": modified})
        self.assertFailsAt(report, "netns_handoff.py", 183)

    def test_libc_callable_pin_rejects_container_handle_escape(self):
        modified = _replace_line(
            NETNS_HANDOFF_PY,
            185,
            "            bucket = [libc]; bucket[0].dlopen(b'/tmp/x.so', 2)",
        )
        report = self.audit(extra_files={"Simulator/wksim_runtime/netns_handoff.py": modified})
        self.assertFailsAt(report, "netns_handoff.py", 183)

    def test_unknown_pinned_shape_fails_closed(self):
        pin = list(audit_mod.KNOWN_NATIVE_LOAD_SITES[0])
        pin[6] = "unsupported_shape"
        with mock.patch.object(audit_mod, "KNOWN_NATIVE_LOAD_SITES", (tuple(pin),)), \
                mock.patch.object(audit_mod, "EXPECTED_PINNED_NATIVE_LOAD_SITES", 1):
            report = audit_mod.audit(_fixture(self.root))
        self.assertTrue(any("unknown pinned native load site shape" in v
                            for v in report["violations"]), report["violations"])

    def test_pinned_native_load_allowlist_duplicate_files_rejected(self):
        duplicated = audit_mod.KNOWN_NATIVE_LOAD_SITES + (
            audit_mod.KNOWN_NATIVE_LOAD_SITES[0],)
        with mock.patch.object(audit_mod, "KNOWN_NATIVE_LOAD_SITES", duplicated), \
                mock.patch.object(audit_mod, "EXPECTED_PINNED_NATIVE_LOAD_SITES", 3):
            report = audit_mod.audit(_fixture(self.root))
        self.assertTrue(any("duplicate files" in v or "duplicate file/line" in v
                            for v in report["violations"]), report["violations"])


if __name__ == "__main__":
    unittest.main()
