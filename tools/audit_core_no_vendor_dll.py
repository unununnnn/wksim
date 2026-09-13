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
        setattr_aliases = {"setattr"}
        vars_aliases = {"vars"}
        getattr_aliases = {"getattr"}
        getattribute_aliases = set()
        ctypes_getattribute_aliases = set()
        attrgetter_aliases = set()
        operator_aliases = set()
        container_bindings = {}
        function_parameter_names = set()

        # Small, deliberately conservative abstract interpreter.  The audit
        # must not execute source, but a syntax-only walk misses a native
        # loader hidden behind a factory, closure, object attribute or
        # comprehension.  Values carry only the identities needed by this
        # audit; unknown owners remain distinct so ordinary user-owned fields
        # can stay clean while an unknown ``x.CDLL`` fails closed.
        class _StaticValue:
            __slots__ = ("tags", "funcs", "items")

            def __init__(self, tags=(), funcs=(), items=None):
                self.tags = set(tags)
                self.funcs = set(funcs)
                self.items = None if items is None else list(items)

        def _sv_union(*values):
            tags = set()
            funcs = set()
            items = []
            have_items = False
            for value in values:
                if value is None:
                    continue
                tags |= value.tags
                funcs |= value.funcs
                if value.items is not None:
                    have_items = True
                    items.extend(value.items)
            return _StaticValue(tags, funcs, items if have_items else None)

        def _sv_item(value, key=None):
            if value is None or value.items is None:
                return _StaticValue()
            selected = []
            for item_key, item_value in value.items:
                if key is None or item_key is None or item_key == key:
                    selected.append(item_value)
            return _sv_union(*selected)

        parent_nodes = {}
        function_nodes = {}
        class_nodes = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_nodes[id(child)] = parent
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_nodes[parent.name] = parent
            elif isinstance(parent, ast.ClassDef):
                class_nodes[parent.name] = parent

        function_envs = {}
        function_closures = {}
        function_return_cache = {}
        sensitive_function_nodes = set()
        global_bindings = {}
        class_attributes = {}
        instance_attributes = {}

        def _enclosing_function(expr):
            parent = parent_nodes.get(id(expr))
            while parent is not None:
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    return parent
                parent = parent_nodes.get(id(parent))
            return None

        def _enclosing_class(expr):
            parent = parent_nodes.get(id(expr))
            while parent is not None:
                if isinstance(parent, ast.ClassDef):
                    return parent
                parent = parent_nodes.get(id(parent))
            return None

        def _known_function_value(node):
            if isinstance(node, ast.Name) and node.id in function_nodes:
                return _StaticValue(funcs=(function_nodes[node.id],))
            return _StaticValue()

        def _static_items(expr, env, context, stack):
            if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
                return [(index, _abstract(value, env, context, stack))
                        for index, value in enumerate(expr.elts)]
            if isinstance(expr, ast.Dict):
                items = []
                for key, value in zip(expr.keys, expr.values):
                    item_key = None if key is None else _eval_str(key)
                    items.append((item_key, _abstract(value, env, context, stack)))
                return items
            if isinstance(expr, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
                value = _abstract(expr, env, context, stack)
                return value.items
            if isinstance(expr, ast.DictComp):
                value = _abstract(expr, env, context, stack)
                return value.items
            return None

        def _function_return(function, args=(), keywords=None, caller_env=None, stack=()):
            if id(function) in stack:
                return _StaticValue(tags=("unknown_owner",))
            keywords = keywords or {}
            cache_key = (id(function), tuple(id(argument) for argument in args),
                         tuple(sorted((name, id(value)) for name, value in keywords.items())))
            if cache_key is not None and cache_key in function_return_cache:
                return function_return_cache[cache_key]
            env = dict(global_bindings)
            env.update(function_closures.get(id(function), {}))
            parameters = (list(function.args.posonlyargs) + list(function.args.args)
                          + list(function.args.kwonlyargs))
            positional = list(args)
            defaults = ([None] * (len(function.args.posonlyargs)
                        + len(function.args.args) - len(function.args.defaults))
                        + list(function.args.defaults))
            for index, parameter in enumerate(parameters):
                if positional:
                    env[parameter.arg] = _abstract(positional.pop(0), caller_env or env,
                                                    function, stack)
                elif parameter.arg in keywords:
                    env[parameter.arg] = _abstract(keywords[parameter.arg], caller_env or env,
                                                    function, stack)
                else:
                    default = defaults[index] if index < len(defaults) else None
                    if default is not None:
                        env[parameter.arg] = _abstract(default, caller_env or env,
                                                        function, stack)
            for parameter, default in zip(function.args.kwonlyargs, function.args.kw_defaults):
                if parameter.arg in keywords:
                    env[parameter.arg] = _abstract(keywords[parameter.arg], caller_env or env,
                                                    function, stack)
                elif default is not None:
                    env[parameter.arg] = _abstract(default, caller_env or env,
                                                    function, stack)
            function_envs[id(function)] = env
            if isinstance(function, ast.Lambda):
                result = _abstract(function.body, env, function, stack + (id(function),))
                function_envs[id(function)] = env
                if cache_key is not None:
                    function_return_cache[cache_key] = result
                return result

            returns = []

            def bind(target, value):
                if isinstance(target, ast.Starred):
                    target = target.value
                if isinstance(target, ast.Name):
                    env[target.id] = value
                    return
                if isinstance(target, (ast.Tuple, ast.List)):
                    for index, child in enumerate(target.elts):
                        bind(child, _sv_item(value, index))
                    return
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    owner = target.value.id
                    owner_class = None
                    if owner == "self":
                        klass = _enclosing_class(function)
                        owner_class = None if klass is None else klass.name
                    if owner_class is not None:
                        class_attributes[(owner_class, target.attr)] = value
                    else:
                        instance_attributes[(owner, target.attr)] = value

            def visit_statements(statements):
                for statement in statements:
                    if isinstance(statement, ast.Return):
                        returns.append(_abstract(statement.value, env, function, stack))
                    elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        function_closures[id(statement)] = dict(env)
                        env[statement.name] = _StaticValue(funcs=(statement,))
                    elif isinstance(statement, ast.ClassDef):
                        class_nodes[statement.name] = statement
                        env[statement.name] = _StaticValue(tags=(f"class:{statement.name}",))
                    elif isinstance(statement, ast.Assign):
                        value = _abstract(statement.value, env, function, stack)
                        for target in statement.targets:
                            bind(target, value)
                    elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
                        bind(statement.target, _abstract(statement.value, env, function, stack))
                    elif isinstance(statement, ast.AugAssign):
                        bind(statement.target, _abstract(statement.value, env, function, stack))
                    elif isinstance(statement, ast.If):
                        before = dict(env)
                        visit_statements(statement.body)
                        body_env = dict(env)
                        env.clear(); env.update(before)
                        visit_statements(statement.orelse)
                        for name, value in body_env.items():
                            env[name] = _sv_union(env.get(name), value)
                    elif isinstance(statement, (ast.For, ast.AsyncFor)):
                        bind(statement.target, _sv_item(_abstract(statement.iter, env, function, stack)))
                        visit_statements(statement.body)
                        visit_statements(statement.orelse)
                    elif isinstance(statement, (ast.While, ast.With, ast.AsyncWith)):
                        visit_statements(statement.body)
                        if hasattr(statement, "orelse"):
                            visit_statements(statement.orelse)
                    elif isinstance(statement, ast.Try):
                        visit_statements(statement.body)
                        for handler in statement.handlers:
                            visit_statements(handler.body)
                        visit_statements(statement.orelse)
                        visit_statements(statement.finalbody)

            visit_statements(function.body)
            function_envs[id(function)] = env
            result = _sv_union(*returns)
            if cache_key is not None:
                function_return_cache[cache_key] = result
            return result

        def _abstract_uncached(expr, env=None, context=None, stack=()):
            if expr is None:
                return _StaticValue()
            if env is None:
                if context is None:
                    context = _enclosing_function(expr)
                env = function_envs.get(id(context), global_bindings) if context else global_bindings
            if isinstance(expr, ast.Name):
                if expr.id in env:
                    return env[expr.id]
                if expr.id in global_bindings:
                    return global_bindings[expr.id]
                if expr.id in function_nodes:
                    return _known_function_value(expr)
                if expr.id in class_nodes:
                    return _StaticValue(tags=(f"class:{expr.id}",))
                if expr.id in ctypes_aliases:
                    return _StaticValue(tags=("ctypes_module",))
                if expr.id in importlib_aliases:
                    return _StaticValue(tags=("importlib_module",))
                if expr.id in importlib_machinery_aliases:
                    return _StaticValue(tags=("machinery",))
                if expr.id in vars_aliases:
                    return _StaticValue(tags=("vars",))
                if expr.id in getattr_aliases:
                    return _StaticValue(tags=("getattr",))
                if expr.id in getattribute_aliases:
                    return _StaticValue(tags=("getattribute",))
                if expr.id in ctypes_getattribute_aliases:
                    return _StaticValue(tags=("ctypes_getattribute",))
                if expr.id in attrgetter_aliases:
                    return _StaticValue(tags=("attrgetter",))
                if expr.id in import_module_aliases:
                    return _StaticValue(tags=("import_module",))
                if expr.id in import_function_aliases:
                    return _StaticValue(tags=("import_function",))
                if expr.id in setattr_aliases:
                    return _StaticValue(tags=("setattr",))
                if expr.id in operator_aliases:
                    return _StaticValue(tags=("operator",))
                return _StaticValue(tags=("unknown_owner",))
            if isinstance(expr, ast.Constant):
                return _StaticValue()
            if isinstance(expr, ast.NamedExpr):
                value = _abstract(expr.value, env, context, stack)
                if isinstance(expr.target, ast.Name):
                    env[expr.target.id] = value
                return value
            if isinstance(expr, ast.Lambda):
                function_closures[id(expr)] = dict(env)
                return _StaticValue(funcs=(expr,))
            if isinstance(expr, ast.Attribute):
                base = _abstract(expr.value, env, context, stack)
                if "ctypes_module" in base.tags:
                    if expr.attr in _ALL_LOADER_TOKENS:
                        return _StaticValue(tags=("ctypes_loader",))
                    if expr.attr == "__dict__":
                        return _StaticValue(tags=("ctypes_reflection",))
                    if expr.attr == "__getattribute__":
                        return _StaticValue(tags=("ctypes_getattribute",))
                    return _StaticValue()
                if "importlib_module" in base.tags:
                    if expr.attr == "import_module":
                        return _StaticValue(tags=("import_module",))
                    if expr.attr == "machinery":
                        return _StaticValue(tags=("machinery",))
                if "machinery" in base.tags and expr.attr in _IMPORTLIB_LOADER_NAMES:
                    return _StaticValue(tags=("ctypes_loader",))
                if "operator" in base.tags and expr.attr == "attrgetter":
                    return _StaticValue(tags=("attrgetter",))
                if "unknown_owner" in base.tags and expr.attr in _ALL_LOADER_TOKENS:
                    return _StaticValue(tags=("unknown_loader",))
                for tag in base.tags:
                    if tag.startswith("class:"):
                        return class_attributes.get((tag[6:], expr.attr), _StaticValue())
                    if tag.startswith("instance:"):
                        owner = tag[9:]
                        value = class_attributes.get((owner, expr.attr))
                        if value is not None:
                            return value
                if isinstance(expr.value, ast.Name):
                    return instance_attributes.get((expr.value.id, expr.attr), _StaticValue())
                return _StaticValue()
            if isinstance(expr, ast.Subscript):
                value = _abstract(expr.value, env, context, stack)
                key = _eval_str(expr.slice)
                if isinstance(key, int):
                    return _sv_item(value, key)
                return _sv_item(value, key)
            if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
                return _StaticValue(items=_static_items(expr, env, context, stack))
            if isinstance(expr, ast.Dict):
                return _StaticValue(items=_static_items(expr, env, context, stack))
            if isinstance(expr, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                local = dict(env)
                for generator in expr.generators:
                    iterable = _abstract(generator.iter, local, context, stack)
                    item = _sv_item(iterable)
                    if isinstance(generator.target, ast.Name):
                        local[generator.target.id] = item
                    elif isinstance(generator.target, (ast.Tuple, ast.List)):
                        for index, target in enumerate(generator.target.elts):
                            if isinstance(target, ast.Name):
                                local[target.id] = _sv_item(item, index)
                if isinstance(expr, ast.DictComp):
                    value = _abstract(expr.value, local, context, stack)
                    key = _eval_str(expr.key)
                    return _StaticValue(tags=value.tags, funcs=value.funcs,
                                        items=[(key, value)])
                value = _abstract(expr.elt, local, context, stack)
                return _StaticValue(tags=value.tags, funcs=value.funcs,
                                    items=[(0, value)])
            if isinstance(expr, ast.IfExp):
                return _sv_union(_abstract(expr.body, env, context, stack),
                                 _abstract(expr.orelse, env, context, stack))
            if isinstance(expr, ast.BoolOp):
                return _sv_union(*(_abstract(value, env, context, stack)
                                   for value in expr.values))
            if isinstance(expr, ast.Call):
                function = _abstract(expr.func, env, context, stack)
                eligible_functions = [value for value in function.funcs
                                      if value in sensitive_function_nodes
                                      or isinstance(value, ast.Lambda)]
                if eligible_functions:
                    return _sv_union(*(_function_return(value, expr.args,
                                                        {keyword.arg: keyword.value for keyword in expr.keywords
                                                         if keyword.arg is not None},
                                                        env, stack + (id(value),))
                                      for value in eligible_functions))
                if function.funcs:
                    return _StaticValue(tags=("unknown_owner",))
                if "ctypes_loader" in function.tags or "unknown_loader" in function.tags:
                    return _StaticValue()
                if "getattr" in function.tags and len(expr.args) >= 2:
                    owner = _abstract(expr.args[0], env, context, stack)
                    attr = _eval_str(expr.args[1])
                    if "ctypes_module" in owner.tags and attr in _ALL_LOADER_TOKENS:
                        return _StaticValue(tags=("ctypes_loader",))
                    if "machinery" in owner.tags and attr in _IMPORTLIB_LOADER_NAMES:
                        return _StaticValue(tags=("ctypes_loader",))
                    return _StaticValue(tags=("unknown_owner",)) if attr is None else _StaticValue()
                if "ctypes_getattribute" in function.tags and expr.args:
                    attr = _eval_str(expr.args[-1])
                    if attr in _ALL_LOADER_TOKENS:
                        return _StaticValue(tags=("ctypes_loader",))
                if "import_function" in function.tags and expr.args:
                    module = _eval_str(expr.args[0])
                    if module == "ctypes":
                        return _StaticValue(tags=("ctypes_module",))
                    if module == "importlib":
                        return _StaticValue(tags=("importlib_module",))
                if "import_module" in function.tags and expr.args:
                    module = _eval_str(expr.args[0])
                    if module == "importlib.machinery":
                        return _StaticValue(tags=("machinery",))
                if "attrgetter" in function.tags:
                    attr = _eval_str(expr.args[0]) if expr.args else None
                    return _StaticValue(tags=("attrgetter_sensitive" if attr in _ALL_LOADER_TOKENS or attr is None
                                               else "attrgetter_safe",))
                if "setattr" in function.tags and len(expr.args) >= 3:
                    owner = expr.args[0]
                    attr = _eval_str(expr.args[1])
                    value = _abstract(expr.args[2], env, context, stack)
                    if isinstance(owner, ast.Name) and attr is not None:
                        if owner.id in class_nodes:
                            class_attributes[(owner.id, attr)] = value
                        else:
                            instance_attributes[(owner.id, attr)] = value
                    return _StaticValue()
                for tag in function.tags:
                    if tag.startswith("class:"):
                        return _StaticValue(tags=(f"instance:{tag[6:]}",))
                return _StaticValue(tags=("unknown_owner",))
            return _StaticValue()

        abstract_cache = {}

        def _abstract(expr, env=None, context=None, stack=()):
            # Calls made by the AST checks repeatedly inspect the same node.
            # Cache only context-free lookups after the initial fixpoint; the
            # function evaluator still passes explicit environments and keeps
            # its call-sensitive behavior.
            if env is None and context is None and not stack:
                key = id(expr)
                if key in abstract_cache:
                    return abstract_cache[key]
                value = _abstract_uncached(expr, None, None, ())
                abstract_cache[key] = value
                return value
            return _abstract_uncached(expr, env, context, stack)

        # Seed the import identities before evaluating aliases and receivers.
        for definition in ast.walk(tree):
            if isinstance(definition, ast.Import):
                for alias in definition.names:
                    name = alias.asname or alias.name
                    if alias.name in ("ctypes", "_ctypes"):
                        ctypes_aliases.add(name)
                    elif alias.name == "importlib":
                        importlib_aliases.add(name)
                    elif alias.name == "importlib.machinery":
                        importlib_machinery_aliases.add(alias.asname or "machinery")
                    elif alias.name == "operator":
                        operator_aliases.add(name)
            elif isinstance(definition, ast.ImportFrom):
                mod = definition.module or ""
                for alias in definition.names:
                    name = alias.asname or alias.name
                    if mod in ("ctypes", "_ctypes") and alias.name == "ctypes":
                        ctypes_aliases.add(name)
                    elif mod == "builtins" and alias.name == "vars":
                        vars_aliases.add(name)
                    elif mod == "builtins" and alias.name == "getattr":
                        getattr_aliases.add(name)
                    elif mod == "builtins" and alias.name == "__import__":
                        import_function_aliases.add(name)
                    elif mod == "builtins" and alias.name == "setattr":
                        setattr_aliases.add(name)
                    elif mod == "operator" and alias.name == "attrgetter":
                        attrgetter_aliases.add(name)
                    elif mod == "importlib" and alias.name == "import_module":
                        import_module_aliases.add(name)
                    elif mod == "importlib" and alias.name == "machinery":
                        importlib_machinery_aliases.add(name)

        # The project uses ctypes only via direct attribute access.  Refuse
        # first-class module escapes instead of claiming complete Python object
        # flow analysis (properties and aliased mutable receivers are open-ended).
        # A simple local name alias remains supported for ordinary ctypes types.
        module_names = set(ctypes_aliases)
        changed = True
        while changed:
            changed = False
            for assignment in ast.walk(tree):
                if (isinstance(assignment, ast.Assign)
                        and isinstance(assignment.value, ast.Name)
                        and assignment.value.id in module_names):
                    for target in assignment.targets:
                        if isinstance(target, ast.Name) and target.id not in module_names:
                            module_names.add(target.id)
                            changed = True
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                    and node.id in module_names):
                continue
            parent = parent_nodes.get(id(node))
            if isinstance(parent, ast.Attribute) and parent.value is node:
                continue
            if (isinstance(parent, ast.Assign) and parent.value is node
                    and all(isinstance(target, ast.Name) for target in parent.targets)):
                continue
            _fail(report, f"unsupported first-class ctypes module escape at {relative}:{node.lineno}")

        # Only analyze user functions whose syntax can carry a native or
        # reflection value.  Other calls become an opaque owner at the use
        # site, which is both fail-closed for ``unknown().CDLL`` and keeps the
        # repository-wide audit linear in the size of the AST.
        for function in function_nodes.values():
            for node in ast.walk(function):
                if isinstance(node, ast.Attribute) and node.attr in (
                        _ALL_LOADER_TOKENS | _IMPORTLIB_LOADER_NAMES
                        | {"__dict__", "__getattribute__"}):
                    sensitive_function_nodes.add(function)
                    break
                if isinstance(node, ast.Name) and node.id in ctypes_aliases:
                    parent = parent_nodes.get(id(node))
                    if not (isinstance(parent, ast.Attribute)
                            and parent.value is node
                            and parent.attr not in (_ALL_LOADER_TOKENS
                                                    | _FORBIDDEN_CPYTHON_ATTRS
                                                    | {"__dict__", "__getattribute__"})):
                        sensitive_function_nodes.add(function)
                        break

        # Resolve module-level names and ordinary class/instance fields to a
        # fixpoint.  This is intentionally syntax-only and never imports or
        # invokes the audited source.
        for _ in range(8):
            changed = False
            for definition in ast.walk(tree):
                if isinstance(definition, ast.ClassDef):
                    for statement in definition.body:
                        value_node = (statement.value if isinstance(statement, (ast.Assign, ast.AnnAssign))
                                      else None)
                        if value_node is None:
                            continue
                        targets = (statement.targets if isinstance(statement, ast.Assign)
                                   else [statement.target])
                        value = _abstract(value_node, global_bindings, definition, ())
                        for target in targets:
                            if isinstance(target, ast.Name):
                                key = (definition.name, target.id)
                                merged = _sv_union(class_attributes.get(key), value)
                                if key not in class_attributes or (merged.tags != class_attributes[key].tags):
                                    class_attributes[key] = merged
                                    changed = True
                if isinstance(definition, ast.Assign):
                    function = _enclosing_function(definition)
                    owner = _enclosing_class(definition)
                    value = _abstract(definition.value, global_bindings, function, ())
                    for target in definition.targets:
                        if function is None and owner is None and isinstance(target, ast.Name):
                            previous = global_bindings.get(target.id)
                            merged = _sv_union(previous, value)
                            if previous is None or merged.tags != previous.tags or merged.funcs != previous.funcs:
                                global_bindings[target.id] = merged
                                changed = True
                        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                            key = (target.value.id, target.attr)
                            previous = instance_attributes.get(key)
                            merged = _sv_union(previous, value)
                            if previous is None or merged.tags != previous.tags:
                                instance_attributes[key] = merged
                                changed = True
                            if target.value.id in class_nodes:
                                class_key = (target.value.id, target.attr)
                                previous = class_attributes.get(class_key)
                                merged = _sv_union(previous, value)
                                if previous is None or merged.tags != previous.tags:
                                    class_attributes[class_key] = merged
                                    changed = True
                elif isinstance(definition, ast.AnnAssign) and definition.value is not None:
                    function = _enclosing_function(definition)
                    owner = _enclosing_class(definition)
                    value = _abstract(definition.value, global_bindings, function, ())
                    if function is None and owner is None and isinstance(definition.target, ast.Name):
                        previous = global_bindings.get(definition.target.id)
                        merged = _sv_union(previous, value)
                        if previous is None or merged.tags != previous.tags:
                            global_bindings[definition.target.id] = merged
                            changed = True
                    elif isinstance(definition.target, ast.Attribute) and isinstance(definition.target.value, ast.Name):
                        instance_attributes[(definition.target.value.id, definition.target.attr)] = value
                        if definition.target.value.id in class_nodes:
                            class_attributes[(definition.target.value.id, definition.target.attr)] = value
            if not changed:
                break
        for function in sensitive_function_nodes:
            _function_return(function)
        for definition in ast.walk(tree):
            if isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)):
                arguments = (list(definition.args.posonlyargs)
                             + list(definition.args.args)
                             + list(definition.args.kwonlyargs))
                function_parameter_names.update(argument.arg for argument in arguments)
        # Track parameters copied to local names.  Unknown callables carrying
        # a native/reflection value must fail closed at their invocation.
        changed = True
        while changed:
            changed = False
            for assignment in ast.walk(tree):
                if not isinstance(assignment, ast.Assign) or not isinstance(assignment.value, ast.Name):
                    continue
                if assignment.value.id not in function_parameter_names:
                    continue
                for target in assignment.targets:
                    if isinstance(target, ast.Name) and target.id not in function_parameter_names:
                        function_parameter_names.add(target.id)
                        changed = True
        allowed_loader_attrs = (
            _model_allowed_loader_call_ids(tree)
            if relative == "Simulator/wksim_core/model.py" else set())

        def _resolved_container(expr, seen=()):
            if not isinstance(expr, ast.Name) or expr.id not in container_bindings:
                return expr
            if expr.id in seen:
                return expr
            return _resolved_container(container_bindings[expr.id], seen + (expr.id,))

        def _container_values(expr):
            """Return values selected by a statically known container access."""
            if not isinstance(expr, ast.Subscript):
                return None
            base = _resolved_container(expr.value)
            key = _eval_str(expr.slice)
            if isinstance(base, ast.Dict):
                values = []
                for dict_key, value in zip(base.keys, base.values):
                    if dict_key is None:
                        values.append(value)
                    elif key is None or _eval_str(dict_key) == key:
                        values.append(value)
                return values
            if isinstance(base, (ast.List, ast.Tuple)):
                if isinstance(key, int) and -len(base.elts) <= key < len(base.elts):
                    return [base.elts[key]]
                if key is None:
                    return list(base.elts)
            return None

        def is_builtins_expr(expr):
            if isinstance(expr, ast.Name):
                return expr.id == "__builtins__"
            if (isinstance(expr, ast.Subscript)
                    and isinstance(expr.value, ast.Call)
                    and isinstance(expr.value.func, ast.Name)
                    and expr.value.func.id in {"globals", "locals"}):
                return _eval_str(expr.slice) == "__builtins__"
            if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute)
                    and expr.func.attr == "get" and expr.args):
                return (_eval_str(expr.args[0]) == "__builtins__"
                        and isinstance(expr.func.value, ast.Call)
                        and isinstance(expr.func.value.func, ast.Name)
                        and expr.func.value.func.id in {"globals", "locals"})
            return False

        def _builtin_lookup(expr, names):
            if isinstance(expr, ast.Subscript):
                key = _eval_str(expr.slice)
                if key in names and (is_builtins_expr(expr.value) or is_vars_call(expr.value)):
                    return True
            if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute)
                    and expr.func.attr == "get" and expr.args):
                key = _eval_str(expr.args[0])
                if key in names and is_builtins_expr(expr.func.value):
                    return True
            return False

        def _container_alias_matches(expr, matcher):
            values = _container_values(expr)
            return bool(values) and any(matcher(value) for value in values)

        def is_vars_expr(expr):
            if isinstance(expr, ast.Name) and expr.id in vars_aliases:
                return True
            return _container_alias_matches(expr,
                                            lambda value: isinstance(value, ast.Name)
                                            and value.id in vars_aliases)

        def is_vars_call(node):
            return (isinstance(node, ast.Call) and is_vars_expr(node.func)
                    and len(node.args) >= 1)

        def is_ctypes_expr(expr):
            if "ctypes_module" in _abstract(expr).tags:
                return True
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
            values = _container_values(expr)
            if values is not None:
                return any(is_ctypes_expr(value) for value in values)
            return False

        def is_importlib_module_expr(expr):
            if "importlib_module" in _abstract(expr).tags:
                return True
            if isinstance(expr, ast.Name):
                direct = expr.id in importlib_aliases
            elif isinstance(expr, ast.Attribute):
                direct = is_importlib_module_expr(expr.value)
            else:
                direct = False
            return direct or _container_alias_matches(expr, is_importlib_module_expr)

        def is_import_module_expr(expr):
            if "import_module" in _abstract(expr).tags:
                return True
            if isinstance(expr, ast.Name):
                direct = expr.id in import_module_aliases
            else:
                direct = (isinstance(expr, ast.Attribute) and expr.attr == "import_module"
                          and is_importlib_module_expr(expr.value))
            return direct or _container_alias_matches(expr, is_import_module_expr)

        def is_import_function_expr(expr):
            if "import_function" in _abstract(expr).tags:
                return True
            if isinstance(expr, ast.Name) and expr.id in import_function_aliases:
                return True
            return _builtin_lookup(expr, {"__import__"}) \
                or _container_alias_matches(expr, is_import_function_expr)

        def is_trusted_import_module_call(node):
            if not isinstance(node, ast.Call):
                return False
            return is_import_module_expr(node.func)

        def is_machinery_expr(expr):
            if "machinery" in _abstract(expr).tags:
                return True
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
            return _container_alias_matches(expr, is_machinery_expr)

        def is_getattr_expr(expr):
            if "getattr" in _abstract(expr).tags:
                return True
            if isinstance(expr, ast.Name) and expr.id in getattr_aliases:
                return True
            return _builtin_lookup(expr, {"getattr"}) \
                or _container_alias_matches(expr, is_getattr_expr)

        def is_attrgetter_expr(expr):
            if "attrgetter" in _abstract(expr).tags:
                return True
            if isinstance(expr, ast.Name):
                direct = expr.id in attrgetter_aliases
            elif isinstance(expr, ast.Attribute):
                direct = expr.attr == "attrgetter" and is_operator_expr(expr.value)
            elif isinstance(expr, ast.Subscript):
                direct = (_eval_str(expr.slice) == "attrgetter"
                          and (is_operator_expr(expr.value)
                               or (isinstance(expr.value, ast.Attribute)
                                   and expr.value.attr == "__dict__"
                                   and is_operator_expr(expr.value.value))
                               or (isinstance(expr.value, ast.Call)
                                   and is_vars_call(expr.value)
                                   and expr.value.args
                                   and is_operator_expr(expr.value.args[0]))))
            elif isinstance(expr, ast.Call) and is_getattr_expr(expr.func) and len(expr.args) >= 2:
                direct = _eval_str(expr.args[1]) == "attrgetter"
            else:
                direct = False
            return direct or _container_alias_matches(expr, is_attrgetter_expr)

        def is_operator_expr(expr):
            if "operator" in _abstract(expr).tags:
                return True
            return ((isinstance(expr, ast.Name) and expr.id in operator_aliases)
                    or _container_alias_matches(expr, is_operator_expr))

        def is_getattribute_expr(expr):
            if "getattribute" in _abstract(expr).tags:
                return True
            if isinstance(expr, ast.Name):
                direct = expr.id in getattribute_aliases
            else:
                direct = isinstance(expr, ast.Attribute) and expr.attr == "__getattribute__"
            return direct or _builtin_lookup(expr, {"__getattribute__"}) \
                or _container_alias_matches(expr, is_getattribute_expr)

        def is_ctypes_getattribute_expr(expr):
            if "ctypes_getattribute" in _abstract(expr).tags:
                return True
            if isinstance(expr, ast.Name):
                direct = expr.id in ctypes_getattribute_aliases
            else:
                direct = (isinstance(expr, ast.Attribute) and expr.attr == "__getattribute__"
                          and is_ctypes_expr(expr.value))
            return direct or _container_alias_matches(expr, is_ctypes_getattribute_expr)

        def is_ctypes_sensitive_expr(expr):
            if _abstract(expr).tags & {"ctypes_module", "ctypes_loader", "ctypes_reflection",
                                       "ctypes_getattribute"}:
                return True
            if isinstance(expr, ast.Name):
                return expr.id in ctypes_aliases
            if isinstance(expr, ast.Attribute):
                if expr.attr not in (_ALL_LOADER_TOKENS | _FORBIDDEN_CPYTHON_ATTRS
                                     | {"__dict__"}):
                    return False
                return is_ctypes_sensitive_expr(expr.value)
            if isinstance(expr, ast.Call) and is_vars_call(expr) and expr.args:
                return is_ctypes_sensitive_expr(expr.args[0])
            values = _container_values(expr)
            return values is not None and any(is_ctypes_sensitive_expr(value) for value in values)

        def is_sensitive_value(expr):
            static_tags = _abstract(expr).tags
            return (bool(static_tags & {"ctypes_module", "ctypes_loader", "ctypes_reflection",
                                        "ctypes_getattribute", "unknown_loader",
                                        "attrgetter_sensitive"})
                    or is_ctypes_sensitive_expr(expr) or is_builtins_expr(expr)
                    or is_vars_expr(expr) or is_getattr_expr(expr)
                    or is_getattribute_expr(expr) or is_ctypes_getattribute_expr(expr)
                    or is_import_function_expr(expr) or is_import_module_expr(expr)
                    or is_attrgetter_expr(expr) or is_machinery_expr(expr)
                    or is_operator_expr(expr))

        def is_loader_expr(expr):
            """Recognize a native loader owner, including opaque owners."""
            tags = _abstract(expr).tags
            return (is_ctypes_expr(expr) or "ctypes_loader" in tags
                    or "unknown_loader" in tags or "unknown_owner" in tags)

        def contains_sensitive_value(expr):
            if is_sensitive_value(expr):
                return True
            if "unknown_loader" in _abstract(expr).tags:
                return True
            # A safe ctypes constant such as ctypes.c_double must not inherit
            # the sensitivity of its module owner.
            if isinstance(expr, ast.Attribute) and is_ctypes_expr(expr.value):
                return False
            if isinstance(expr, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
                if isinstance(expr, ast.Dict):
                    values = list(expr.values) + [key for key in expr.keys if key is not None]
                else:
                    values = list(expr.elts)
                return any(contains_sensitive_value(value) for value in values)
            if isinstance(expr, ast.Call):
                if is_attrgetter_expr(expr.func):
                    return True
                if is_getattr_expr(expr.func) and expr.args:
                    attr = _eval_str(expr.args[1]) if len(expr.args) >= 2 else None
                    return (is_ctypes_expr(expr.args[0])
                            or is_machinery_expr(expr.args[0])
                            or attr in _ALL_LOADER_TOKENS
                            or attr in _IMPORTLIB_LOADER_NAMES)
                if is_import_function_expr(expr.func):
                    module = _eval_str(expr.args[0]) if expr.args else None
                    return module is None or "ctypes" in module or module == "importlib.machinery"
                if is_import_module_expr(expr.func):
                    module = _eval_str(expr.args[0]) if expr.args else None
                    return module is None or "ctypes" in module or module == "importlib.machinery"
                if is_vars_expr(expr.func) and expr.args:
                    return is_sensitive_value(expr.args[0])
                return (any(contains_sensitive_value(argument) for argument in expr.args)
                        or any(contains_sensitive_value(keyword.value) for keyword in expr.keywords))
            return any(contains_sensitive_value(child) for child in ast.iter_child_nodes(expr))

        def contains_sensitive_literal(expr):
            return any(isinstance(inner, ast.Constant) and inner.value in (
                set(_ALL_LOADER_TOKENS) | set(_IMPORTLIB_LOADER_NAMES)
                | {"ctypes", "importlib.machinery", "__builtins__"})
                       for inner in ast.walk(expr))

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
                      is_vars_expr)
            bind_names(target, value, getattr_aliases,
                      is_getattr_expr)
            bind_names(target, value, attrgetter_aliases, is_attrgetter_expr)
            bind_names(target, value, import_module_aliases,
                      is_import_module_expr)
            bind_names(target, value, import_function_aliases,
                      is_import_function_expr)
            bind_names(target, value, getattribute_aliases, is_getattribute_expr)
            bind_names(target, value, ctypes_getattribute_aliases, is_ctypes_getattribute_expr)
            bind_names(target, value, operator_aliases,
                      lambda expr: ((isinstance(expr, ast.Name) and expr.id in operator_aliases)
                                    or _container_alias_matches(expr, is_operator_expr)))

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "__builtins__":
                _fail(report, f"forbidden __builtins__ reflection surface at {relative}:{node.lineno}")

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
                if is_import_function_expr(node.func):
                    module_name = _eval_str(node.args[0]) if node.args else None
                    if module_name is None:
                        _fail(report, f"forbidden dynamic __import__ module name at {relative}:{node.lineno}")
                    elif "ctypes" in module_name:
                        _fail(report, f"forbidden dynamic __import__ of ctypes at {relative}:{node.lineno}")
                elif is_import_module_expr(node.func):
                    module_name = _eval_str(node.args[0]) if node.args else None
                    if module_name is None:
                        _fail(report, f"forbidden dynamic importlib module name at {relative}:{node.lineno}")
                    elif "ctypes" in module_name:
                        _fail(report, f"forbidden dynamic importlib of ctypes at {relative}:{node.lineno}")
                    if is_trusted_import_module_call(node) and module_name == "importlib.machinery":
                        _fail(report, f"forbidden dynamic importlib loader module at {relative}:{node.lineno}")

                if isinstance(node.func, ast.Name) and node.func.id in {"globals", "locals"}:
                    _fail(report, f"forbidden global namespace reflection at {relative}:{node.lineno}")

            # 3. Dynamic execution calls: eval, exec, compile.
            if isinstance(node, ast.Call):
                call_name = None
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile"}:
                    call_name = node.func.id
                elif _builtin_lookup(node.func, {"eval", "exec", "compile"}):
                    call_name = _eval_str(node.func.slice) if isinstance(node.func, ast.Subscript) else "builtin"
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

            # 3b. Do not allow native/reflection values to cross an opaque
            # callable or be hidden in a container.  The audit does not run
            # those callables, so this conservative boundary is the safe
            # substitute for interprocedural execution.
            if isinstance(node, (ast.Dict, ast.List, ast.Tuple, ast.Set)) \
                    and contains_sensitive_value(node):
                _fail(report, f"forbidden sensitive value carried through container at "
                              f"{relative}:{node.lineno}")
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Subscript)
                                                    for target in node.targets) \
                    and contains_sensitive_value(node.value):
                _fail(report, f"forbidden sensitive value stored in container at "
                              f"{relative}:{node.lineno}")
            if isinstance(node, ast.Call):
                arguments = list(node.args) + [keyword.value for keyword in node.keywords]
                if any(is_sensitive_value(argument) for argument in arguments):
                    _fail(report, f"forbidden sensitive value passed through callable at "
                                  f"{relative}:{node.lineno}")
                if (isinstance(node.func, ast.Name)
                        and node.func.id in function_parameter_names
                        and any(contains_sensitive_value(argument) or contains_sensitive_literal(argument)
                                for argument in arguments)):
                    _fail(report, f"forbidden sensitive value passed to callable parameter at "
                                  f"{relative}:{node.lineno}")

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
                    and is_loader_expr(node.value) and id(node) not in allowed_loader_attrs):
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
                if node.attr in _LOADER_ATTRS and is_loader_expr(node.value):
                    _fail(report, f"forbidden ctypes loader module access ({node.attr}) at {relative}:{node.lineno}")
                elif ((isinstance(node.value, ast.Attribute) and node.value.attr in _LOADER_ATTRS
                       and is_loader_expr(node.value.value))
                      or (isinstance(node.value, ast.Name) and node.value.id in _LOADER_ATTRS
                          and node.value.id in aliases)):
                    _fail(report, f"forbidden ctypes loader attribute access ({node.attr}) at {relative}:{node.lineno}")
                elif node.attr in _FORBIDDEN_CPYTHON_ATTRS and is_ctypes_expr(node.value):
                    _fail(report, f"forbidden pre-bound interpreter library handle ({node.attr}) at {relative}:{node.lineno}")
                elif node.attr in _IMPORTLIB_LOADER_NAMES and is_machinery_expr(node.value):
                    _fail(report, f"forbidden native/bytecode loader access ({node.attr}) at {relative}:{node.lineno}")

            # 8. getattr loader calls, including returned importlib machinery modules.
            if isinstance(node, ast.Call) and is_getattr_expr(node.func):
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
                    if isinstance(target, ast.Name):
                        container_bindings[target.id] = rhs
                    bind_aliases(target, rhs)
                is_loader_alias = (
                    isinstance(rhs, ast.Attribute) and rhs.attr in _ALL_LOADER_TOKENS
                    and is_ctypes_expr(rhs.value))
                if isinstance(rhs, ast.Name) and rhs.id in aliases:
                    is_loader_alias = True
                elif isinstance(rhs, ast.Call) and is_getattr_expr(rhs.func):
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
                if isinstance(node.target, ast.Name):
                    container_bindings[node.target.id] = node.value
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
                    and is_loader_expr(func.value)) or (
                        isinstance(func, ast.Name) and func.id in aliases) or (
                        bool(_abstract(func).tags & {"ctypes_loader", "unknown_loader"}))
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
