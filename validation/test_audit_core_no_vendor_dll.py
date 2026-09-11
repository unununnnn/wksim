"""Pure offline tests for the no-vendor-DLL core audit (#75 supporting gate)."""

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


def _fixture(root, model_py=MODEL_PY, extra_files=None, cap=None, joint=None,
             example=None):
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

    def test_plain_container_and_dict_get_stay_clean(self):
        for label, source in (
            ("plain_get", 'd = {}\nx = d.get("CDLL")\n'),
            ("plain_container", 'f = [len][0]\nf("x")\n'),
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


if __name__ == "__main__":
    unittest.main()
