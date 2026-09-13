#!/usr/bin/env python3
"""Render a short human-readable summary of recheck-output.json (read-only)."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE / "recheck-output.json"


def main(argv=None):
    source = Path(argv[1]) if argv and len(argv) > 1 else REPORT
    data = json.loads(source.read_text(encoding="utf-8"))
    out = []
    out.append(f"head={data['head']}")
    out.append(f"ancestry_pin_is_ancestor={data['ancestry_pin_is_ancestor']}")
    out.append(f"evidence_pins_intact={data['evidence_pins_intact']}")
    out.append(f"status={data['status']}")
    out.append(f"current_wrapper_tracked_at_head={data.get('current_wrapper_tracked_at_head')}")
    out.append("")
    out.append("wrapper pins:")
    for pin in data["wrapper_pins"]:
        out.append(
            "  {build_id:20s} pin={sha} {size:>6} B  matches_current={match!s:5s} "
            "preserved_copies={copies} {example}".format(
                build_id=pin["build_id"],
                sha=pin["pinned_sha256"][:12],
                size=pin["pinned_size_bytes"],
                match=pin["matches_current_tracked_source"],
                copies=pin["preserved_copy_count"],
                example=pin["preserved_copy_example"] or "-",
            )
        )
    out.append("")
    out.append("findings:")
    for item in data["findings"]:
        out.append(f"  [{item['severity']:4s}] {item['id']}")
        out.append(f"        {item['message']}")
    out.append("")
    out.append(
        f"vendor_regex_hit_count={data['vendor_regex_hit_count']} "
        f"classes={data['vendor_regex_hit_classes']} "
        f"real_vendor_material={data['real_vendor_material_count']}"
    )
    out.append("")
    out.append("evidence pins:")
    for pin in data["evidence_pins"]:
        out.append(f"  intact={pin['intact']!s:5s} {pin['path']}")
    text = "\n".join(out) + "\n"
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
