"""Build/use the reviewed local model without CopterSim, Gazebo or MATLAB runtime."""
import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import struct
import subprocess
import tempfile
import zipfile

ARCHIVE = Path("/mnt/e/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip")
EXPECTED_HASH = "d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed"
MODEL_PREFIX = "e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/"
MEMBERS = [MODEL_PREFIX + name for name in
           ("Exp1_MinModelTemp.cpp", "Exp1_MinModelTemp.h", "rtwtypes.h")]
MEMBERS += ["R2022b/simulink/include/rtw_continuous.h", "R2022b/simulink/include/rtw_solver.h"]
ABI_CONTRACT = {
    "name": "wksim-model-c-v2",
    "required_symbols": {
        "wk_model_create": "void*()",
        "wk_model_destroy": "void(void*)",
        "wk_model_initial_state": "int(void*,double*,int)",
        "wk_model_step": "int(void*,const double*,int,int,double*,int)",
        "wk_model_step_with_terrain": "int(void*,const double*,int,const double*,int,int,double*,int)",
    },
    "actuator_count": 16,
    "terrain_count": 15,
    "output_count": 120,
    "output_layout": ["Vehicle60", "Sensor30", "HILGPS30"],
    "dt_seconds": 0.001,
    "initial_state": {"tick": 0, "read_only": True, "finite": True, "return_codes": [0, 1, 3]},
    "step_return_codes": [0, 1, 2, 3],
}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dynamic_dependencies(library):
    """Return ELF NEEDED entries without executing the candidate library."""
    output = subprocess.check_output(["readelf", "-d", str(library)], text=True, timeout=10)
    return sorted(match.group(1) for line in output.splitlines()
                  if (match := re.search(r"\(NEEDED\).*Shared library: \[(.+)\]", line)))


def exported_model_symbols(library):
    """Return defined public wk_model_* symbols without loading the library."""
    output = subprocess.check_output(["nm", "-D", "--defined-only", str(library)], text=True, timeout=10)
    return sorted({line.split()[-1] for line in output.splitlines()
                   if line.split() and line.split()[-1].startswith("wk_model_")})


def model_platform():
    return {"system": platform.system(), "machine": platform.machine(),
            "libc": list(platform.libc_ver()), "binary64_bytes": ctypes.sizeof(ctypes.c_double)}


def extract_source(archive_path=ARCHIVE):
    """Extract an exact reviewed allowlist into a fresh non-repository directory."""
    archive_path = Path(archive_path)
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != EXPECTED_HASH:
        raise ValueError("Unreviewed model archive: inspect source before changing its hash")
    build_dir = Path(tempfile.mkdtemp(prefix="wksim-model-"))
    with zipfile.ZipFile(archive_path) as archive:
        for member in MEMBERS:
            if archive.getinfo(member).file_size > 2_000_000:
                raise ValueError("Unexpected member size")
            (build_dir / Path(member).name).write_bytes(archive.read(member))
    return build_dir


