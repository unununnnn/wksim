"""Small owner of the namespace-bound kernel PID probe ABI.

The native implementation is deliberately kept in ``kernel_pid_probe_native.c``.
This module owns only compilation, descriptor provenance and the narrow ctypes
boundary used by the scheduler and collector.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from Simulator.wksim_runtime.evidence import host_boot_id, json_identity


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "kernel_pid_probe_native.c"
MANIFEST_SCHEMA = "wksim.kernel-pid-probe.v1"
NAMESPACE_PATH = "/proc/self/ns/pid"
DEFAULT_MAX_ENTRIES = 4096
VERIFIER_BYTES = 65536
UINT32_MAX = (1 << 32) - 1
BPF_MAP_TYPE_HASH = 1
MIN_MAP_ENTRIES = 2
MAX_MAP_ENTRIES = 16384
MAP_INFO_FIELDS = ("map_id", "map_type", "key_size", "value_size", "max_entries")
MANIFEST_FIELDS = {
    "schema", "run_id", "boot_id", "creator", "source_path", "source_sha256",
    "library_path", "library_sha256", "compiler", "compiler_argv", "verifier",
    "namespace", "map_info", "prog_id", "prog_tag", "link_type", "link_tp_name",
}


class KernelPidProbeError(RuntimeError):
    """Raised when probe provenance or an ABI descriptor cannot be proven."""


class _PidRecord(ctypes.Structure):
    _fields_ = [
        ("kernel_ids", ctypes.c_uint64),
        ("local_tid", ctypes.c_uint32),
        ("local_tgid", ctypes.c_uint32),
        ("observed_boot_ns", ctypes.c_uint64),
        ("comm", ctypes.c_char * 16),
    ]


if ctypes.sizeof(_PidRecord) != 40:  # pragma: no cover - ABI guard
    raise RuntimeError("kernel PID probe record ABI is not 40 bytes")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strict_json(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON object, rejecting duplicates and non-finite values."""

    raw = path.read_bytes()

    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise KernelPidProbeError(f"duplicate manifest key: {key}")
            value[key] = item
        return value

    def reject_constant(value):
        raise KernelPidProbeError(f"non-finite JSON value: {value}")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                           parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KernelPidProbeError("manifest is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise KernelPidProbeError("manifest root must be an object")
    return value


def _require_int(value: Any, label: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise KernelPidProbeError(f"{label} is invalid")
    return value


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise KernelPidProbeError(f"{label} is invalid")
    return value


def _require_identity(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise KernelPidProbeError(f"{label} is invalid")
    _require_int(value.get("pid"), f"{label}.pid", minimum=1)
    _require_int(value.get("start_ticks"), f"{label}.start_ticks", minimum=1)
    _require_int(value.get("pgid"), f"{label}.pgid", minimum=1)
    argv = value.get("argv")
    if (not isinstance(argv, list) or not argv
            or any(not isinstance(item, str) for item in argv)):
        raise KernelPidProbeError(f"{label}.argv is invalid")
    return value


def _namespace_proof() -> dict[str, Any]:
    try:
        stat = os.stat(NAMESPACE_PATH)
    except OSError as error:
        raise KernelPidProbeError("PID namespace proof is unavailable") from error
    return {"path": NAMESPACE_PATH, "dev": int(stat.st_dev), "ino": int(stat.st_ino)}


def _validate_namespace(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"path", "dev", "ino"}:
        raise KernelPidProbeError("manifest namespace proof is invalid")
    if value.get("path") != NAMESPACE_PATH:
        raise KernelPidProbeError("manifest namespace path is invalid")
    _require_int(value.get("dev"), "manifest namespace dev", minimum=1)
    _require_int(value.get("ino"), "manifest namespace ino", minimum=1)
    current = _namespace_proof()
    if (value["dev"], value["ino"]) != (current["dev"], current["ino"]):
        raise KernelPidProbeError("PID namespace proof differs")
    return value


def _parse_fdinfo(fd: int) -> dict[str, int | str]:
    """Read fdinfo fields without inventing absent numeric or text values."""

    if type(fd) is not int or fd < 0:
        raise KernelPidProbeError("descriptor is invalid")
    try:
        os.fstat(fd)
        raw = Path(f"/proc/self/fdinfo/{fd}").read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise KernelPidProbeError(f"fdinfo for {fd} is unavailable") from error
    fields: dict[str, int | str] = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        value = value.strip()
        fields[key.strip()] = int(value, 10) if re.fullmatch(r"[0-9]+", value) else value
    return fields


def _require_fdinfo(fd: int, fields: tuple[str, ...], label: str) -> dict[str, int | str]:
    info = _parse_fdinfo(fd)
    missing = [field for field in fields if field not in info]
    if missing:
        raise KernelPidProbeError(f"{label} fdinfo missing: {','.join(missing)}")
    return info


def _read_fdinfo_text(fd: int, fields: tuple[str, ...]) -> dict[str, str]:
    info = _parse_fdinfo(fd)
    missing = [field for field in fields if field not in info]
    if missing:
        raise KernelPidProbeError(f"fdinfo missing: {','.join(missing)}")
    result = {field: info[field] for field in fields}
    if any(not isinstance(value, str) for value in result.values()):
        raise KernelPidProbeError("fdinfo textual field is not textual")
    return result


def _configure_library(library: ctypes.CDLL) -> ctypes.CDLL:
    try:
        open_fn = library.wk_pid_probe_open
        lookup_fn = library.wk_pid_probe_lookup
        info_fn = library.wk_pid_probe_info
    except AttributeError as error:
        raise KernelPidProbeError("kernel PID probe ABI is incomplete") from error
    open_fn.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint32,
                        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_char),
                        ctypes.c_uint32]
    open_fn.restype = ctypes.c_int
    lookup_fn.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.POINTER(_PidRecord)]
    lookup_fn.restype = ctypes.c_int
    info_fn.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint32)]
    info_fn.restype = ctypes.c_int
    return library


