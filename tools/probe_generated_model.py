"""Run in WSL: extract known local model inputs to /tmp, build, and run bounded checks.

No vendor material is copied into this repository. Original files are not edited.
This probe does not start CopterSim, MATLAB, flight controllers, or network clients.
"""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from Simulator.wksim_core.model import ARCHIVE, EXPECTED_HASH, extract_source


def main():
    if platform.system() != "Linux":
        raise SystemExit("Run with Ubuntu-22.04 WSL python3")
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if digest != EXPECTED_HASH:
        raise SystemExit("Archive differs from reviewed source; inspect it before updating this probe")
    repo = Path(__file__).resolve().parent.parent
    result_dir = Path(tempfile.mkdtemp(prefix="generated-model-", dir=repo / "validation"))
    build_dir = extract_source()
    result = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "scope": "One unchanged generated model; no FC, DDS, UE, physics equivalence or full-product validation",
              "archive": str(ARCHIVE), "archive_sha256": digest,
              "build_dir": str(build_dir), "result_dir": str(result_dir),
              "platform": platform.platform(), "commands": [], "status": "failed"}

    def command(args, label, timeout=30):
        started = time.monotonic()
        process = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        (result_dir / f"{label}.stdout.log").write_text(process.stdout, encoding="utf-8")
        (result_dir / f"{label}.stderr.log").write_text(process.stderr, encoding="utf-8")
        result["commands"].append({"argv": args, "label": label, "returncode": process.returncode,
                                   "seconds": time.monotonic() - started})
        if process.returncode:
            raise RuntimeError(f"{label} failed: {process.stderr[-2000:]}")
        return process.stdout

    try:
        result["compiler"] = command(["g++", "--version"], "compiler").splitlines()[0]
        executable = str(build_dir / "model-check")
        command(["g++", "-std=c++17", "-O2", "-fno-fast-math", "-I", str(build_dir),
                 str(build_dir / "Exp1_MinModelTemp.cpp"),
                 str(repo / "tools/generated_model_check.cpp"), "-o", executable], "build", 60)
        result["dynamic_libraries"] = command(["ldd", executable], "dependencies")
        output = command(["timeout", "10s", executable], "model-check", 15)
        result["checks"] = json.loads(output)
        result["status"] = result["checks"]["status"]
        result["executable_sha256"] = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
    except Exception as error:
        result["error"] = str(error)
    finally:
        result["source_unchanged"] = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == digest
        (result_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items()
                          if key not in ("checks", "dynamic_libraries")}, indent=2))
        if "checks" in result:
            print(json.dumps({key: value for key, value in result["checks"].items()
                              if key not in ("idle", "powered", "repeated")}, indent=2))
    return 0 if result["status"] == "pass" and result["source_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
