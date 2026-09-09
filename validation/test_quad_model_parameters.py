"""Offline contract tests; --native runs the predeclared isolated response experiment."""
import copy
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Simulator"))
from wksim_core.model_parameters import (RAW_HASHES, load_config, make_config,
                                        parameterize_source, save_config, sha, validate)


class ConfigTests(unittest.TestCase):
    def test_roundtrip_and_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = make_config("payload", 1.818)
            save_config(config, path)
            self.assertEqual(config, load_config(path))
            with self.assertRaises(FileExistsError):
                save_config(make_config(), path)
            self.assertNotEqual(config["model_identity"], make_config("payload", 1.515)["model_identity"])

    def test_invalid_mass(self):
        for value in (True, None, "1.515", 0, -.1, .4999, 5.01, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                make_config(mass_kg=value)

    def test_incomplete_and_tampered(self):
        config = make_config()
        for key in config:
            changed = copy.deepcopy(config)
            del changed[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(changed)
        for path, value in [(('mass', 'value'), 1.818), (('mass', 'unit'), 'g'),
                            (('source', 'archive_sha256'), 'bad'), (('components', 'motor_count'), 6),
                            (('fixed_parameters', 'ModelParam_uavR'), {'value': .3, 'unit': 'm'}),
                            (('components', 'motors'), [])]:
            changed = copy.deepcopy(config)
            changed[path[0]][path[1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate(changed)

    def test_duplicate_and_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            for text in ('{', '{"schema":1,"schema":2}', '[]', '{}'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(path)

    def test_unpinned_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "source hash"):
            parameterize_source(b"// Variable: ModelParam_uavMass\n// ref\n 1.515,", 1.818)

    def test_unique_mass_mapping(self):
        source = b"// Variable: ModelParam_uavMass\n// ref\n 1.515,"
        for ambiguous in (b"no initializer", source + source):
            # Exercise the independent uniqueness gate after the raw hash gate.
            with patch.dict(RAW_HASHES, {"Exp1_MinModelTemp.cpp": sha(ambiguous)}):
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    parameterize_source(ambiguous, 1.818)


def native(evidence):
    """Do not adapt this protocol to observed data; failures remain in evidence."""
    evidence = Path(evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    cli = ROOT / "tools/quad_model_parameters.py"
    baseline = make_config("static-baseline", 1.515)
    heavier = make_config("static-heavier", 1.818)
    save_config(baseline, evidence / "baseline.json")
    save_config(heavier, evidence / "heavier.json")
    protocol = {"protocol": "quad-mass-static-v1", "frozen_before_build_or_response": True,
                "config_pair": [baseline, heavier], "initial_state": "pinned defaults: zero position/attitude/velocity/motor speed",
                "commands": [.8] * 4 + [0.] * 12, "ticks": 500, "dt_s": .001,
                "observables": {"up_velocity_m_s": "-output120[5]", "height_m": "-output120[8]", "motor_rpm": "output120[16:20]"},
                "expected": ["at tick 500: baseline upward velocity > heavier upward velocity > 0",
                             "at tick 500: baseline height > heavier height > 0",
                             "all motor RPM samples equal for the two masses",
                             "export/import rebuild reproduces identity, applied mass, and every output sample"],
                "basis": "Pinned cpp 4833-4834: T=Ct*omega^2; 4955-4963: force divided by mass. Equal four 0.8 commands exceed weight for both masses; ground release can delay heavier response. This is a directional response check, no fitted numerical tolerance or G6 accuracy claim.",
                "raw_source_sha256": RAW_HASHES["Exp1_MinModelTemp.cpp"],
                "test_source_sha256": sha(Path(__file__).read_bytes())}
    (evidence / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    traces = {}
    libraries = {}
    subprocess.run([sys.executable, str(cli), "export", str(evidence / "heavier.json"), str(evidence / "imported.json")], check=True, stdout=subprocess.DEVNULL)
    for name in ("baseline", "heavier", "imported"):
        result = subprocess.run([sys.executable, str(cli), "build", str(evidence / (name + ".json"))], capture_output=True, text=True)
        (evidence / (name + ".build.log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        result.check_returncode()
        library = result.stdout.strip()
        libraries[name] = library
        run = subprocess.run([sys.executable, str(cli), "run", str(evidence / (name + ".json")), library,
                              str(evidence / (name + ".jsonl")), "--commands", ".8", ".8", ".8", ".8", "--ticks", "500"], capture_output=True, text=True)
        (evidence / (name + ".run.log")).write_text(run.stdout + run.stderr, encoding="utf-8")
        run.check_returncode()
        traces[name] = [json.loads(line) for line in (evidence / (name + ".jsonl")).read_text().splitlines()]
    b, h, i = (traces[n] for n in ("baseline", "heavier", "imported"))
    checks = {"lighter_up_velocity_greater": -b[-1]["output120"][5] > -h[-1]["output120"][5] > 0,
              "lighter_height_greater": -b[-1]["output120"][8] > -h[-1]["output120"][8] > 0,
              "same_motor_response": all(x["output120"][16:20] == y["output120"][16:20] for x, y in zip(b[1:], h[1:])),
              "reimport_same_identity_and_mass": h[0]["config"] == i[0]["config"] and h[0]["applied_mass_kg_before_step"] == i[0]["applied_mass_kg_before_step"] == 1.818,
              "reimport_same_native_response": h[1:] == i[1:],
              "sample_counts": all(len(t) == 501 for t in (b, h, i))}
    # Reject cross-configuration library use before any sample is emitted.
    mismatch = subprocess.run([sys.executable, str(cli), "run", str(evidence / "heavier.json"), libraries["baseline"],
                               str(evidence / "rejected-mismatch.jsonl"), "--commands", ".8", ".8", ".8", ".8"], capture_output=True, text=True)
    (evidence / "rejected-mismatch.log").write_text(mismatch.stdout + mismatch.stderr, encoding="utf-8")
    checks["wrong_model_rejected"] = mismatch.returncode != 0 and "build config identity differs" in mismatch.stderr
    tampered = evidence / "tampered-build"
    shutil.copytree(Path(libraries["baseline"]).parent, tampered)
    with (tampered / "libwksim_configured.so").open("ab") as stream:
        stream.write(b"tampered-test")
    rejected = subprocess.run([sys.executable, str(cli), "run", str(evidence / "baseline.json"), str(tampered / "libwksim_configured.so"),
                               str(evidence / "rejected-tamper.jsonl"), "--commands", ".8", ".8", ".8", ".8"], capture_output=True, text=True)
    (evidence / "rejected-tamper.log").write_text(rejected.stdout + rejected.stderr, encoding="utf-8")
    checks["tampered_library_rejected"] = rejected.returncode != 0 and "build artifact hash differs" in rejected.stderr
    bad_archive = evidence / "invalid-source.zip"
    bad_archive.write_bytes(b"not the pinned default model archive")
    rejected = subprocess.run([sys.executable, str(cli), "build", str(evidence / "baseline.json"), "--archive", str(bad_archive)], capture_output=True, text=True)
    (evidence / "rejected-archive.log").write_text(rejected.stdout + rejected.stderr, encoding="utf-8")
    checks["unreviewed_archive_rejected"] = rejected.returncode != 0 and "Unreviewed model archive" in rejected.stderr
    probe = """import sys
sys.path.insert(0, sys.argv[1])
from wksim_core.model_parameters import ConfiguredModel, load_config
config = load_config(sys.argv[2])
with ConfiguredModel(sys.argv[3], config) as model:
    try:
        model.step([.8]*4+[1.]+[0.]*11)
    except ValueError:
        print('unused-channel-rejected')
    else:
        raise AssertionError('unused channel accepted')
try:
    ConfiguredModel(sys.argv[3], config)
except RuntimeError as error:
    assert 'fresh process' in str(error)
    print('second-lifetime-rejected')
else:
    raise AssertionError('second lifetime accepted')
"""
    rejected = subprocess.run([sys.executable, "-c", probe, str(ROOT / "Simulator"), str(evidence / "baseline.json"), libraries["baseline"]], capture_output=True, text=True)
    (evidence / "runtime-guards.log").write_text(rejected.stdout + rejected.stderr, encoding="utf-8")
    checks["unused_channel_and_second_lifetime_rejected"] = rejected.returncode == 0 and "second-lifetime-rejected" in rejected.stdout
    summary = {"checks": checks, "passed": all(checks.values()), "libraries": libraries,
               "protocol_sha256": sha((evidence / "protocol.json").read_bytes()),
               "final": {n: {"mass_kg": t[0]["applied_mass_kg_before_step"], "up_velocity_m_s": -t[-1]["output120"][5],
                             "height_m": -t[-1]["output120"][8], "motor_rpm": t[-1]["output120"][16:20]} for n, t in traces.items()}}
    (evidence / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["passed"]:
        raise RuntimeError("predeclared static response failed; evidence retained")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--native":
        native(sys.argv[2])
    else:
        unittest.main()