def _load_library(path: Path) -> ctypes.CDLL:
    try:
        return _configure_library(ctypes.CDLL(str(path), use_errno=True))
    except OSError as error:
        raise KernelPidProbeError(f"kernel PID probe library cannot load: {path}") from error


def _call_error(rc: int, label: str) -> None:
    if type(rc) is not int:
        rc = int(rc)
    if rc < 0:
        number = -rc
        raise OSError(number, f"{label} failed: {os.strerror(number)}")
    if rc != 0:
        raise KernelPidProbeError(f"{label} returned unexpected status {rc}")


def _map_info(library: ctypes.CDLL, map_fd: int) -> dict[str, int]:
    values = (ctypes.c_uint32 * 5)()
    rc = library.wk_pid_probe_info(map_fd, values)
    _call_error(rc, "wk_pid_probe_info")
    return {name: int(values[index]) for index, name in enumerate(MAP_INFO_FIELDS)}


def _validate_map_info(value: Any, *, require_capacity: bool = True) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(MAP_INFO_FIELDS):
        raise KernelPidProbeError("map_info is invalid")
    info = {name: _require_int(value.get(name), f"map_info.{name}", minimum=0)
            for name in MAP_INFO_FIELDS}
    if (info["map_id"] <= 0 or info["map_type"] != BPF_MAP_TYPE_HASH
            or info["key_size"] != 4 \
            or info["value_size"] != 40):
        raise KernelPidProbeError("map_info ABI fields are invalid")
    if require_capacity and not MIN_MAP_ENTRIES <= info["max_entries"] <= MAX_MAP_ENTRIES:
        raise KernelPidProbeError("map_info.max_entries is outside the C ABI bounds")
    if not require_capacity and info["max_entries"] < MIN_MAP_ENTRIES:
        raise KernelPidProbeError("map_info.max_entries must reserve tid 0")
    return info


def _map_info_matches_fdinfo(map_info: dict[str, int], fdinfo: dict[str, int]) -> None:
    for field in MAP_INFO_FIELDS:
        if fdinfo.get(field) != map_info[field]:
            raise KernelPidProbeError(f"map fdinfo {field} differs")