def build_model(archive_path=ARCHIVE):
    if platform.system() != "Linux":
        raise RuntimeError("This build profile requires Linux (Ubuntu-22.04 WSL)")
    build_dir = extract_source(archive_path)
    library = build_dir / "libwksim_model.so"
    wrapper = Path(__file__).with_suffix(".cpp")
    argv = ["g++", "-std=c++17", "-O2", "-fno-fast-math", "-fPIC", "-shared",
            "-Wl,--no-undefined", "-I", str(build_dir),
            str(build_dir / "Exp1_MinModelTemp.cpp"), str(wrapper), "-o", str(library)]
    build = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    (build_dir / "build.stdout.log").write_text(build.stdout, encoding="utf-8")
    (build_dir / "build.stderr.log").write_text(build.stderr, encoding="utf-8")
    if build.returncode:
        raise RuntimeError(f"Build failed; see {build_dir / 'build.stderr.log'}")
    loader = Path(__file__).resolve()
    source_files = [{"path": Path(member).name, "size": (build_dir / Path(member).name).stat().st_size,
                     "sha256": _sha(build_dir / Path(member).name)} for member in MEMBERS]
    archive_members = [{"path": member, "size": row["size"], "sha256": row["sha256"]}
                       for member, row in zip(MEMBERS, source_files)]
    manifest = {"schema_version": 2, "archive": str(archive_path), "archive_sha256": EXPECTED_HASH,
                "archive_members": archive_members, "source_files": source_files,
                "wrapper": str(wrapper), "wrapper_sha256": _sha(wrapper),
                "loader": str(loader), "loader_sha256": _sha(loader),
                "library": str(library), "library_sha256": _sha(library),
                "argv": argv, "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
                "profile": "generated-quad-x-1ms; local use; vendor redistribution not granted",
                "platform": model_platform(), "abi": ABI_CONTRACT,
                "dynamic_dependencies": dynamic_dependencies(library)}
    (build_dir / "build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return library


class Model:
    """One model instance, fixed 1 ms integration; coordinates NED / FRD, SI units."""
    def __init__(self, library):
        self.library = ctypes.CDLL(str(Path(library).resolve()))
        self.library.wk_model_create.argtypes = []
        self.library.wk_model_create.restype = ctypes.c_void_p
        self.library.wk_model_destroy.argtypes = [ctypes.c_void_p]
        self.library.wk_model_destroy.restype = None
        self.library.wk_model_step.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_double),
                                             ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        self.library.wk_model_step.restype = ctypes.c_int
        if hasattr(self.library, "wk_model_step_with_terrain"):
            self.library.wk_model_step_with_terrain.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_double),
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_double),
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_double),
                ctypes.c_int,
            ]
            self.library.wk_model_step_with_terrain.restype = ctypes.c_int
        self.handle = self.library.wk_model_create()
        if not self.handle:
            raise RuntimeError("Model initialization failed")
        self.ticks = 0
        self._output = (ctypes.c_double * 120)()

    def step(self, commands, steps=1, *, terrain=None):
        if (
            not isinstance(commands, (list, tuple))
            or len(commands) != 16
            or any(
                isinstance(x, bool)
                or not isinstance(x, (int, float))
                or not math.isfinite(x)
                or not 0 <= x <= 1
                for x in commands
            )
        ):
            raise ValueError("Expected 16 finite normalized actuator commands in [0,1]")
        if type(steps) is not int or not 1 <= steps <= 1000:
            raise ValueError("steps must be an integer in [1,1000]")
        if terrain is not None:
            if (
                not isinstance(terrain, (list, tuple))
                or len(terrain) != 15
                or any(
                    isinstance(x, bool)
                    or not isinstance(x, (int, float))
                    or not math.isfinite(x)
                    for x in terrain
                )
            ):
                raise ValueError("Expected 15 finite numeric terrain inputs")
            step_fn = getattr(self.library, "wk_model_step_with_terrain", None)
            if step_fn is None:
                raise RuntimeError("Model library lacks the reviewed terrain-input ABI")
            if not getattr(step_fn, "argtypes", None):
                step_fn.argtypes = [
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_double),
                    ctypes.c_int,
                    ctypes.POINTER(ctypes.c_double),
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.POINTER(ctypes.c_double),
                    ctypes.c_int,
                ]
                step_fn.restype = ctypes.c_int
            inputs = (ctypes.c_double * 16)(*commands)
            terrain_inputs = (ctypes.c_double * 15)(*terrain)
            status = step_fn(
                self.handle, inputs, 16, terrain_inputs, 15, steps, self._output, 120
            )
        else:
            inputs = (ctypes.c_double * 16)(*commands)
            status = self.library.wk_model_step(
                self.handle, inputs, 16, steps, self._output, 120
            )
        if status:
            raise RuntimeError(f"Model step failed: {status}")
        self.ticks += steps
        result = list(self._output)
        if abs(result[2] - self.ticks * 0.001) > 1e-8:
            raise RuntimeError("Model clock differs from fixed-step scheduler")
        return result

    def initial_state(self):
        if self.ticks != 0:
            raise RuntimeError("Initial state is only available before stepping")
        state_fn = getattr(self.library, "wk_model_initial_state", None)
        if state_fn is None:
            raise RuntimeError("Model library lacks the initial-state ABI")
        if not getattr(state_fn, "argtypes", None):
            state_fn.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_double),
                ctypes.c_int,
            ]
            state_fn.restype = ctypes.c_int
        status = state_fn(self.handle, self._output, 120)
        if status:
            raise RuntimeError(f"Model initial state failed: {status}")
        result = list(self._output)
        if len(result) != 120 or not all(math.isfinite(value) for value in result):
            raise RuntimeError("Model initial state is not finite")
        return result


    def close(self):
        if self.handle:
            self.library.wk_model_destroy(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def probe_model(library):
    """Exercise the tick-0 ABI and prove it does not change the first fixed step."""
    commands = [0.0] * ABI_CONTRACT["actuator_count"]
    with Model(library) as candidate:
        initial = candidate.initial_state()
        repeated = candidate.initial_state()
        if candidate.ticks != 0 or initial != repeated:
            raise RuntimeError("Initial-state ABI advanced or changed the model")
        after_initial = candidate.step(commands)
    with Model(library) as fresh:
        direct = fresh.step(commands)
    if after_initial != direct:
        raise RuntimeError("Initial-state ABI changed the first fixed model step")
    pack = lambda values: hashlib.sha256(struct.pack("<120d", *values)).hexdigest()
    return {"symbol": "wk_model_initial_state", "values": len(initial), "finite": True,
            "tick_before_step": 0, "tick_after_step": 1, "read_only": True,
            "initial_state_sha256": pack(initial), "first_step_sha256": pack(after_initial),
            "scope": "tick-0 ABI exercise and first-step equivalence; not flight proof"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()
    print(build_model(args.archive))
