"""Isolated, immutable source-template Hex X candidate; no flight controllers/UI.

Only uavType changes from the pinned Quad X source. Vendor source stays in a
private temporary build directory. Mass/inertia/rotors are uncalibrated defaults.
"""
import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Simulator"))
from wksim_core.model import ARCHIVE, EXPECTED_HASH, MEMBERS, Model
from wksim_core.model_parameters import FIXED, RAW_HASHES, WRAPPER_HASH, _pairs, canonical, sha

ANGLES = (90, 270, 330, 150, 30, 210)
SPINS = (1, -1, 1, -1, -1, 1)
LIBRARY = "libwksim_hex_candidate.so"
RECIPE = "hex-x-template-uavType-initializer-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_pairs)


def write_json(value, path):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def make_config(name="hex-x-source-template"):
    require(type(name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name), "Invalid configuration name")
    parameters = json.loads(canonical(FIXED))
    parameters["ModelParam_uavType"] = {"value": 5, "unit": "source enum; Hex X"}
    parameters["ModelParam_uavMass"] = {"value": 1.515, "unit": "kg"}
    config = {
        "schema": "wksim.hex-source-template.v1", "name": name,
        "source": {"archive_sha256": EXPECTED_HASH, "raw_members_sha256": RAW_HASHES,
                   "base_wrapper_sha256": WRAPPER_HASH, "recipe": RECIPE},
        "parameters": parameters,
        "basis": "Original Quad X mass/inertia/motor/rotor/environment template; no physical Hex aircraft calibration",
        "geometry": {"airframe": "Hex X", "motor_count": 6,
                     "motor_count_basis": "generated d[4]=6; no writable motor-count parameter",
                     "angles_deg": list(ANGLES), "source_spin": list(SPINS),
                     "spin_convention": "+1 CW, -1 CCW viewed from above; body yaw moment has opposite sign",
                     "rpm_output_indices": list(range(16, 22)), "unused_input_indices": list(range(6, 16))},
        "profile": {"dt_s": .001, "input_count": 16, "output_count": 120,
                    "lifetime": "one vehicle per fresh process; no in-process reset",
                    "source_3DType": 3, "hex_visual_3DType": None},
    }
    config["model_identity"] = "sha256:" + sha(canonical(config).encode())
    return json.loads(canonical(config))


def validate(config):
    require(type(config) is dict, "Configuration must be an object")
    expected = make_config(config.get("name"))
    require(canonical(config) == canonical(expected), "Immutable Hex configuration or identity differs")
    return expected


def load_config(path):
    return validate(read_json(path))


def parameterize_source(raw, config):
    """Verify actual table/22 unique initializers before replacing exactly one value."""
    config = validate(config)
    require(sha(raw) == RAW_HASHES["Exp1_MinModelTemp.cpp"], "Raw generated source hash differs")
    source = raw.decode("latin1")
    pattern = r"// Variable: (Model\w+)\s*(?://[^\r\n]*\s*)+([{}0-9., +Ee\-]+),"
    found = {}
    for match in re.finditer(pattern, source):
        name, value = match.groups()
        require(name not in found, "Duplicate named initializer: " + name)
        found[name] = ([float(v) for v in value.strip(" {}\r\n").split(",")]
                       if "{" in value else float(value))
    expected = {k: v["value"] for k, v in config["parameters"].items()}
    expected["ModelParam_uavType"] = 3
    require(found == expected and len(found) == 22, "Original 22 named template parameters differ")
    arrays = {}
    for name, size in [("d", 10), ("e", 80), ("c", 80)]:
        matches = list(re.finditer(r"static const \w+ " + name + r"\[" + str(size) + r"\] = \{(.*?)\};", source, re.S))
        require(len(matches) == 1, "Ambiguous rotor table: " + name)
        arrays[name] = [float(v.strip()) for v in matches[0][1].split(",")]
        require(len(arrays[name]) == size, "Wrong rotor table size")
    require("s297_iter = d[uavType - 1];" in source and
            "s305_iter = (10 * rtb_Sum_i + uavType) - 1;" in source, "Rotor table addressing differs")
    require(arrays["d"][4] == 6 and [int(arrays["c"][10*i+4]) for i in range(6)] == list(SPINS), "Hex motor count/spins differ")
    require(all(abs(math.degrees(arrays["e"][10*i+4]) % 360 - ANGLES[i]) < 1e-10 for i in range(6)), "Hex angles differ")
    for i in range(6):
        require(len(re.findall(r"Exp1_MinModelTemp_U.inPWMs\[" + str(i) + r"\], &Exp1_MinModelTemp_B.MotorNonlinearDynamic" + str(i+1) + r",", source)) == 1, "Motor input mapping differs")
        require(len(re.findall(r"VehileInfo60d\[" + str(16+i) + r"\] = .*?MotorNonlinearDynamic" + str(i+1) + r"\.Motor_Dynamics.x;", source, re.S)) == 1, "RPM output mapping differs")
    pattern = rb"(// Variable: ModelParam_uavType\s*//[^\r\n]*[\r\n\s]+)(3)(,)"
    matches = list(re.finditer(pattern, raw))
    require(len(matches) == 1, "uavType initializer must map exactly once")
    match = matches[0]
    return raw[:match.start(2)] + b"5" + raw[match.end(2):]


