#!/usr/bin/env python3
"""Read-only integrity check for this directory's SHA256SUMS.

Re-hashes every listed file and reports mismatches, unlisted files and stale
entries.  Never writes anything.  Exit status is 0 when the record is complete
and consistent.
"""

import hashlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SUMS = HERE / "SHA256SUMS"


def main(argv=None):
    if not SUMS.is_file():
        print("FAIL: SHA256SUMS is missing")
        return 1
    listed = {}
    for line in SUMS.read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        listed[name] = digest

    ok = 0
    mismatches = []
    for name, digest in sorted(listed.items()):
        target = HERE / name
        if not target.is_file():
            mismatches.append((name, "missing"))
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual == digest:
            ok += 1
        else:
            mismatches.append((name, f"expected {digest}, got {actual}"))

    present = {
        p.name for p in HERE.iterdir() if p.is_file() and p.name != "SHA256SUMS"
    }
    unlisted = sorted(present - set(listed))
    stale = sorted(set(listed) - present)

    print(f"verified_ok={ok}")
    print(f"mismatches={len(mismatches)}")
    for name, reason in mismatches:
        print(f"  MISMATCH {name}: {reason}")
    print(f"unlisted_files={unlisted or 'none'}")
    print(f"stale_entries={stale or 'none'}")
    print(f"total_files={len(present) + 1}")

    clean = not mismatches and not unlisted and not stale
    print("status=" + ("consistent" if clean else "inconsistent"))
    return 0 if clean else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