def _validate_link_fdinfo(prog_info: dict[str, int | str],
                          link_info: dict[str, int | str],
                          link_text: dict[str, str]) -> None:
    """Validate the complete program/link identity exposed by fdinfo."""
    _require_int(prog_info.get("prog_id"), "program fdinfo prog_id", minimum=1)
    _require_int(link_info.get("link_id"), "link fdinfo link_id", minimum=1)
    _require_int(link_info.get("prog_id"), "link fdinfo prog_id", minimum=1)
    for value, label in ((prog_info.get("prog_tag"), "program fdinfo prog_tag"),
                         (link_info.get("prog_tag"), "link fdinfo prog_tag")):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{16}", value) is None:
            raise KernelPidProbeError(f"{label} is invalid")
    if (prog_info["prog_id"] != link_info["prog_id"]
            or prog_info["prog_tag"] != link_info["prog_tag"]):
        raise KernelPidProbeError("BPF link is bound to another program")
    if (link_info.get("link_type") != link_text.get("link_type")
            or link_info.get("tp_name") != link_text.get("tp_name")):
        raise KernelPidProbeError("BPF link fdinfo identity is inconsistent")
    if link_text != {"link_type": "raw_tracepoint", "tp_name": "sched_switch"}:
        raise KernelPidProbeError("BPF link target is not sched_switch")