def parameter_slots(config):
    return [(name, i if isinstance(record["value"], list) else None, value)
            for name, record in sorted(config["parameters"].items())
            for i, value in enumerate(record["value"] if isinstance(record["value"], list) else [record["value"]])]


def wrapper_source(config):
    config = validate(config)
    base = (ROOT / "Simulator/wksim_core/model.cpp").read_bytes()
    require(sha(base) == WRAPPER_HASH, "Default wrapper hash differs")
    slots = parameter_slots(config)
    fields = ["MulticopterModelClass::Exp1_MinModelTemp_P." + n + ("[" + str(i) + "]" if i is not None else "") for n, i, _ in slots]
    checks = " && ".join(f"{field} == {repr(value)}" for field, (_, _, value) in zip(fields, slots))
    require(base.count(b"    try {") == 1 and base.count(b"    auto* model = static_cast<MulticopterModelClass*>(handle);") == 2, "Base wrapper mapping differs")
    base = base.replace(b"    try {", ("    static bool used = false;\n    if (used || !(" + checks + ")) return nullptr;\n    used = true;\n    try {").encode())
    marker = b"    std::copy_n(commands, count, model->Exp1_MinModelTemp_U.inPWMs);"
    require(base.count(marker) == 1, "Step mapping differs")
    base = base.replace(marker, b"    for (int i = 6; i < count; ++i) if (commands[i] != 0) return 1;\n" + marker)
    extra = '\nextern "C" const char* wk_hex_identity() { return "' + config["model_identity"] + '"; }\n'
    extra += 'extern "C" double wk_hex_parameter(int index) {\n    switch (index) {\n'
    extra += "".join(f"    case {i}: return {field};\n" for i, field in enumerate(fields))
    extra += '    default: return NAN;\n    }\n}\n'
    return base + extra.encode()


def build(config, archive=ARCHIVE):
    config = validate(config)
    require(platform.system() == "Linux", "Use Ubuntu-22.04 WSL for the native build profile")
    require(sha(Path(archive).read_bytes()) == EXPECTED_HASH, "Archive SHA256 differs")
    # WSL can remove /tmp between CLI invocations. Retain the private build on
    # the Linux filesystem so a subsequent explicit import has the actual files.
    private = Path.home() / "wksim-hex-candidate-private"
    private.mkdir(mode=0o700, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="build-", dir=private))
    with zipfile.ZipFile(archive) as zipped:
        for member in MEMBERS:
            require(zipped.getinfo(member).file_size <= 2_000_000, "Unexpected member size")
            (folder / Path(member).name).write_bytes(zipped.read(member))
    for name, expected in RAW_HASHES.items():
        require(sha((folder / name).read_bytes()) == expected, "Raw member hash differs: " + name)
    source = folder / "Exp1_MinModelTemp.cpp"
    raw = source.read_bytes()
    (folder / "Exp1_MinModelTemp.original.cpp").write_bytes(raw)
    source.write_bytes(parameterize_source(raw, config))
    (folder / "hex_wrapper.cpp").write_bytes(wrapper_source(config))
    write_json(config, folder / "config.json")
    library = folder / LIBRARY
    argv = ["g++", "-std=c++17", "-O2", "-fno-fast-math", "-fPIC", "-shared", "-Wl,--no-undefined",
            "-I", str(folder), str(source), str(folder / "hex_wrapper.cpp"), "-o", str(library)]
    manifest = {"schema": "wksim.hex-build.v1", "config": config, "archive": str(archive), "argv": argv,
                "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
                "builder_sha256": sha(Path(__file__).read_bytes()), "files_sha256": {}}
    write_json(manifest, folder / "build-request.json")
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    (folder / "build.stdout.log").write_text(result.stdout, encoding="utf-8")
    (folder / "build.stderr.log").write_text(result.stderr, encoding="utf-8")
    require(result.returncode == 0, "Build failed; retained evidence: " + str(folder))
    names = [*RAW_HASHES, "Exp1_MinModelTemp.original.cpp", "hex_wrapper.cpp", LIBRARY, "config.json"]
    manifest["files_sha256"] = {n: sha((folder / n).read_bytes()) for n in names}
    write_json(manifest, folder / "build.json")
    return library


