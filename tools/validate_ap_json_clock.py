"""Compile actual SIM_JSON clock and Aircraft::time_advance in a recorder fixture.

No simulation, hardware or network. This checks only the extracted clock boundary.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

REPO = Path(__file__).resolve().parent.parent
PIN = "1511f27194f1dcc3728270883047bdf022b3fd53"


def extract_clock(source):
    starts = ["    double deltat;", "    // Quantize absolute JSON time once; never truncate each floating-point delta."]
    matches = [(source.index(marker), marker) for marker in starts if marker in source]
    if len(matches) != 1:
        raise ValueError("Expected exactly one known JSON clock boundary")
    start, marker = matches[0]
    end = source.index("    frame_counter++;", start) + len("    frame_counter++;")
    return source[start:end] + "\n", marker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    if candidate.parent != Path("/root") or not candidate.name.startswith(("wksim-ap-dds-yaw-", "wksim-ap-clock-stop-")):
        parser.error("Requires isolated /root/wksim-ap-dds-yaw-* or /root/wksim-ap-clock-stop-* workspace in WSL")
    src = candidate / "src"
    revision = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    if revision != PIN:
        raise ValueError("Unexpected ArduPilot source revision")
    evidence = Path(tempfile.mkdtemp(prefix="ap-json-clock-boundary-", dir=REPO / "validation"))
    work = Path(tempfile.mkdtemp(prefix="wksim-ap-clock-unit-", dir="/root"))
    paths = [src / "libraries/SITL/SIM_JSON.cpp", src / "libraries/SITL/SIM_Aircraft.cpp",
             src / "libraries/AP_Math/AP_Math.h", Path(__file__), REPO / "validation/ap_json_clock_boundary.cpp"]
    snapshots = {p: p.read_bytes() for p in paths}
    result = {"status": "failed", "phase": "extract", "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "scope": __doc__, "candidate": str(candidate), "revision": revision, "work": str(work),
              "sha256": {str(p): hashlib.sha256(data).hexdigest() for p, data in snapshots.items()}}
    try:
        block, marker = extract_clock(snapshots[paths[0]].decode())
        aircraft = snapshots[paths[1]].decode()
        method = re.search(r"^void Aircraft::time_advance\(\)\s*\n\{.*?^\}", aircraft, re.M | re.S)
        if method is None:
            raise ValueError("Actual Aircraft::time_advance definition missing")
        math = snapshots[paths[2]].decode()
        positive = re.search(r"^inline bool is_positive\(const double fVal1\)\s*\{.*?^\}", math, re.M | re.S)
        if positive is None:
            raise ValueError("Actual double is_positive definition missing")
        fragments = {"json_clock.inc": block, "aircraft_time.inc": method.group() + "\n",
                     "positive.inc": positive.group() + "\n"}
        for name, value in fragments.items():
            (work / name).write_text(value)
            (evidence / name).write_text(value)
            result["sha256"][name] = hashlib.sha256(value.encode()).hexdigest()
        result["clock_start"] = marker
        command = ["g++", "-std=c++17", "-O1", "-g", "-fsanitize=undefined,float-cast-overflow",
                   "-fno-sanitize-recover=all", "-Wall", "-Wextra", "-I", str(work),
                   str(paths[-1]), "-o", str(work / "boundary")]
        result.update(phase="build", build_command=command)
        build = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (evidence / "build.log").write_text(build.stdout + build.stderr)
        result["build_returncode"] = build.returncode
        build.check_returncode()
        result.update(phase="run", cases=[])
        for case in ("1ms-10004", "1ms-long", "4ms", "duplicate", "fractional", "fractional-drift", "reset", "sync-disabled", "no-lockstep", "invalid", "overflow"):
            run = subprocess.run([str(work / "boundary"), case], capture_output=True, text=True, timeout=20)
            (evidence / (case + ".log")).write_text(run.stdout + run.stderr)
            result["cases"].append({"name": case, "returncode": run.returncode,
                                    "stdout": run.stdout, "stderr": run.stderr})
        result["status"] = "pass" if all(c["returncode"] == 0 for c in result["cases"]) else "failed"
        result["phase"] = "complete"
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result["error"] = str(error)
    result["source_unchanged_during_run"] = all(p.read_bytes() == data for p, data in snapshots.items())
    if not result["source_unchanged_during_run"]:
        result.update(status="failed", error="Inputs changed during run; rerun against a stable source")
    (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    (evidence / "report.md").write_text(
        f"# AP JSON clock boundary\n\nStatus: {result['status']}; phase: {result['phase']}.\n\n"
        f"Candidate: {candidate}\n\nRevision: {revision}\n\n"
        + "\n".join(f"- {c['name']}: exit {c['returncode']}; {c['stdout'].strip()} {c['stderr'].strip()}"
                    for c in result.get("cases", []))
        + "\n\nActual source fragments and SHA256 provenance are archived alongside result.json. "
        "Only sync/adjust callbacks are recorders; Aircraft::time_advance and the JSON clock execute extracted source. "
        "No full firmware, transport, simulation or hardware validation is implied.\n")
    print(json.dumps({"result_dir": str(evidence), "status": result["status"], "phase": result["phase"]}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
