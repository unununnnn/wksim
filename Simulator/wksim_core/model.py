"""Build/use the reviewed local model without CopterSim, Gazebo or MATLAB runtime."""
import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import tempfile
import zipfile

ARCHIVE = Path("/mnt/e/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip")
EXPECTED_HASH = "d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed"
MODEL_PREFIX = "e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/"
MEMBERS = [MODEL_PREFIX + name for name in
           ("Exp1_MinModelTemp.cpp", "Exp1_MinModelTemp.h", "rtwtypes.h")]
MEMBERS += ["R2022b/simulink/include/rtw_continuous.h", "R2022b/simulink/include/rtw_solver.h"]


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
    manifest = {"archive": str(archive_path), "archive_sha256": EXPECTED_HASH,
                "wrapper_sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
                "library": str(library), "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
                "argv": argv, "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
                "profile": "generated-quad-x-1ms; local use; vendor redistribution not granted"}
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

    def close(self):
        if self.handle:
            self.library.wk_model_destroy(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()
    print(build_model(args.archive))