def verify_build(library, config):
    config = validate(config)
    library = Path(library).resolve()
    manifest = read_json(library.parent / "build.json")
    require(manifest["config"] == config and load_config(library.parent / "config.json") == config, "Build config identity differs")
    names = {*RAW_HASHES, "Exp1_MinModelTemp.original.cpp", "hex_wrapper.cpp", LIBRARY, "config.json"}
    require(library.name == LIBRARY and set(manifest["files_sha256"]) == names, "Incomplete build artifact manifest")
    for name, expected in manifest["files_sha256"].items():
        require(sha((library.parent / name).read_bytes()) == expected, "Build artifact hash differs: " + name)
    original = (library.parent / "Exp1_MinModelTemp.original.cpp").read_bytes()
    require((library.parent / "Exp1_MinModelTemp.cpp").read_bytes() == parameterize_source(original, config), "Configured source recipe differs")
    require((library.parent / "hex_wrapper.cpp").read_bytes() == wrapper_source(config), "Configured wrapper recipe differs")
    for name, expected in RAW_HASHES.items():
        if name.endswith(".h"):
            require(sha((library.parent / name).read_bytes()) == expected, "Pinned header differs: " + name)
    return library


class HexModel(Model):
    """Source/readback verified before initialization; one lifetime per process."""
    _used_pid = None

    def __init__(self, library, config):
        self.handle = None
        library = verify_build(library, config)
        require(HexModel._used_pid != os.getpid(), "A fresh process is required for every Hex vehicle lifetime")
        # Load solely to inspect generated static parameters; wk_model_create has
        # not been called. The native create function also checks all values.
        loaded = ctypes.CDLL(str(library))
        loaded.wk_hex_identity.restype = ctypes.c_char_p
        loaded.wk_hex_parameter.argtypes = [ctypes.c_int]
        loaded.wk_hex_parameter.restype = ctypes.c_double
        require(loaded.wk_hex_identity().decode() == config["model_identity"], "Compiled Hex identity differs before initialize")
        self.readback = {}
        for slot, (name, index, expected) in enumerate(parameter_slots(config)):
            value = loaded.wk_hex_parameter(slot)
            require(value == expected, "Actual parameter differs before initialize: " + name)
            if index is None:
                self.readback[name] = value
            else:
                self.readback.setdefault(name, []).append(value)
        HexModel._used_pid = os.getpid()
        super().__init__(library)

    def step(self, commands, steps=1):
        require(self.handle is not None, "Hex model is closed")
        require(len(commands) == 16 and all(x == 0 for x in commands[6:]), "Hex unused channels 6..15 must be zero")
        require(type(steps) is int, "Steps must be an integer")
        return super().step(commands, steps)


