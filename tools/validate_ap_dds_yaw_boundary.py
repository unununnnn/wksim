"""Compile the candidate DDS handler with its generated types and typed recorders.

No FC/network runs here. This checks dispatch and input validation, not Guided,
fences, real AP math internals, message transport, or flight behavior.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

REPO = Path(__file__).resolve().parent.parent
PIN = "1511f27194f1dcc3728270883047bdf022b3fd53"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    if candidate.parent != Path("/root") or not candidate.name.startswith("wksim-ap-dds-yaw-"):
        parser.error("Requires isolated /root/wksim-ap-dds-yaw-* workspace in WSL")
    source = candidate / "src/libraries/AP_DDS/AP_DDS_ExternalControl.cpp"
    revision = subprocess.check_output(["git", "-C", str(candidate / "src"), "rev-parse", "HEAD"], text=True).strip()
    if revision != PIN:
        raise ValueError("Unexpected ArduPilot source revision")
    evidence = Path(tempfile.mkdtemp(prefix="ap-dds-yaw-boundary-", dir=REPO / "validation"))
    work = Path(tempfile.mkdtemp(prefix="wksim-ap-dds-unit-", dir="/root"))
    text = source.read_text()
    handler = text[text.index("bool AP_DDS_External_Control::handle_global_position_control("):
                   text.index("bool AP_DDS_External_Control::handle_velocity_control(")]
    altitude = text[text.index("bool AP_DDS_External_Control::convert_alt_frame("):text.index("#endif // AP_DDS_ENABLED")]
    # Generated fragments live outside the repository, as in the Prometheus oracle.
    (work / "firmware_position_methods.inc").write_text(handler + "\n" + altitude)
    generated = candidate / "build/sitl/libraries/AP_DDS/generated"
    command = ["g++", "-std=c++17", "-O1", "-g", "-fsanitize=undefined,float-cast-overflow",
               "-fno-sanitize-recover=all", "-Wall", "-Wextra", "-I", str(work), "-I", str(generated),
               str(REPO / "validation/ap_dds_yaw_boundary.cpp"), "-o", str(work / "boundary")]
    result = {"status": "failed", "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "scope": __doc__, "candidate": str(candidate), "work": str(work), "revision": revision,
              "build_command": command, "sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [source, Path(__file__), REPO / "validation/ap_dds_yaw_boundary.cpp",
                        work / "firmware_position_methods.inc", *sorted(generated.rglob("*.h"))]}}
    try:
        with (evidence / "build.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        run = subprocess.run([str(work / "boundary")], capture_output=True, text=True, check=True, timeout=10)
        (evidence / "run.log").write_text(run.stdout + run.stderr)
        result.update(json.loads(run.stdout))
    except (subprocess.SubprocessError, ValueError) as error:
        result["error"] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            (evidence / "failure.log").write_text(str(error.stdout) + "\n" + str(error.stderr))
    (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"result_dir": str(evidence), **{k: result[k] for k in ("status", "assertions", "error") if k in result}}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
