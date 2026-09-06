"""Submit a local operator action. Atomic submission is NOT action completion."""

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Simulator"))
from wksim_runtime.mission_actions import request_action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="local run directory")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--action", required=True, choices=("pause", "resume"))
    args = parser.parse_args()
    try:
        request = request_action(args.directory, args.run_id, args.mission_id,
                                 args.token, args.action)
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"submitted": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"submitted": True, "request": request,
                      "message": "Atomic submission is NOT action completion; await runtime status."}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