def protocol():
    """Static thresholds; publish before any native experiment."""
    signs = [[-1, 0, -1], [1, 0, 1], [1, 1, -1], [-1, -1, 1], [-1, 1, 1], [1, -1, -1]]
    return {"schema": "wksim.hex-static-response-protocol.v1", "recipe": RECIPE,
            "config": make_config(), "source_equations": {"roll": "-R*sin(angle)*Ct*omega^2",
                "pitch": "R*cos(angle)*Ct*omega^2", "yaw": "-Cm*omega^2*source_spin",
                "body_rate_outputs": [27, 28, 29], "source_lines": "raw cpp 4833-4852; 7868-7872"},
            "dt_s": .001, "warmup_ticks": 200, "response_ticks": 10,
            "equal_command": .6, "perturbation": .01, "expected_acceleration_signs": signs,
            "checks": {"stationary_ticks": 200, "stationary_rate_abs_max": 1e-10,
                "equal_rpm_min": 100., "equal_rpm_spread_max": 1e-8,
                "equal_rate_abs_max": 1e-8, "unused_rpm_abs_max": 1e-10,
                "perturbed_rpm_increase_min": .1, "other_rpm_delta_abs_max": 1e-8,
                "nonzero_acceleration_signed_min": 1e-6,
                "nominal_zero_axis_fraction_of_largest_max": .02,
                "cold_restart_all_120_outputs_abs_max": 0.0},
            "lifecycle": "Each stationary/equal/motor/restart trace is a fresh OS process; second create must fail before and after close",
            "negative_inputs": "Reject each nonzero channel 6..15 in Python and native bridge; reject bad size, NaN, infinity, range, config and library",
            "evidence": "Full 120 outputs every tick, raw commands, pre-initialize readback, library/config/protocol hashes and process IDs",
            "scope": "Open-loop static model candidate only; no FC/ROS/UE, hover/flight acceptance or physical-aircraft calibration"}


def worker(library, config, case, output):
    spec = protocol()
    commands = [0.] * 16 if case == "stationary" else [spec["equal_command"]] * 6 + [0.] * 10
    count = spec["checks"]["stationary_ticks"] if case == "stationary" else spec["warmup_ticks"] + spec["response_ticks"]
    evidence = {"case": case, "pid": os.getpid(), "model_identity": config["model_identity"],
                "library_sha256": sha(Path(library).read_bytes()), "samples": [], "negative_checks": []}
    with HexModel(library, config) as model:
        evidence["pre_initialize_readback"] = model.readback
        for channel in range(6, 16):
            bad = [0.] * 16
            bad[channel] = .1
            try:
                model.step(bad)
                raise AssertionError("Python accepted unused channel")
            except ValueError:
                pass
            native = (ctypes.c_double * 16)(*bad)
            require(model.library.wk_model_step(model.handle, native, 16, 1, model._output, 120) == 1, "Native accepted unused channel")
            evidence["negative_checks"].append("unused-channel-" + str(channel))
        require(not model.library.wk_model_create(), "Native allowed concurrent second lifetime")
        for tick in range(count):
            current = commands.copy()
            if case.startswith("motor-") and tick >= spec["warmup_ticks"]:
                current[int(case.split("-")[1])] += spec["perturbation"]
            evidence["samples"].append({"tick": tick + 1, "commands": current, "output": model.step(current)})
    require(not model.library.wk_model_create(), "Native allowed restart after close")
    try:
        HexModel(library, config)
        raise AssertionError("Python allowed restart")
    except ValueError as error:
        require("fresh process" in str(error), "Wrong lifecycle rejection")
    evidence["negative_checks"] += ["native-second-create", "native-post-close-create", "python-post-close-create"]
    write_json(evidence, output)