def _close_descriptor(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError as error:
        if error.errno != errno.EBADF:
            raise


class KernelPidProbe:
    """Owned map/program/link descriptors and the stable record ABI."""

    def __init__(self, *, manifest_path: Path, manifest: dict[str, Any],
                 library: ctypes.CDLL, map_fd: int, link_fd: int,
                 prog_fd: int | None = None):
        self.manifest_path = Path(manifest_path)
        self.manifest = manifest
        self._library = library
        self._map_fd = map_fd
        self._link_fd = link_fd
        self._prog_fd = prog_fd
        self.sampling_detached = False

    @property
    def map_fd(self) -> int | None:
        return self._map_fd

    @property
    def link_fd(self) -> int | None:
        return self._link_fd

    @property
    def prog_fd(self) -> int | None:
        return self._prog_fd

    def inherited_fds(self) -> tuple[int, int]:
        if self._map_fd is None or self._link_fd is None:
            raise KernelPidProbeError("probe descriptors were already released")
        return self._map_fd, self._link_fd

    @property
    def map_info(self) -> dict[str, int]:
        return dict(self.manifest["map_info"])

    def lookup(self, tid: int) -> dict[str, Any] | None:
        _require_int(tid, "tid", maximum=UINT32_MAX)
        if self._map_fd is None:
            raise KernelPidProbeError("probe map descriptor is closed")
        record = _PidRecord()
        rc = self._library.wk_pid_probe_lookup(self._map_fd, tid, ctypes.byref(record))
        if rc == -errno.ENOENT:
            return None
        _call_error(rc, "wk_pid_probe_lookup")
        try:
            comm = bytes(record.comm).split(b"\0", 1)[0].decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise KernelPidProbeError("kernel PID record comm is not UTF-8") from error
        return {
            "kernel_ids": int(record.kernel_ids),
            "local_tid": int(record.local_tid),
            "local_tgid": int(record.local_tgid),
            "observed_boot_ns": int(record.observed_boot_ns),
            "comm": comm,
        }

    @property
    def dropped_updates(self) -> int:
        record = self.lookup(0)
        if record is None:
            raise KernelPidProbeError("kernel PID probe drop counter is missing")
        return record["kernel_ids"]

    def stop_sampling(self) -> None:
        """Detach sampling by closing only the inherited BPF link."""
        if self._link_fd is not None:
            fd = self._link_fd
            _close_descriptor(fd)
            self._link_fd = None
            self.sampling_detached = True
        else:
            self.sampling_detached = True

    def release_parent_after_spawn(self) -> None:
        """Close all parent copies after the collector inherited map/link."""
        errors = []
        for name in ("_link_fd", "_map_fd", "_prog_fd"):
            fd = getattr(self, name)
            try:
                _close_descriptor(fd)
            except OSError as error:
                errors.append(f"{name}: {error}")
            else:
                setattr(self, name, None)
        self.sampling_detached = self._link_fd is None
        if errors:
            raise KernelPidProbeError("parent probe descriptor close failed: " + "; ".join(errors))

    def close(self) -> None:
        """Close link, map and program descriptors; safe to call repeatedly."""
        errors = []
        try:
            self.stop_sampling()
        except OSError as error:
            errors.append(f"link: {error}")
        for name in ("_map_fd", "_prog_fd"):
            fd = getattr(self, name)
            setattr(self, name, None)
            try:
                _close_descriptor(fd)
            except OSError as error:
                errors.append(f"{name}: {error}")
        if errors:
            raise KernelPidProbeError("probe descriptor close failed: " + "; ".join(errors))


def _manifest_for_create(directory: Path, run_id: str, boot_id: str,
                         compiler: str, compiler_argv: list[str], verifier: str,
                         namespace: dict[str, Any], map_info: dict[str, int],
                         prog_id: int, prog_tag: str, link_type: str,
                         link_tp_name: str, library_path: Path) -> dict[str, Any]:
    creator = json_identity(os.getpid())
    if creator is None:
        raise KernelPidProbeError("creator process identity is unavailable")
    _require_identity(creator, "creator")
    return {
        "schema": MANIFEST_SCHEMA,
        "run_id": run_id,
        "boot_id": boot_id,
        "creator": creator,
        "source_path": str(SOURCE.resolve()),
        "source_sha256": _sha256(SOURCE),
        "library_path": str(library_path.resolve()),
        "library_sha256": _sha256(library_path),
        "compiler": compiler,
        "compiler_argv": list(compiler_argv),
        "verifier": verifier,
        "namespace": namespace,
        "map_info": map_info,
        "prog_id": prog_id,
        "prog_tag": prog_tag,
        "link_type": link_type,
        "link_tp_name": link_tp_name,
    }


def _validate_manifest(value: dict[str, Any], manifest_path: Path,
                       run_id: str, boot_id: str) -> dict[str, Any]:
    if set(value) != MANIFEST_FIELDS:
        raise KernelPidProbeError("manifest fields are incomplete or unexpected")
    if value.get("schema") != MANIFEST_SCHEMA:
        raise KernelPidProbeError("manifest schema is invalid")
    if value.get("run_id") != run_id or not isinstance(run_id, str) or not run_id:
        raise KernelPidProbeError("manifest run_id differs")
    if value.get("boot_id") != boot_id or not isinstance(boot_id, str) or not boot_id:
        raise KernelPidProbeError("manifest boot_id differs")
    _require_identity(value.get("creator"), "creator")
    for key in ("source_path", "library_path"):
        if not isinstance(value.get(key), str) or not Path(value[key]).is_absolute():
            raise KernelPidProbeError(f"manifest {key} is invalid")
    _require_sha(value.get("source_sha256"), "source_sha256")
    _require_sha(value.get("library_sha256"), "library_sha256")
    compiler = value.get("compiler")
    if not isinstance(compiler, str) or not compiler:
        raise KernelPidProbeError("manifest compiler is invalid")
    argv = value.get("compiler_argv")
    if (not isinstance(argv, list) or not argv
            or any(not isinstance(item, str) for item in argv)):
        raise KernelPidProbeError("manifest compiler_argv is invalid")
    if not isinstance(value.get("verifier"), str) or not value["verifier"]:
        raise KernelPidProbeError("manifest verifier is invalid")
    _validate_namespace(value.get("namespace"))
    value["map_info"] = _validate_map_info(value.get("map_info"))
    _require_int(value.get("prog_id"), "manifest prog_id", minimum=1)
    for key in ("prog_tag", "link_type", "link_tp_name"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise KernelPidProbeError(f"manifest {key} is invalid")
    if re.fullmatch(r"[0-9a-f]{16}", value["prog_tag"]) is None:
        raise KernelPidProbeError("manifest prog_tag is invalid")
    if value["link_type"] != "raw_tracepoint" or value["link_tp_name"] != "sched_switch":
        raise KernelPidProbeError("manifest link target is invalid")
    if manifest_path.resolve() == Path(value["library_path"]).resolve():
        raise KernelPidProbeError("manifest and library paths collide")
    return value


def _validate_adopt_owner(manifest: dict[str, Any], boot_id: str) -> None:
    """Bind adoption to this boot and the exact process that created the probe."""
    try:
        current_boot = host_boot_id()
    except OSError as error:
        raise KernelPidProbeError("host boot identity is unavailable") from error
    if current_boot != boot_id:
        raise KernelPidProbeError("host boot identity differs")
    creator = manifest["creator"]
    parent_pid = os.getppid()
    if parent_pid != creator["pid"]:
        raise KernelPidProbeError("probe creator is not the current parent")
    parent = json_identity(parent_pid)
    if parent is None:
        raise KernelPidProbeError("current parent identity is unavailable")
    for field in ("pid", "start_ticks", "pgid"):
        if parent.get(field) != creator[field]:
            raise KernelPidProbeError("current parent identity differs")


def _validate_adopt_paths(manifest_path: Path, manifest: dict[str, Any]) -> tuple[Path, Path]:
    """Reject path aliases and require the repository source plus sibling library."""
    source = Path(manifest["source_path"])
    library = Path(manifest["library_path"])
    if source.is_symlink() or library.is_symlink():
        raise KernelPidProbeError("probe source or library must not be a symlink")
    if source.resolve() != SOURCE.resolve():
        raise KernelPidProbeError("native probe source path differs")
    expected_library = manifest_path.parent / "libkernel_pid_probe.so"
    if library.name != expected_library.name or library.resolve() != expected_library:
        raise KernelPidProbeError("native probe library path differs")
    if not source.is_file() or not library.is_file():
        raise KernelPidProbeError("native probe source or library is unavailable")
    return source, library


def create_probe(directory: str | Path, run_id: str, boot_id: str) -> KernelPidProbe:
    """Compile and open one namespace-bound probe, retaining all three fds."""
    if not isinstance(run_id, str) or not run_id or not isinstance(boot_id, str) or not boot_id:
        raise KernelPidProbeError("run_id and boot_id are required")
    if not sys_platform_linux():
        raise KernelPidProbeError("kernel PID probe requires Linux")
    directory = Path(directory)
    if directory.exists() or not directory.is_absolute():
        raise KernelPidProbeError("probe directory must be a fresh absolute directory")
    directory.mkdir(mode=0o700)
    if not SOURCE.is_file():
        raise KernelPidProbeError(f"native probe source is missing: {SOURCE}")
    compiler = shutil.which("gcc")
    if not compiler:
        raise KernelPidProbeError("gcc is unavailable")
    library_path = directory / "libkernel_pid_probe.so"
    command = [compiler, "-shared", "-fPIC", "-std=c11", "-O2", "-Wall", "-Wextra",
               "-Werror", "-o", str(library_path), str(SOURCE)]
    try:
        with (directory/'build.stdout.log').open('xb') as stdout, \
                (directory/'build.stderr.log').open('xb') as stderr:
            subprocess.run(command, cwd=ROOT, check=True, stdout=stdout,
                           stderr=stderr, timeout=60)
        library = _load_library(library_path)
        namespace = _namespace_proof()
        fds = (ctypes.c_int * 3)(-1, -1, -1)
        verifier = ctypes.create_string_buffer(VERIFIER_BYTES)
        rc = library.wk_pid_probe_open(namespace["dev"], namespace["ino"],
                                       DEFAULT_MAX_ENTRIES, fds, verifier, VERIFIER_BYTES)
        (directory/'verifier.log').write_bytes(verifier.value)
        _call_error(rc, "wk_pid_probe_open")
        owned = [int(fd) for fd in fds]
        if any(fd < 0 for fd in owned) or len(set(owned)) != 3:
            raise KernelPidProbeError("native probe returned invalid descriptors")
        map_fd, prog_fd, link_fd = owned
        map_info = _validate_map_info(_map_info(library, map_fd))
        _map_info_matches_fdinfo(map_info, _require_fdinfo(
            map_fd, MAP_INFO_FIELDS, "map"))
        prog_info = _require_fdinfo(prog_fd, ("prog_id", "prog_tag"), "program")
        link_info = _require_fdinfo(
            link_fd, ("link_type", "link_id", "prog_id", "prog_tag", "tp_name"), "link")
        link_text = _read_fdinfo_text(link_fd, ("link_type", "tp_name"))
        _validate_link_fdinfo(prog_info, link_info, link_text)
        manifest = _manifest_for_create(
            directory, run_id, boot_id, compiler, command,
            verifier.value.decode("utf-8", errors="strict"), namespace,
            map_info, link_info["prog_id"], str(link_info["prog_tag"]),
            link_text["link_type"], link_text["tp_name"], library_path)
        manifest_path = directory / "manifest.json"
        with manifest_path.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        return KernelPidProbe(manifest_path=manifest_path, manifest=manifest,
                              library=library, map_fd=map_fd, link_fd=link_fd,
                              prog_fd=prog_fd)
    except BaseException:
        for fd in locals().get("owned", []):
            try:
                _close_descriptor(fd)
            except OSError:
                pass
        raise


def sys_platform_linux() -> bool:
    # Kept as a small seam for pure mock tests; no namespace or native probe
    # is touched by the tests when this returns a mocked Linux value.
    import sys
    return sys.platform.startswith("linux")


def adopt_probe(manifest_path: str | Path, map_fd: int, link_fd: int,
                run_id: str, boot_id: str) -> KernelPidProbe:
    """Adopt inherited map/link fds only after strict provenance checks."""
    raw_path = Path(manifest_path)
    if raw_path.is_symlink():
        raise KernelPidProbeError("probe manifest must not be a symlink")
    path = raw_path.resolve()
    manifest = _validate_manifest(_strict_json(path), path, run_id, boot_id)
    _validate_adopt_owner(manifest, boot_id)
    source, library_path = _validate_adopt_paths(path, manifest)
    if _sha256(source) != manifest["source_sha256"]:
        raise KernelPidProbeError("native probe source hash differs")
    if _sha256(library_path) != manifest["library_sha256"]:
        raise KernelPidProbeError("native probe library hash differs")
    map_fd = _require_int(map_fd, "map_fd", minimum=0)
    link_fd = _require_int(link_fd, "link_fd", minimum=0)
    if map_fd == link_fd:
        raise KernelPidProbeError("map_fd and link_fd must be distinct")
    library = _load_library(library_path)
    map_info = _validate_map_info(_map_info(library, map_fd))
    if map_info != manifest["map_info"]:
        raise KernelPidProbeError("map info differs from manifest")
    _map_info_matches_fdinfo(map_info, _require_fdinfo(map_fd, MAP_INFO_FIELDS, "map"))
    link_info = _require_fdinfo(
        link_fd, ("link_type", "link_id", "prog_id", "prog_tag", "tp_name"), "link")
    link_text = _read_fdinfo_text(link_fd, ("link_type", "tp_name"))
    _validate_link_fdinfo(
        {"prog_id": manifest["prog_id"], "prog_tag": manifest["prog_tag"]},
        link_info, link_text)
    if (link_info["prog_id"] != manifest["prog_id"]
            or link_info["prog_tag"] != manifest["prog_tag"]
            or link_text["link_type"] != manifest["link_type"]
            or link_text["tp_name"] != manifest["link_tp_name"]):
        raise KernelPidProbeError("BPF link program identity differs")
    return KernelPidProbe(manifest_path=path, manifest=manifest, library=library,
                          map_fd=map_fd, link_fd=link_fd)
