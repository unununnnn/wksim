"""Strict mass-only configuration for the pinned generated Quad X model.

Local source use only; no vendor source is redistributed. Other components are
read-only. This is not a component library or a physics-accuracy approval.
"""
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess

from .model import ARCHIVE, EXPECTED_HASH, Model, extract_source

RAW_HASHES = {
    "Exp1_MinModelTemp.cpp": "a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019",
    "Exp1_MinModelTemp.h": "2d89ad1b492c5e70e80682a9f53896e0538260946a0180a2ca44e500ba1589bd",
    "rtwtypes.h": "9d5bd1a47f06fd3f6cb124a96d407a6296875763759ab9fb388296e6199a1716",
    "rtw_continuous.h": "8f2c78fdc5a097552078484c738aefcc944463c8834d2ca6319b76cedf526b18",
    "rtw_solver.h": "359ff69aa94a137e8b246721ead52e056dd4fdf11c35a7f92ebb9f14e0cda674",
}
WRAPPER_HASH = "3f325678b1d85c9aa3fd07bd644d82935aa26d82885926defeced139f02ddf2c"
SOURCE = {"archive_sha256": EXPECTED_HASH, "raw_members_sha256": RAW_HASHES,
          "base_wrapper_sha256": WRAPPER_HASH, "model_version": "11.0 / R2022b",
          "recipe": "quad-mass-initializer-v1; g++ c++17 O2 no-fast-math"}
# Units below are derived from the generated equations, not similarly named
# aerodynamic dimensionless coefficients. Source-native RPM is kept fixed zero.
_FIXED = {
    "ModelInit_AngEuler": ([0., 0., 0.], "rad; roll,pitch,yaw"),
    "ModelInit_PosE": ([0., 0., 0.], "m; NED"),
    "ModelInit_RPM": (0., "source-native motor initial speed; fixed zero"),
    "ModelInit_RateB": ([0., 0., 0.], "rad/s; FRD"),
    "ModelInit_VelB": ([0., 0., 0.], "m/s; FRD"),
    "ModelParam_GPSLatLong": ([40.1540302, 116.2593683], "degree; latitude,longitude"),
    "ModelParam_envAltitude": (-50., "m; source altitude parameter"),
    "ModelParam_motorCr": (842.1, "rad/s per normalized command"),
    "ModelParam_motorJm": (.0001287, "kg*m^2"),
    "ModelParam_motorMinThr": (.05, "normalized command"),
    "ModelParam_motorT": (.0214, "s"),
    "ModelParam_motorWb": (22.83, "rad/s"),
    "ModelParam_rotorCm": (2.783e-7, "N*m/(rad/s)^2"),
    "ModelParam_rotorCt": (1.681e-5, "N/(rad/s)^2"),
    "ModelParam_uavCCm": ([.0035, .0039, .0034], "N*m/(rad/s)^2; FRD"),
    "ModelParam_uavCd": (.055, "N/(m/s)^2"),
    "ModelParam_uavDearo": (.12, "m; downward aero-center offset"),
    "ModelParam_uavJ": ([.0211, 0., 0., 0., .0219, 0., 0., 0., .0366], "kg*m^2; 3x3 diagonal"),
    "ModelParam_uavR": (.225, "m; center to rotor"),
    "ModelParam_3DType": (3, "source enum"),
    "ModelParam_uavType": (3, "source enum; Quad X"),
}
FIXED = {k: {"value": v, "unit": u} for k, (v, u) in _FIXED.items()}
COMPONENTS = {"airframe": "fixed Quad X", "motor_count": 4,
              "motor_count_basis": "uavType=3 selects generated d[2]=4; no named uavMotNumbs parameter",
              "input": "16 normalized commands [0,1]; indices 4..15 must be zero",
              "motors": [{"input_index": i, "position_FRD": p, "angle_deg": a,
                          "source_rotation_sign": s, "motor": "fixed shared motor", "rotor": "fixed shared rotor"}
                         for i, p, a, s in [(0, "front-right", 45, -1), (1, "rear-left", 225, -1),
                                           (2, "front-left", 315, 1), (3, "rear-right", 135, 1)]],
              "rotation_sign_convention": "generated source: -1 anticlockwise, +1 clockwise"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _mass(value):
    # Bounded local engineering edit range; not an airworthiness envelope.
    if type(value) not in (int, float) or not math.isfinite(value) or not 0.5 <= value <= 5.0:
        raise ValueError("mass must be a finite number in [0.5,5.0] kg")
    return float(value)


def make_config(name="quad-x-default", mass_kg=1.515):
    if type(name) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("name must contain 1..64 ASCII letters, digits, underscores or hyphens")
    result = {"schema": "wksim.quad-mass.v1", "name": name, "source": SOURCE,
              "components": COMPONENTS, "fixed_parameters": FIXED,
              "mass": {"value": _mass(mass_kg), "unit": "kg", "default": 1.515,
                       "source_parameter": "ModelParam_uavMass"}}
    result["model_identity"] = "sha256:" + sha(canonical(result).encode())
    return json.loads(canonical(result))


def validate(config):
    if type(config) is not dict or type(config.get("mass")) is not dict:
        raise ValueError("incomplete configuration")
    expected = make_config(config.get("name"), config["mass"].get("value"))
    if canonical(config) != canonical(expected):
        raise ValueError("configuration fields, fixed mapping, units, source or identity differ")
    return expected


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def load_config(path):
    return validate(json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_pairs))


def save_config(config, path):
    text = json.dumps(validate(config), indent=2, allow_nan=False) + "\n"
    # Explicit no-clobber: default and previous user exports are never overwritten.
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(text)