def run(library, config, protocol_path, output):
    spec = read_json(protocol_path)
    require(canonical(spec) == canonical(protocol()), "Frozen protocol differs")
    require(config == spec["config"], "Run requires the frozen named configuration")
    library = verify_build(library, config)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    protocol_hash = sha(Path(protocol_path).read_bytes())
    write_json({"protocol_sha256": protocol_hash, "library_sha256": sha(library.read_bytes()),
                "runner_sha256": sha(Path(__file__).read_bytes())}, output / "run-request.json")
    traces, processes = {}, []
    for case in ["stationary", "equal", *[f"motor-{i}" for i in range(6)], "restart"]:
        argv = [sys.executable, str(Path(__file__).resolve()), "worker", "--library", str(library),
                "--config", str(library.parent / "config.json"), "--case", case, "--output", str(output / (case + ".json"))]
        started = time.monotonic()
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        (output / (case + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
        require(result.returncode == 0, "Worker failed: " + case)
        traces[case] = read_json(output / (case + ".json"))
        processes.append({"case": case, "pid": traces[case]["pid"], "exit_code": result.returncode,
                          "elapsed_s": time.monotonic() - started, "argv": argv})
    write_json({"processes": processes, "all_exited": all(p["exit_code"] == 0 for p in processes)}, output / "process-completion.json")
    thresholds = spec["checks"]
    checks = {}
    equal = traces["equal"]["samples"]
    final = equal[-1]["output"]
    checks["six_equal_active_rpm"] = min(final[16:22]) > thresholds["equal_rpm_min"] and max(final[16:22]) - min(final[16:22]) <= thresholds["equal_rpm_spread_max"]
    checks["equal_zero_body_rates"] = max(abs(x) for x in final[27:30]) <= thresholds["equal_rate_abs_max"]
    checks["unused_rpm_zero"] = all(max(abs(x) for x in sample["output"][22:24]) <= thresholds["unused_rpm_abs_max"] for trace in traces.values() for sample in trace["samples"])
    checks["stationary_zero_rates_rpm"] = all(max(abs(x) for x in sample["output"][16:24] + sample["output"][27:30]) <= thresholds["stationary_rate_abs_max"] for sample in traces["stationary"]["samples"])
    checks["fresh_processes"] = len({trace["pid"] for trace in traces.values()}) == len(traces)
    checks["cold_restart_exact"] = traces["restart"]["samples"] == equal
    responses = []
    for motor in range(6):
        perturbed = traces[f"motor-{motor}"]["samples"]
        before = spec["warmup_ticks"] - 1
        accel = [(perturbed[-1]["output"][27+a] - perturbed[before]["output"][27+a] - final[27+a] + equal[before]["output"][27+a]) / (spec["response_ticks"] * spec["dt_s"]) for a in range(3)]
        rpm_delta = [perturbed[-1]["output"][16+i] - final[16+i] for i in range(6)]
        signs = spec["expected_acceleration_signs"][motor]
        checks[f"motor_{motor}_rpm_mapping"] = rpm_delta[motor] > thresholds["perturbed_rpm_increase_min"] and all(abs(value) <= thresholds["other_rpm_delta_abs_max"] for i, value in enumerate(rpm_delta) if i != motor)
        checks[f"motor_{motor}_moment_signs"] = all(value * sign > thresholds["nonzero_acceleration_signed_min"] if sign else abs(value) <= thresholds["nominal_zero_axis_fraction_of_largest_max"] * max(abs(v) for v in accel) for value, sign in zip(accel, signs))
        responses.append({"motor": motor, "delta_body_acceleration_rad_s2": accel, "expected_signs": signs, "rpm_delta": rpm_delta})
    summary = {"passed": all(checks.values()), "checks": checks, "responses": responses,
               "protocol_sha256": protocol_hash, "library_sha256": sha(library.read_bytes()),
               "pre_initialize_readback": traces["equal"]["pre_initialize_readback"],
               "six_equal_rpm": final[16:22], "files_sha256": {p.name: sha(p.read_bytes()) for p in output.glob("*.json")}}
    write_json(summary, output / "summary.json")
    require(summary["passed"], "Static response failed; retained evidence: " + str(output))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    save = subs.add_parser("save")
    save.add_argument("--name", default="hex-x-source-template")
    save.add_argument("--output", type=Path, required=True)
    freeze = subs.add_parser("protocol")
    freeze.add_argument("--output", type=Path, required=True)
    for name in ["build", "run", "worker"]:
        command = subs.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        if name == "build":
            command.add_argument("--archive", type=Path, default=ARCHIVE)
        else:
            command.add_argument("--library", type=Path, required=True)
            command.add_argument("--output", type=Path, required=True)
            if name == "run":
                command.add_argument("--protocol", type=Path, required=True)
            else:
                command.add_argument("--case", choices=["stationary", "equal", "restart", *[f"motor-{i}" for i in range(6)]], required=True)
    args = parser.parse_args()
    if args.action == "save":
        write_json(make_config(args.name), args.output)
    elif args.action == "protocol":
        write_json(protocol(), args.output)
    elif args.action == "build":
        print(build(load_config(args.config), args.archive))
    elif args.action == "worker":
        worker(args.library, load_config(args.config), args.case, args.output)
    else:
        print(json.dumps(run(args.library, load_config(args.config), args.protocol, args.output), indent=2))


if __name__ == "__main__":
    main()
