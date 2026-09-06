#!/usr/bin/env python3
"""Submit cancellation for an explicitly selected local wksim mission."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Simulator"))
from wksim_runtime.mission_cancel import request_cancel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", metavar="RUN_DIRECTORY")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mission-id", required=True)
    args = parser.parse_args()
    try:
        request = request_cancel(args.run_directory, args.run_id, args.mission_id)
    except (OSError, ValueError) as exc:
        print("Cancellation request rejected: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(request, sort_keys=True))
    print("Request submitted only; this is NOT confirmation of cancellation or "
          "landing. Check mission-status.json for the runtime outcome.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