def parameterize_source(raw, mass_kg):
    if sha(raw) != RAW_HASHES["Exp1_MinModelTemp.cpp"]:
        raise ValueError("raw generated source hash differs")
    pattern = rb"(// Variable: ModelParam_uavMass\s*//[^\r\n]*[\r\n\s]+)(1\.515)(,)"
    matches = list(re.finditer(pattern, raw))
    if len(matches) != 1:
        raise ValueError("mass initializer must have exactly one mapping")
    match = matches[0]
    return raw[:match.start(2)] + repr(_mass(mass_kg)).encode("ascii") + raw[match.end(2):]


def build_configured_model(config, archive=ARCHIVE):
    config = validate(config)
    if platform.system() != "Linux":
        raise RuntimeError("Use Ubuntu-22.04 WSL for this build profile")
    folder = extract_source(archive)
    for name, expected in RAW_HASHES.items():
        if sha((folder / name).read_bytes()) != expected:
            raise ValueError("raw member hash differs: " + name)
    source = folder / "Exp1_MinModelTemp.cpp"
    raw = source.read_bytes()
    (folder / "Exp1_MinModelTemp.original.cpp").write_bytes(raw)
    source.write_bytes(parameterize_source(raw, config["mass"]["value"]))
    wrapper = Path(__file__).with_name("model.cpp").read_bytes()
    if sha(wrapper) != WRAPPER_HASH:
        raise ValueError("default wrapper hash differs")
    # Keep the exact base bridge, adding a local one-lifetime guard and readback.
    marker = b"    try {"
    if wrapper.count(marker) != 1:
        raise ValueError("ambiguous create mapping")
    wrapper = wrapper.replace(marker, b"    static bool used = false;\n    if (used) return nullptr;\n    used = true;\n" + marker)
    wrapper += ("\nextern \"C\" double wk_configured_mass() { return MulticopterModelClass::Exp1_MinModelTemp_P.ModelParam_uavMass; }\n"
                "extern \"C\" const char* wk_configured_identity() { return \"" + config["model_identity"] + "\"; }\n").encode()
    (folder / "configured_wrapper.cpp").write_bytes(wrapper)
    save_config(config, folder / "config.json")
    library = folder / "libwksim_configured.so"
    argv = ["g++", "-std=c++17", "-O2", "-fno-fast-math", "-fPIC", "-shared", "-Wl,--no-undefined",
            "-I", str(folder), str(source), str(folder / "configured_wrapper.cpp"), "-o", str(library)]
    manifest = {"config": config, "archive": str(archive), "argv": argv,
                "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
                "builder_sha256": sha(Path(__file__).read_bytes()), "files_sha256": {}}
    (folder / "build-request.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    build = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    (folder / "build.stdout.log").write_text(build.stdout, encoding="utf-8")
    (folder / "build.stderr.log").write_text(build.stderr, encoding="utf-8")
    if build.returncode:
        raise RuntimeError(f"Build failed; retained in {folder}")
    names = [*RAW_HASHES, "Exp1_MinModelTemp.original.cpp", "configured_wrapper.cpp", library.name, "config.json"]
    manifest["files_sha256"] = {n: sha((folder / n).read_bytes()) for n in names}
    (folder / "build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return library


class ConfiguredModel(Model):
    """Verified local build; one vehicle lifetime per library/process, no live tuning."""
    _used_pid = None

    def __init__(self, library, config):
        config = validate(config)
        library = Path(library).resolve()
        manifest = json.loads((library.parent / "build.json").read_text(encoding="utf-8"))
        if manifest["config"] != config or load_config(library.parent / "config.json") != config:
            raise ValueError("build config identity differs")
        expected_names = {*RAW_HASHES, "Exp1_MinModelTemp.original.cpp", "configured_wrapper.cpp", "libwksim_configured.so", "config.json"}
        if set(manifest["files_sha256"]) != expected_names or library.name != "libwksim_configured.so":
            raise ValueError("incomplete build artifact manifest")
        for name, expected in manifest["files_sha256"].items():
            if sha((library.parent / name).read_bytes()) != expected:
                raise ValueError("build artifact hash differs: " + name)
        original = (library.parent / "Exp1_MinModelTemp.original.cpp").read_bytes()
        expected_source = parameterize_source(original, config["mass"]["value"])
        if (library.parent / "Exp1_MinModelTemp.cpp").read_bytes() != expected_source:
            raise ValueError("generated source does not apply the configured mass")
        for name, expected in RAW_HASHES.items():
            if name.endswith(".h") and sha((library.parent / name).read_bytes()) != expected:
                raise ValueError("pinned header differs: " + name)
        if ConfiguredModel._used_pid == os.getpid():
            raise RuntimeError("Use a fresh process for each configured vehicle lifetime")
        ConfiguredModel._used_pid = os.getpid()
        self.config = config
        super().__init__(library)
        self.library.wk_configured_mass.restype = ctypes.c_double
        self.library.wk_configured_identity.restype = ctypes.c_char_p
        self.applied_mass_kg = self.library.wk_configured_mass()
        if self.applied_mass_kg != config["mass"]["value"] or self.library.wk_configured_identity().decode() != config["model_identity"]:
            self.close()
            raise ValueError("compiled identity or applied mass differs before first step")

    def step(self, commands, steps=1):
        if len(commands) != 16 or any(x != 0 for x in commands[4:]):
            raise ValueError("Quad X unused actuator channels 4..15 must be zero")
        return super().step(commands, steps)
