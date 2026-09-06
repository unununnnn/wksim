"""Compare the actual PX4 DDS bridge schemas against the built ROS message source.

Ignore comments/formatting only; fields, their order, constants and nested types
must match. Fail closed on missing/ambiguous files. No network or FC mutation.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re

import yaml


def declarations(path):
    return [re.sub(r"\s+", "", line.split("#", 1)[0])
            for line in path.read_text().splitlines() if line.split("#", 1)[0].strip()]


def check(px4, messages):
    topics = yaml.safe_load((px4 / "src/modules/uxrce_dds_client/dds_topics.yaml").read_text())
    pending = {entry["type"].split("::")[-1]
               for entries in topics.values() if isinstance(entries, list)
               for entry in entries}
    checked = {}
    while pending:
        name = pending.pop()
        if name in checked:
            continue
        candidates = [p for p in (px4 / "msg" / f"{name}.msg", px4 / "msg/versioned" / f"{name}.msg") if p.is_file()]
        if len(candidates) != 1:
            raise ValueError(f"Expected exactly one PX4 source for {name}: {candidates}")
        original, ros = candidates[0], messages / "msg" / f"{name}.msg"
        left, right = declarations(original), declarations(ros)
        checked[name] = {"match": left == right, "px4_source": str(original), "ros_source": str(ros),
                         "px4_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                         "ros_sha256": hashlib.sha256(ros.read_bytes()).hexdigest(),
                         "difference": list(difflib.unified_diff(left, right, fromfile="px4", tofile="ros", lineterm=""))}
        for line in original.read_text().splitlines():
            tokens = line.split("#", 1)[0].split()
            if tokens and re.match(r"^[A-Z]", tokens[0]):
                pending.add(tokens[0].split("[", 1)[0])
    return {"status": "pass" if all(item["match"] for item in checked.values()) else "failed",
            "schemas": dict(sorted(checked.items())), "bridge_topics": topics}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("px4", type=Path)
    parser.add_argument("messages", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.px4, args.messages)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "checked": len(result["schemas"]),
                      "mismatches": [name for name, item in result["schemas"].items() if not item["match"]],
                      "output": str(args.output)}))
    raise SystemExit(0 if result["status"] == "pass" else 1)
