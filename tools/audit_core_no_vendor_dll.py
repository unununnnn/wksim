"""Fail-closed audit: the default autonomous core never resolves vendor DLLs.

Proves statically, on the current repository tree, that the autonomous core
packages (wksim_core, wksim_runtime, wksim_planning):

1. contain exactly one dynamic-library load site as an AST-verified
   ``ctypes.CDLL`` call in ``Simulator/wksim_core/model.py`` whose argument is
   the caller-supplied path (``str(Path(library).resolve())``) with no
   hardcoded vendor/Windows DLL literal; ``from ctypes import CDLL``,
   ``getattr(ctypes, ...)`` and attribute-chain variants are all detected;
2. never reference vendor artifacts (``.dll``, ``CopterSim.exe``,
   ``DllSimCtrlAPI``, ``RflySim``) in Python source outside an exact
   line-and-content-pinned allowlist;
3. expose no vendor/DLL/plugin path field in the runtime config schemas
   (validated example configs included);
4. pin exactly the project-built model library names exported from the
   frozen expectation set — removing an identity entry fails the audit.

This is a static invariant audit.  It is NOT the #75 run: the ticket's
"execute once in a fresh directory" requirement stays blocked on #74 and is
not claimed here.

Usage:
    python3 -B tools/audit_core_no_vendor_dll.py [--output REPORT]
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

REPORT_SCHEMA = "wksim.core-no-vendor-dll.v1"
ROOT = Path(__file__).resolve().parents[1]
CORE_PACKAGES = ("Simulator/wksim_core", "Simulator/wksim_runtime",
                 "Simulator/wksim_planning")
EXAMPLE_CONFIGS = ("Simulator/wksim_runtime/examples/arducopter-session.json",
                   "Simulator/wksim_runtime/examples/px4-session.json")
CAPABILITY_INDEX = "Simulator/wksim_runtime/capability-index.json"
JOINT_PROFILES = "Simulator/wksim_runtime/joint-profiles.json"
CONFIG_SOURCES = ("Simulator/wksim_runtime/config.py",
                  "Simulator/wksim_runtime/joint_config.py")

# Frozen model-library identities, exported from the pinned evidence: the set
# observed in the identity files must equal this exactly (no more, no less).
EXPECTED_MODEL_LIBS = frozenset({"libwksim_model.so"})
EXPECTED_ALLOWLIST_COUNT = 2
EXPECTED_DYNAMIC_EXEC_COUNT = 1

FORBIDDEN_LOADABLE_EXTENSIONS = frozenset({".dll", ".pyd", ".so", ".dylib", ".exe"})
BYTECODE_EXTENSIONS = frozenset({".pyc", ".pyo"})

VENDOR_RE = re.compile(r"\.dll\b|CopterSim\.exe|DllSimCtrlAPI|RflySim",
                       re.IGNORECASE)
CONFIG_KEY_RE = re.compile(r"dll|plugin|vendor", re.IGNORECASE)
CONFIG_VALUE_RE = re.compile(
    r"\.dll\b|CopterSim\.exe|DllSimCtrlAPI|RflySim|LoadLibrary|dlopen|WinDLL|OleDLL",
    re.IGNORECASE,
)

# Vendor tokens that exist for provenance/guard reasons only.  Each entry is
# (relative path, 1-based line, sha256 of the exact line, token contained,
# justification).  Any new reference, moved line, edited line, or allowlist
# add/remove/duplicate fails the audit.
KNOWN_VENDOR_REFERENCES = (
    ("Simulator/wksim_core/model.py", 15,
     "64406af0ac2082545ea2dde6d45b0f7bc6b8144fbd5e45b6bc81668a299e4559",
     "/mnt/e/rflysimtools",
     "legacy build-time archive provenance constant; the runtime Model loads only "
     "a caller-supplied library and the pinned model is the project-generated e0 build"),
    ("Simulator/wksim_runtime/joint_runtime.py", 478,
     "50d84d7a7fea63689a2af3763da245811b96dfac46b7f2054843f8dff530193a",
     "coptersim.exe",
     "defensive guard rejecting vendor runtime dependencies from process maps"),
)

# Legitimate dynamic code generation/execution sites pinned by exact file, line
# number and line SHA256.  Any extra exec/eval/compile, moved line, or line drift fails.
KNOWN_DYNAMIC_EXEC = (
    ("Simulator/wksim_runtime/telemetry_dialect.py", 20,
     "f16205be5a12b6ca7f6f3db0a349bdaddad18645a00f4812aeafe015dcc6a6d1",
     "exec(compile(raw, str(source), 'exec'), module.__dict__)",
     "isolated generated per-firmware MAVLink dialect loader executing pre-hashed bytes"),
)

_LOAD_NAMES = frozenset({"CDLL", "PyDLL", "WinDLL", "OleDLL", "LoadLibrary", "dlopen"})
_LOADER_ATTRS = frozenset({"cdll", "windll", "oledll"})
# pythonapi is a pre-bound PyDLL of the running interpreter: a live native-call
# surface with no vendor-DLL semantics.  It is forbidden in core all the same,
# because this audit certifies "no native surface beyond the one pinned CDLL".
_FORBIDDEN_CPYTHON_ATTRS = frozenset({"pythonapi"})
_IMPORTLIB_LOADER_NAMES = frozenset({"ExtensionFileLoader", "SourcelessFileLoader"})
_ALL_LOADER_TOKENS = _LOAD_NAMES | _LOADER_ATTRS


def _line_sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fail(report, message):
    report["violations"].append(message)
    return report


def _reject_duplicate_keys(pairs):
    seen = set()
    result = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key: {key!r}")
        seen.add(key)
        result[key] = value
    return result


def _reject_json_constant(constant):
    raise ValueError(f"disallowed JSON constant: {constant!r}")


def load_json_strict(path):
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys,
                      parse_constant=_reject_json_constant)


def _iter_core_python(root, report):
    """Yield (relative, path, text) for core .py files; refuse symlink tricks."""
    files = []
    for package in CORE_PACKAGES:
        base = root / package
        if base.is_symlink() or not base.is_dir():
            _fail(report, f"core package missing or symlinked: {package}")
            continue
        for path in sorted(base.rglob("*")):
            if path.is_symlink():
                _fail(report, f"symlink inside core package: {path.relative_to(root).as_posix()}")
                continue
            if path.is_dir() or path.suffix != ".py":
                continue
            rel = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as error:
                _fail(report, f"unreadable core source: {rel}: {error}")
                continue
            files.append((rel, path, text))
    return files


def _eval_str(node):
    """Statically resolve string expressions (constants, concatenation, f-strings)."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return node.value
        if isinstance(node.value, bytes):
            try:
                return node.value.decode("utf-8", errors="ignore")
            except Exception:
                return ""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _eval_str(node.left)
        right = _eval_str(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts = [_eval_str(v) for v in node.values]
        if all(p is not None for p in parts):
            return "".join(parts)
    # Static "<sep>".join(("C", "DLL")) style assembly.
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join" and not node.keywords and len(node.args) == 1):
        sep = _eval_str(node.func.value)
        seq = node.args[0]
        if sep is not None and isinstance(seq, (ast.Tuple, ast.List)):
            parts = [_eval_str(elt) for elt in seq.elts]
            if all(p is not None for p in parts):
                return sep.join(parts)
    return None


def _is_allowed_model_call(node):
    """True iff the call is exactly ctypes.CDLL(str(Path(library).resolve()))."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "CDLL"
            and isinstance(func.value, ast.Name) and func.value.id == "ctypes"):
        return False
    if len(node.args) != 1 or node.keywords:
        return False
    arg = node.args[0]
    if isinstance(arg, ast.Constant):
        return False  # any hardcoded literal is forbidden
    return (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)
            and arg.func.id == "str" and len(arg.args) == 1
            and isinstance(arg.args[0], ast.Call)
            and isinstance(arg.args[0].func, ast.Attribute)
            and arg.args[0].func.attr == "resolve"
            and isinstance(arg.args[0].func.value, ast.Call)
            and isinstance(arg.args[0].func.value.func, ast.Name)
            and arg.args[0].func.value.func.id == "Path"
            and len(arg.args[0].func.value.args) == 1
            and isinstance(arg.args[0].func.value.args[0], ast.Name)
            and arg.args[0].func.value.args[0].id == "library")


def _model_allowed_loader_call_ids(tree):
    """Return only the exact loader call in ``Model.__init__(..., library)``."""
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    allowed = set()
    for node in ast.walk(tree):
        if not _is_allowed_model_call(node):
            continue
        function = None
        owner = None
        parent = parents.get(id(node))
        while parent is not None:
            if function is None and isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function = parent
            if isinstance(parent, ast.ClassDef):
                owner = parent
                break
            parent = parents.get(id(parent))
        parameters = () if function is None else (
            list(function.args.posonlyargs) + list(function.args.args) +
            list(function.args.kwonlyargs))
        if (function is not None and function.name == "__init__"
                and owner is not None and owner.name == "Model"
                and any(parameter.arg == "library" for parameter in parameters)):
            allowed.add(id(node.func))
    return allowed


def _check_loadable_artifacts(root, report):
    """Refuse binary loadable artifacts and stray/orphaned bytecode in core packages."""
    for package in CORE_PACKAGES:
        base = root / package
        if base.is_symlink() or not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_symlink() or path.is_dir():
                continue
            rel = path.relative_to(root).as_posix()
            suffix = path.suffix.lower()
            if suffix in FORBIDDEN_LOADABLE_EXTENSIONS:
                _fail(report, f"forbidden loadable binary artifact inside core package: {rel}")
                continue
            if suffix in BYTECODE_EXTENSIONS:
                if path.parent.name != "__pycache__":
                    _fail(report, f"forbidden stray bytecode artifact outside __pycache__: {rel}")
                    continue
                stem = path.name.split(".")[0]
                source_file = path.parent.parent / f"{stem}.py"
                if not source_file.is_file():
                    _fail(report, f"forbidden orphaned bytecode artifact without source: {rel}")
                    continue
            elif path.parent.name == "__pycache__":
                _fail(report, f"forbidden non-bytecode file inside __pycache__: {rel}")


def _check_dynamic_exec_allowlist(root, report, files):
    if len(KNOWN_DYNAMIC_EXEC) != EXPECTED_DYNAMIC_EXEC_COUNT:
        _fail(report, f"dynamic exec allowlist count must be exactly {EXPECTED_DYNAMIC_EXEC_COUNT}, got {len(KNOWN_DYNAMIC_EXEC)}")
    pairs = [(e[0], e[1]) for e in KNOWN_DYNAMIC_EXEC]
    if len(set(pairs)) != len(pairs):
        _fail(report, "dynamic exec allowlist has duplicate file/line entries")
    seen_lines = {}
    for relative, path, text in files:
        for number, line in enumerate(text.splitlines(), 1):
            seen_lines[(relative, number)] = line
    allowed = set()
    for relative, number, line_sha, token, _ in KNOWN_DYNAMIC_EXEC:
        line = seen_lines.get((relative, number))
        if line is None or _line_sha256(line) != line_sha or token not in line:
            _fail(report, "allowlisted dynamic exec reference missing, moved or edited: "
                          f"{relative}:{number}")
        else:
            allowed.add((relative, number))
    return allowed


def _check_load_sites(root, report, files, allowed_dynamic_exec):
    allowed_count = 0
    observed_dynamic_exec = set()
    literal_re = re.compile(
        r"""ctypes\.(?:CDLL|WinDLL|OleDLL)\(\s*['"]([^'"]+)['"]""")

    for relative, path, text in files:
        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError as error:
            _fail(report, f"unparseable core source: {relative}: {error}")
            continue

        aliases = set()
        ctypes_aliases = {"ctypes"}
        importlib_aliases = {"importlib"}
        importlib_machinery_aliases = set()
        import_module_aliases = set()
        import_function_aliases = {"__import__"}
        vars_aliases = {"vars"}
        getattr_aliases = {"getattr"}
        getattribute_aliases = set()
        ctypes_getattribute_aliases = set()
        attrgetter_aliases = set()
        operator_aliases = set()
        allowed_loader_attrs = (
            _model_allowed_loader_call_ids(tree)
            if relative == "Simulator/wksim_core/model.py" else set())

        def is_vars_call(node):
            return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in vars_aliases and len(node.args) >= 1)

        def is_ctypes_expr(expr):
            if isinstance(expr, ast.Name):
                return expr.id in ctypes_aliases
            if isinstance(expr, ast.Attribute):
                return is_ctypes_expr(expr.value)
            if isinstance(expr, ast.Call) and is_vars_call(expr):
                return is_ctypes_expr(expr.args[0])
            if isinstance(expr, ast.Subscript):
                value = expr.value
                if isinstance(value, (ast.Tuple, ast.List)) and isinstance(expr.slice, ast.Constant):
                    if isinstance(expr.slice.value, int) and 0 <= expr.slice.value < len(value.elts):
                        return is_ctypes_expr(value.elts[expr.slice.value])
                return is_ctypes_expr(value)
            if isinstance(expr, ast.IfExp):
                return is_ctypes_expr(expr.body) or is_ctypes_expr(expr.orelse)
            if isinstance(expr, ast.BoolOp):
                return any(is_ctypes_expr(value) for value in expr.values)
            return False

        def is_importlib_module_expr(expr):
            if isinstance(expr, ast.Name):
                return expr.id in importlib_aliases
            if isinstance(expr, ast.Attribute):
                return is_importlib_module_expr(expr.value)
            return False

        def is_import_module_expr(expr):
            if isinstance(expr, ast.Name):
                return expr.id in import_module_aliases
            return (isinstance(expr, ast.Attribute) and expr.attr == "import_module"
                    and is_importlib_module_expr(expr.value))

        def is_trusted_import_module_call(node):
            if not isinstance(node, ast.Call):
                return False
            if isinstance(node.func, ast.Name):
                return node.func.id in import_module_aliases
            if isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                return is_importlib_module_expr(node.func.value)
            return False

        def is_machinery_expr(expr):
            if isinstance(expr, ast.Name):
                return expr.id in importlib_machinery_aliases
            if isinstance(expr, ast.Attribute):
                if expr.attr == "machinery" and is_importlib_module_expr(expr.value):
                    return True
                return is_machinery_expr(expr.value)
            if isinstance(expr, ast.Call) and is_trusted_import_module_call(expr):
                return bool(expr.args) and _eval_str(expr.args[0]) == "importlib.machinery"
            if isinstance(expr, ast.Call) and is_vars_call(expr):
                return is_machinery_expr(expr.args[0])
            return False

        def is_attrgetter_expr(expr):
            if isinstance(expr, ast.Name):
                return expr.id in attrgetter_aliases
            if isinstance(expr, ast.Attribute):
                return expr.attr == "attrgetter" and is_operator_expr(expr.value)
            if isinstance(expr, ast.Subscript):
                return (_eval_str(expr.slice) == "attrgetter"
                        and (is_operator_expr(expr.value)
                             or (isinstance(expr.value, ast.Attribute)
                                 and expr.value.attr == "__dict__"
                                 and is_operator_expr(expr.value.value))
                             or (isinstance(expr.value, ast.Call)
                                 and is_vars_call(expr.value)
                                 and expr.value.args
                                 and is_operator_expr(expr.value.args[0]))))
            if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) \
                    and expr.func.id in getattr_aliases and len(expr.args) >= 2:
                return _eval_str(expr.args[1]) == "attrgetter"
            return False

        def is_operator_expr(expr):
            return isinstance(expr, ast.Name) and expr.id in operator_aliases

        def is_getattribute_expr(expr):
            if isinstance(expr, ast.Name):
                return expr.id in getattribute_aliases
            return isinstance(expr, ast.Attribute) and expr.attr == "__getattribute__"

        def is_ctypes_getattribute_expr(expr):
            if isinstance(expr, ast.Name):
                return expr.id in ctypes_getattribute_aliases
            return (isinstance(expr, ast.Attribute) and expr.attr == "__getattribute__"
                    and is_ctypes_expr(expr.value))

        def bind_names(target, value, names, predicate):
            if isinstance(target, ast.Starred):
                target = target.value
            if isinstance(target, ast.Name):
                if predicate(value):
                    names.add(target.id)
                return
            if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
                for left, right in zip(target.elts, value.elts):
                    bind_names(left, right, names, predicate)

        def bind_loader_names(target, value):
            if isinstance(target, ast.Starred):
                target = target.value
            if isinstance(target, ast.Name):
                aliases.add(target.id)
                return
            if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
                for left, right in zip(target.elts, value.elts):
                    bind_loader_names(left, right)

        def bind_aliases(target, value):
            bind_names(target, value, ctypes_aliases, is_ctypes_expr)
            bind_names(target, value, importlib_machinery_aliases, is_machinery_expr)
            bind_names(target, value, vars_aliases,
                      lambda expr: isinstance(expr, ast.Name) and expr.id in vars_aliases)
            bind_names(target, value, getattr_aliases,
                      lambda expr: isinstance(expr, ast.Name) and expr.id in getattr_aliases)
            bind_names(target, value, attrgetter_aliases, is_attrgetter_expr)
            bind_names(target, value, import_module_aliases,
                      is_import_module_expr)
            bind_names(target, value, import_function_aliases,
                      lambda expr: isinstance(expr, ast.Name) and expr.id in import_function_aliases)
            bind_names(target, value, getattribute_aliases, is_getattribute_expr)
            bind_names(target, value, ctypes_getattribute_aliases, is_ctypes_getattribute_expr)
            bind_names(target, value, operator_aliases,
                      lambda expr: isinstance(expr, ast.Name) and expr.id in operator_aliases)

        for node in ast.walk(tree):
            # 1. Imports from ctypes, importlib, operator or builtins.
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in ("ctypes", "_ctypes") or mod.startswith("ctypes."):
                    for alias in node.names:
                        if alias.name == "*":
                            _fail(report, f"forbidden wildcard ctypes import at {relative}:{node.lineno}")
                        elif alias.name in _ALL_LOADER_TOKENS:
                            _fail(report, f"forbidden ctypes loader import at {relative}:{node.lineno}: "
                                          f"from {mod} import {alias.name}")
                            aliases.add(alias.asname or alias.name)
                elif mod in ("builtins", "__builtin__", "__builtins__"):
                    for alias in node.names:
                        if alias.name == "*":
                            _fail(report, f"forbidden wildcard builtins import at {relative}:{node.lineno}")
                        if alias.name in {"eval", "exec", "compile"}:
                            _fail(report, f"forbidden dynamic code execution import ({alias.name}) at {relative}:{node.lineno}")
                        if alias.name == "vars":
                            vars_aliases.add(alias.asname or alias.name)
                        if alias.name == "getattr":
                            getattr_aliases.add(alias.asname or alias.name)
                        if alias.name == "__import__":
                            import_function_aliases.add(alias.asname or alias.name)
                elif mod == "operator":
                    for alias in node.names:
                        if alias.name == "*":
                            _fail(report, f"forbidden wildcard operator import at {relative}:{node.lineno}")
                        elif alias.name == "attrgetter":
                            attrgetter_aliases.add(alias.asname or alias.name)
                elif mod == "importlib":
                    for alias in node.names:
                        if alias.name == "*":
                            _fail(report, f"forbidden wildcard importlib import at {relative}:{node.lineno}")
                        elif alias.name == "import_module":
                            import_module_aliases.add(alias.asname or alias.name)
                        elif alias.name == "machinery":
                            importlib_machinery_aliases.add(alias.asname or alias.name)
                        elif alias.name in _IMPORTLIB_LOADER_NAMES:
                            _fail(report, f"forbidden native/bytecode loader import ({alias.name}) at {relative}:{node.lineno}")
                elif mod.startswith("importlib."):
                    for alias in node.names:
                        if alias.name == "*":
                            _fail(report, f"forbidden wildcard importlib loader import at {relative}:{node.lineno}")
                        elif alias.name in _IMPORTLIB_LOADER_NAMES:
                            _fail(report, f"forbidden native/bytecode loader import ({alias.name}) at {relative}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("ctypes", "_ctypes"):
                        ctypes_aliases.add(alias.asname if alias.asname else alias.name)
                    elif alias.name in ("builtins", "__builtin__"):
                        _fail(report, f"forbidden dynamic execution module import at {relative}:{node.lineno}")
                    elif alias.name == "importlib":
                        importlib_aliases.add(alias.asname if alias.asname else alias.name)
                    elif alias.name == "importlib.machinery":
                        importlib_machinery_aliases.add(alias.asname if alias.asname else "machinery")
                        _fail(report, f"forbidden native/bytecode loader module import at {relative}:{node.lineno}")
                    elif alias.name == "operator":
                        operator_aliases.add(alias.asname if alias.asname else alias.name)

            # 2. Dynamic module imports: __import__('ctypes') or import_module(...).
            if isinstance(node, ast.Call):
                if (isinstance(node.func, ast.Name)
                        and node.func.id in import_function_aliases):
                    module_name = _eval_str(node.args[0]) if node.args else None
                    if module_name is None:
                        _fail(report, f"forbidden dynamic __import__ module name at {relative}:{node.lineno}")
                    elif "ctypes" in module_name:
                        _fail(report, f"forbidden dynamic __import__ of ctypes at {relative}:{node.lineno}")
                elif ((isinstance(node.func, ast.Attribute) and node.func.attr == "import_module")
                      or (isinstance(node.func, ast.Name) and node.func.id in import_module_aliases)):
                    module_name = _eval_str(node.args[0]) if node.args else None
                    if module_name is None:
                        _fail(report, f"forbidden dynamic importlib module name at {relative}:{node.lineno}")
                    elif "ctypes" in module_name:
                        _fail(report, f"forbidden dynamic importlib of ctypes at {relative}:{node.lineno}")
                    if is_trusted_import_module_call(node) and module_name == "importlib.machinery":
                        _fail(report, f"forbidden dynamic importlib loader module at {relative}:{node.lineno}")

            # 3. Dynamic execution calls: eval, exec, compile.
            if isinstance(node, ast.Call):
                call_name = None
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile"}:
                    call_name = node.func.id
                elif isinstance(node.func, ast.Attribute) and node.func.attr in {"eval", "exec"}:
                    call_name = node.func.attr
                elif (isinstance(node.func, ast.Attribute) and node.func.attr == "compile"
                      and not (isinstance(node.func.value, ast.Name) and node.func.value.id == "re")):
                    call_name = "compile"
                if call_name is not None:
                    if (relative, node.lineno) not in allowed_dynamic_exec:
                        _fail(report, f"forbidden dynamic code execution call ({call_name}) at {relative}:{node.lineno}")
                    else:
                        observed_dynamic_exec.add((relative, node.lineno))

            # 4. Access to ctypes/importlib machinery dictionaries or vars aliases.
            if isinstance(node, ast.Attribute) and node.attr == "__dict__":
                if is_ctypes_expr(node.value):
                    _fail(report, f"forbidden ctypes __dict__ access at {relative}:{node.lineno}")
                elif is_machinery_expr(node.value):
                    _fail(report, f"forbidden importlib loader __dict__ access at {relative}:{node.lineno}")
                elif is_importlib_module_expr(node.value):
                    _fail(report, f"forbidden importlib __dict__ access at {relative}:{node.lineno}")
                elif is_operator_expr(node.value):
                    _fail(report, f"forbidden operator __dict__ access at {relative}:{node.lineno}")
            if isinstance(node, ast.Call) and is_vars_call(node):
                if is_ctypes_expr(node.args[0]):
                    _fail(report, f"forbidden vars(ctypes) dynamic access at {relative}:{node.lineno}")
                elif is_machinery_expr(node.args[0]):
                    _fail(report, f"forbidden vars(importlib.machinery) dynamic access at {relative}:{node.lineno}")
                elif is_importlib_module_expr(node.args[0]):
                    _fail(report, f"forbidden vars(importlib) dynamic access at {relative}:{node.lineno}")
                elif is_operator_expr(node.args[0]):
                    _fail(report, f"forbidden vars(operator) dynamic access at {relative}:{node.lineno}")

            # 5. Dictionary .get() with loader token on a native owner.
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get" and len(node.args) >= 1):
                base_expr = node.func.value
                token = _eval_str(node.args[0])
                if token in _ALL_LOADER_TOKENS and is_ctypes_expr(base_expr):
                    _fail(report, f"forbidden loader dictionary lookup via .get() at {relative}:{node.lineno}")
                elif token in _IMPORTLIB_LOADER_NAMES and is_machinery_expr(base_expr):
                    _fail(report, f"forbidden importlib loader dictionary lookup via .get() at {relative}:{node.lineno}")

            # 6. Subscript loader access on ctypes/importlib machinery owners.
            if isinstance(node, ast.Subscript):
                val = node.value
                slice_val = _eval_str(node.slice)
                base_ctypes = is_ctypes_expr(val)
                base_machinery = is_machinery_expr(val)
                if (isinstance(val, ast.Attribute) and val.attr in _LOADER_ATTRS
                        and is_ctypes_expr(val.value)):
                    _fail(report, f"forbidden ctypes loader subscript access at {relative}:{node.lineno}")
                elif isinstance(val, ast.Name) and val.id in _LOADER_ATTRS and val.id in aliases:
                    _fail(report, f"forbidden ctypes loader subscript access at {relative}:{node.lineno}")
                elif isinstance(val, ast.Attribute) and val.attr == "__dict__" and is_ctypes_expr(val.value):
                    _fail(report, f"forbidden ctypes __dict__ subscript access at {relative}:{node.lineno}")
                elif isinstance(val, ast.Attribute) and val.attr == "__dict__" and is_machinery_expr(val.value):
                    _fail(report, f"forbidden importlib loader __dict__ subscript access at {relative}:{node.lineno}")
                elif isinstance(val, ast.Call) and is_vars_call(val) and val.args:
                    if is_ctypes_expr(val.args[0]):
                        _fail(report, f"forbidden vars(ctypes) subscript access at {relative}:{node.lineno}")
                    elif is_machinery_expr(val.args[0]):
                        _fail(report, f"forbidden vars(importlib.machinery) subscript access at {relative}:{node.lineno}")
                elif slice_val in _ALL_LOADER_TOKENS and base_ctypes:
                    _fail(report, f"forbidden ctypes loader subscript access ({slice_val}) at {relative}:{node.lineno}")
                elif slice_val in _IMPORTLIB_LOADER_NAMES and base_machinery:
                    _fail(report, f"forbidden importlib loader subscript access ({slice_val}) at {relative}:{node.lineno}")

            # 6c. Reject ctypes-owned loader references while keeping user-owned
            # Foo.CDLL references clean.
            if (isinstance(node, ast.Attribute) and node.attr in _LOAD_NAMES
                    and is_ctypes_expr(node.value) and id(node) not in allowed_loader_attrs):
                _fail(report, f"forbidden loader reference outside the pinned call "
                              f"({node.attr}) at {relative}:{node.lineno}")

            # 6d. attrgetter aliases fail closed for unknown/dynamic names.
            if isinstance(node, ast.Call):
                is_attrgetter_call = (
                    is_attrgetter_expr(node.func)
                ) or (isinstance(node.func, ast.Name) and node.func.id in attrgetter_aliases)
                if is_attrgetter_call:
                    values = [_eval_str(arg) for arg in node.args]
                    if (not values or any(value is None for value in values)
                            or any(value in _ALL_LOADER_TOKENS for value in values)):
                        _fail(report, f"forbidden attrgetter dynamic loader access at {relative}:{node.lineno}")

            # 7. Attribute access on ctypes/importlib loader owners.
            if isinstance(node, ast.Attribute):
                if node.attr in _LOADER_ATTRS and is_ctypes_expr(node.value):
                    _fail(report, f"forbidden ctypes loader module access ({node.attr}) at {relative}:{node.lineno}")
                elif ((isinstance(node.value, ast.Attribute) and node.value.attr in _LOADER_ATTRS
                       and is_ctypes_expr(node.value.value))
                      or (isinstance(node.value, ast.Name) and node.value.id in _LOADER_ATTRS
                          and node.value.id in aliases)):
                    _fail(report, f"forbidden ctypes loader attribute access ({node.attr}) at {relative}:{node.lineno}")
                elif node.attr in _FORBIDDEN_CPYTHON_ATTRS and is_ctypes_expr(node.value):
                    _fail(report, f"forbidden pre-bound interpreter library handle ({node.attr}) at {relative}:{node.lineno}")
                elif node.attr in _IMPORTLIB_LOADER_NAMES and is_machinery_expr(node.value):
                    _fail(report, f"forbidden native/bytecode loader access ({node.attr}) at {relative}:{node.lineno}")

            # 8. getattr loader calls, including returned importlib machinery modules.
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in getattr_aliases):
                if len(node.args) >= 2:
                    attr_val = _eval_str(node.args[1])
                    base = node.args[0]
                    base_is_ctypes = is_ctypes_expr(base)
                    base_is_machinery = is_machinery_expr(base)
                    if attr_val in {"eval", "exec", "compile"}:
                        _fail(report, f"forbidden getattr dynamic code execution access ({attr_val}) at {relative}:{node.lineno}")
                    elif attr_val in _ALL_LOADER_TOKENS and base_is_ctypes:
                        _fail(report, f"forbidden getattr dynamic loader access ({attr_val}) at {relative}:{node.lineno}")
                    elif base_is_ctypes and (attr_val is None or attr_val in ("__dict__",)):
                        _fail(report, f"suspicious dynamic getattr on ctypes at {relative}:{node.lineno}")
                    elif attr_val in _IMPORTLIB_LOADER_NAMES and base_is_machinery:
                        _fail(report, f"forbidden getattr importlib loader access ({attr_val}) at {relative}:{node.lineno}")
                    elif base_is_machinery and (attr_val is None or attr_val == "__dict__"):
                        _fail(report, f"suspicious dynamic getattr on importlib machinery at {relative}:{node.lineno}")
                    elif is_importlib_module_expr(base) and attr_val in {"import_module", "machinery"}:
                        _fail(report, f"forbidden importlib reflection access ({attr_val}) at {relative}:{node.lineno}")

            # __getattribute__ is an equivalent reflection surface to getattr.
            if ((isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and node.func.attr == "__getattribute__")
                    or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in getattribute_aliases)):
                owner = (node.func.value if isinstance(node.func, ast.Attribute) else None)
                lookup_owner = owner
                lookup_index = 0
                lookup_is_ctypes_alias = (
                    isinstance(node.func, ast.Name)
                    and node.func.id in ctypes_getattribute_aliases)
                if lookup_is_ctypes_alias:
                    lookup_owner = node.func
                    lookup_index = 0
                elif isinstance(node.func, ast.Name):
                    lookup_owner = node.args[0] if node.args else None
                    lookup_index = 1
                if not (is_ctypes_expr(lookup_owner) or is_machinery_expr(lookup_owner)
                        or is_importlib_module_expr(lookup_owner) or is_operator_expr(lookup_owner)):
                    if node.args:
                        lookup_owner = node.args[0]
                        lookup_index = 1
                if (len(node.args) > lookup_index
                        and (lookup_is_ctypes_alias or is_ctypes_expr(lookup_owner)
                             or is_machinery_expr(lookup_owner)
                             or is_importlib_module_expr(lookup_owner) or is_operator_expr(lookup_owner))):
                    attr_val = _eval_str(node.args[lookup_index])
                    if (attr_val is None or attr_val in _ALL_LOADER_TOKENS
                            or attr_val in _IMPORTLIB_LOADER_NAMES
                            or attr_val in {"__dict__", "import_module", "machinery", "attrgetter"}):
                        _fail(report, f"forbidden __getattribute__ reflection access at {relative}:{node.lineno}")

            # 9. Assignment alias tracking plus loader-alias rejection.
            if isinstance(node, ast.Assign):
                rhs = node.value
                for target in node.targets:
                    bind_aliases(target, rhs)
                is_loader_alias = (
                    isinstance(rhs, ast.Attribute) and rhs.attr in _ALL_LOADER_TOKENS
                    and is_ctypes_expr(rhs.value))
                if isinstance(rhs, ast.Name) and rhs.id in aliases:
                    is_loader_alias = True
                elif (isinstance(rhs, ast.Call) and isinstance(rhs.func, ast.Name)
                      and rhs.func.id in getattr_aliases):
                    if (len(rhs.args) >= 2 and _eval_str(rhs.args[1]) in _ALL_LOADER_TOKENS
                            and is_ctypes_expr(rhs.args[0])):
                        is_loader_alias = True
                elif isinstance(rhs, ast.Subscript):
                    is_loader_alias = (
                        _eval_str(rhs.slice) in _ALL_LOADER_TOKENS
                        and is_ctypes_expr(rhs.value))
                if is_loader_alias:
                    _fail(report, f"forbidden dynamic loader assignment alias at {relative}:{node.lineno}")
                    for target in node.targets:
                        bind_loader_names(target, rhs)

            if isinstance(node, ast.AnnAssign) and node.value is not None:
                bind_aliases(node.target, node.value)

            # 10. Dynamic library call sites require a ctypes owner or a
            # previously rejected ctypes loader alias; Foo.CDLL is user code.
            if isinstance(node, ast.Call):
                func = node.func
                func_parts = []
                f = func
                while isinstance(f, ast.Attribute):
                    func_parts.append(f.attr)
                    f = f.value
                if isinstance(f, ast.Name):
                    func_parts.append(f.id)
                func_parts.reverse()
                loads_library = (
                    isinstance(func, ast.Attribute) and func.attr in _LOAD_NAMES
                    and is_ctypes_expr(func.value)) or (
                        isinstance(func, ast.Name) and func.id in aliases)
                if loads_library:
                    if relative == "Simulator/wksim_core/model.py" and id(func) in allowed_loader_attrs:
                        allowed_count += 1
                    else:
                        _fail(report, f"unexpected dynamic-load site: {relative}:{node.lineno} ({'.'.join(func_parts) or 'alias'})")

        for match in literal_re.finditer(text):
            _fail(report, f"hardcoded library literal at {relative}: {match.group(1)!r}")

    if allowed_count != 1:
        _fail(report, f"expected exactly one allowed CDLL site, got {allowed_count}")

    if observed_dynamic_exec != allowed_dynamic_exec:
        _fail(report, f"dynamic exec allowlist observation mismatch: "
                      f"expected {sorted(allowed_dynamic_exec)}, observed {sorted(observed_dynamic_exec)}")

def _check_vendor_references(root, report, files):
    if len(KNOWN_VENDOR_REFERENCES) != EXPECTED_ALLOWLIST_COUNT:
        _fail(report, f"allowlist count must be exactly {EXPECTED_ALLOWLIST_COUNT}, got {len(KNOWN_VENDOR_REFERENCES)}")
    pairs = [(e[0], e[1]) for e in KNOWN_VENDOR_REFERENCES]
    if len(set(pairs)) != len(pairs):
        _fail(report, "allowlist has duplicate file/line entries")
    seen_lines = {}
    for relative, path, text in files:
        for number, line in enumerate(text.splitlines(), 1):
            seen_lines[(relative, number)] = line
    matched = set()
    for relative, number, line_sha, token, _ in KNOWN_VENDOR_REFERENCES:
        line = seen_lines.get((relative, number))
        if line is None or _line_sha256(line) != line_sha or token not in line:
            _fail(report, "allowlisted vendor reference missing, moved or edited: "
                          f"{relative}:{number}")
        else:
            matched.add((relative, number))
    for (relative, number), line in seen_lines.items():
        for match in VENDOR_RE.finditer(line):
            if (relative, number) not in matched:
                _fail(report, f"vendor artifact reference at {relative}:{number}: "
                              f"{match.group(0)!r}")


def _config_keys(value):
    keys = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            keys.add(str(key))
            keys |= _config_keys(inner)
    elif isinstance(value, list):
        for inner in value:
            keys |= _config_keys(inner)
    return keys


def _config_strings(value):
    strings = set()
    if isinstance(value, dict):
        for inner in value.values():
            strings |= _config_strings(inner)
    elif isinstance(value, list):
        for inner in value:
            strings |= _config_strings(inner)
    elif isinstance(value, str):
        strings.add(value)
    return strings


def _check_config_surface(root, report):
    for module_name in CONFIG_SOURCES:
        path = root / module_name
        if path.is_symlink() or not path.is_file():
            _fail(report, f"config schema source missing or linked: {module_name}")
    inserted = str(root) not in sys.path
    if inserted:
        sys.path.insert(0, str(root))
    cached = {name: module for name, module in sys.modules.items()
              if name == "Simulator" or name.startswith("Simulator.")}
    validate_config = None
    try:
        for name in cached:
            del sys.modules[name]
        from Simulator.wksim_runtime.config import validate_config as validator
        validate_config = validator
    except Exception as error:
        _fail(report, f"cannot import runtime config validator: {error}")
    finally:
        for name in [n for n in list(sys.modules)
                     if n == "Simulator" or n.startswith("Simulator.")]:
            del sys.modules[name]
        sys.modules.update(cached)
        if inserted:
            sys.path.remove(str(root))
    if validate_config is None:
        return
    for relative in EXAMPLE_CONFIGS:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            _fail(report, f"example config missing or linked: {relative}")
            continue
        try:
            data = load_json_strict(path)
        except ValueError as error:
            _fail(report, f"{relative}: {error}")
            continue
        try:
            normalized = validate_config(data)
        except Exception as error:
            _fail(report, f"{relative}: config schema validation error: {error}")
            continue
        offenders = [key for key in _config_keys(normalized) if CONFIG_KEY_RE.search(key)]
        if offenders:
            _fail(report, f"{relative}: vendor/DLL config fields present: {offenders}")
        bad_values = [val for val in _config_strings(normalized) if CONFIG_VALUE_RE.search(val)]
        if bad_values:
            _fail(report, f"{relative}: forbidden vendor/loader token in config value: {bad_values}")


def _check_model_identity(root, report):
    for relative in (CAPABILITY_INDEX, JOINT_PROFILES):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            _fail(report, f"identity file missing or linked: {relative}")
            continue
        try:
            data = load_json_strict(path)
        except ValueError as error:
            _fail(report, f"{relative}: {error}")
            continue

        def walk(value):
            if isinstance(value, dict):
                for inner in value.values():
                    yield from walk(inner)
            elif isinstance(value, list):
                for inner in value:
                    yield from walk(inner)
            elif isinstance(value, str) and (".so" in value or ".dll" in value):
                yield value

        file_observed = set()
        for entry in walk(data):
            name = entry.rsplit("/", 1)[-1]
            if name.endswith(".dll"):
                _fail(report, f"{relative}: DLL model pin {name}")
            elif ".so" in name:
                if not name.startswith("libwksim_"):
                    _fail(report, f"{relative}: non-project model library pin {name}")
                else:
                    file_observed.add(name)
        if file_observed != EXPECTED_MODEL_LIBS:
            _fail(report, f"{relative}: model library identity set differs: "
                          f"observed {sorted(file_observed)}, expected {sorted(EXPECTED_MODEL_LIBS)}")


def audit(root=ROOT):
    root = Path(root)
    report = {"schema": REPORT_SCHEMA,
              "status": "pass",
              "claim": ("default autonomous core has exactly one caller-supplied "
                        "libwksim_*.so load site and no vendor DLL surface"),
              "non_claims": [
                  "static audit only; not the #75 fresh-directory run",
                  "does not approve or load any vendor ABI",
                  "does not prove physics, rate or flight acceptance",
              ],
              "violations": []}
    if root.is_symlink() or not root.is_dir():
        return _fail(report, "audit root is missing or a symlink")
    resolved = root.resolve()
    if not resolved.is_absolute():
        return _fail(report, "audit root must resolve to an absolute directory")
    files = _iter_core_python(resolved, report)
    _check_loadable_artifacts(resolved, report)
    allowed_dynamic_exec = _check_dynamic_exec_allowlist(resolved, report, files)
    _check_load_sites(resolved, report, files, allowed_dynamic_exec)
    _check_vendor_references(resolved, report, files)
    _check_config_surface(resolved, report)
    _check_model_identity(resolved, report)
    if report["violations"]:
        report["status"] = "failed"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = audit()
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(raw, encoding="utf-8", newline="\n")
    sys.stdout.buffer.write(raw.encode("utf-8"))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
