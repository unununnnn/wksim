#!/usr/bin/env python3
"""Read-only, pure-Python recheck of the #26 pin-drift adjudication.

This script is an *independent* re-derivation.  It does not import, patch or
replace ``tools/audit_26_closure_readiness.py`` and it never writes to any
tracked path.  It only reads repository files, runs read-only ``git`` plumbing
and prints a JSON report on stdout.

Checks performed
----------------
1. ``git rev-parse HEAD`` and ``git merge-base --is-ancestor <pin> HEAD``.
2. Every ``acceptance_evidence.*.pins[*]`` entry of the closure-readiness
   manifest is re-hashed from bytes.
3. The lifecycle ``audit.json`` is re-hashed and cross-compared against the
   manifest's pinned ``requirements`` block.
4. For each ``build-manifest.json`` the ``staged_sources.model.cpp`` pin is
   compared with the current tracked ``Simulator/wksim_core/model.cpp``.
5. ``git cat-file -e`` decides whether each pinned ``model.cpp`` digest is an
   object this checkout can reproduce at all (i.e. whether the historical
   pin is *recoverable from git*).
6. The set of tracked paths matched by the auditor's vendor regex is listed
   and each is content-classified so a filename-only match can be told apart
   from real vendor bytes.

Usage (pure Python, no third-party imports)::

    python validation/coordination/ds-26-pin-drift-20260913-01/recheck_26_pin_drift.py
    python validation/coordination/ds-26-pin-drift-20260913-01/recheck_26_pin_drift.py --json

Exit status is ``0`` when the report was produced, regardless of findings;
findings are data, not process failure.  ``--fail-on-drift`` opts into a
non-zero exit so the script can be used as a gate.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = "docs/plan/26-closure-readiness-manifest.json"
CURRENT_WRAPPER = "Simulator/wksim_core/model.cpp"
ANCESTRY_PIN = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
# Verbatim from tools/audit_26_closure_readiness.py:932 -- do not "improve"
# this locally; the point of the recheck is to reproduce the auditor's own
# classifier and then show what it actually matched.
VENDOR_RE = re.compile(r"(?:\.dll$|\.zip$|rflysim)", re.IGNORECASE)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_KEYS = {"checked_unix", "distro", "boot_id", "uptime", "found"}


def git(*args):
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, timeout=120
    )
    return completed.returncode, completed.stdout.decode("utf-8", "replace").strip()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_object_exists(digest):
    code, _ = git("cat-file", "-e", digest)
    return code == 0


def tracked_model_cpp_copies():
    """Tracked paths named ``model.cpp`` except the canonical wrapper itself.

    These are frozen per-run source snapshots.  They are the only in-repository
    place a historical wrapper can survive after the canonical path moved on.
    """
    code, raw = git("ls-files", "-z", "--", "*model.cpp")
    if code != 0:
        return []
    paths = [item for item in raw.split("\0") if item]
    return [
        path for path in paths
        if path != CURRENT_WRAPPER and path.endswith("model.cpp")
    ]


def find_preserved_copies(digest, cache):
    """Return tracked snapshot paths whose bytes hash to *digest*."""
    if digest in cache:
        return cache[digest]
    matches = []
    for path in tracked_model_cpp_copies():
        full = ROOT / path
        try:
            if full.is_file() and sha256_file(full) == digest:
                matches.append(path)
        except OSError:
            continue
    cache[digest] = matches
    return matches


def wrapper_is_tracked_at_head():
    """Whether the current canonical wrapper is tracked and clean at HEAD."""
    code, _ = git("status", "--porcelain", "--", CURRENT_WRAPPER)
    if code != 0:
        return None
    code, tracked = git("ls-files", "--error-unmatch", "--", CURRENT_WRAPPER)
    if code != 0:
        return False
    return tracked != ""


def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def classify_path(path):
    """Return a content class for a tracked path hit by the vendor regex.

    The classification is content-based on purpose: the point of the finding is
    that the auditor's rule decides on the *path text* alone, so the recheck has
    to look at what the bytes actually are.
    """
    lowered = path.lower()
    if lowered.endswith(".dll"):
        return "vendor-dll-name"
    if lowered.endswith(".zip"):
        return "vendor-zip-name"
    full = ROOT / path
    try:
        raw_bytes = full.read_bytes()
    except OSError:
        return "unreadable"
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return "binary-content"
    if "\x00" in text:
        return "binary-content"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "text-precheck-note" if "checked_unix" in text else "text-other"
    if isinstance(payload, dict) and RECEIPT_KEYS.issubset(payload):
        return "wsl-precheck-receipt-empty" if payload.get("found") == [] else "wsl-precheck-receipt-nonempty"
    return "json-other"


def repo_relative_source(source_path):
    """Mirror the auditor's mapping of a Windows provenance path to the repo."""
    if source_path.startswith(str(ROOT)):
        return Path(source_path).relative_to(ROOT).as_posix()
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="pretty JSON only")
    parser.add_argument("--fail-on-drift", action="store_true")
    args = parser.parse_args(argv)

    report = {"schema": "wksim.26-pin-drift-recheck.v1", "findings": []}
    def finding(fid, severity, message, evidence=None):
        item = {"id": fid, "severity": severity, "message": message}
        if evidence is not None:
            item["evidence"] = evidence
        report["findings"].append(item)

    code, head = git("rev-parse", "HEAD")
    report["head"] = head
    report["head_resolved"] = code == 0

    code, _ = git("merge-base", "--is-ancestor", ANCESTRY_PIN, "HEAD")
    report["ancestry_pin"] = ANCESTRY_PIN
    report["ancestry_pin_is_ancestor"] = code == 0
    if code != 0:
        finding("ANCESTRY", "P0", "required architecture commit is not an ancestor of HEAD")

    # --- 1. manifest evidence pins -----------------------------------------
    manifest = read_json(MANIFEST)
    pin_results = []
    for ac_key, entry in manifest["acceptance_evidence"].items():
        for pin in entry["pins"]:
            path = pin["path"]
            full = ROOT / path
            exists = full.is_file()
            actual = sha256_file(full) if exists else None
            pin_results.append(
                {
                    "ac": ac_key,
                    "path": path,
                    "pinned_sha256": pin["sha256"],
                    "actual_sha256": actual,
                    "intact": actual == pin["sha256"],
                }
            )
            if not exists:
                finding("PIN-MISSING", "P0", f"pinned evidence missing: {path}")
            elif actual != pin["sha256"]:
                finding("PIN-DRIFT", "P0", f"pinned evidence drifted: {path}")
    report["evidence_pins"] = pin_results
    report["evidence_pins_intact"] = all(item["intact"] for item in pin_results)

    # --- 2. lifecycle audit cross-binding ----------------------------------
    lifecycle_rel = "validation/codegen-e0-lifecycle-01/audit.json"
    audit = read_json(lifecycle_rel)
    req = manifest["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]
    binding = {
        "audit_sha256": sha256_file(ROOT / lifecycle_rel),
        "audit_sha256_matches_lifecycle_pin": any(
            item["path"] == lifecycle_rel and item["intact"] for item in pin_results
        ),
        "library_sha256_equal": audit["library_sha256"] == req["library_sha256"],
        "source_sha256_equal": audit["source_sha256"] == req["source_sha256"],
        "raw_sha256_equal": audit["raw_sha256"] == req["raw_sha256"],
        "status": audit["status"],
        "limitation": audit["limitation"],
    }
    report["lifecycle_cross_binding"] = binding
    if not all(
        binding[key]
        for key in (
            "audit_sha256_matches_lifecycle_pin",
            "library_sha256_equal",
            "source_sha256_equal",
            "raw_sha256_equal",
        )
    ):
        finding("LIFECYCLE-CROSSBIND", "P1", "lifecycle evidence is not internally cross-bound")

    # --- 3. wrapper pin vs current source ----------------------------------
    current = ROOT / CURRENT_WRAPPER
    current_sha = sha256_file(current)
    current_size = current.stat().st_size
    report["current_wrapper"] = {
        "path": CURRENT_WRAPPER,
        "sha256": current_sha,
        "size_bytes": current_size,
    }
    wrapper_pins = []
    preserved_cache = {}
    for candidate in sorted((ROOT / "validation").glob("codegen-e0-build-*/build-manifest.json")):
        build = json.loads(candidate.read_text(encoding="utf-8"))
        staged = build.get("staged_sources", {}).get("model.cpp")
        if not staged:
            continue
        rel = repo_relative_source(staged["source_path"])
        pinned = staged["sha256"]
        preserved = find_preserved_copies(pinned, preserved_cache)
        entry = {
            "build_manifest": candidate.relative_to(ROOT).as_posix(),
            "build_id": build.get("build_id"),
            "pinned_sha256": pinned,
            "pinned_size_bytes": staged["size_bytes"],
            "source_path": staged["source_path"],
            "repo_relative_source": rel,
            # The pin names the canonical wrapper path, but the bytes it pins
            # are not necessarily today's bytes at that path.
            "pinned_is_canonical_head_blob": pinned == current_sha,
            "pinned_digest_is_git_object": git_object_exists(pinned),
            "pinned_bytes_preserved_in_tracked_snapshot": bool(preserved),
            "preserved_copy_count": len(preserved),
            "preserved_copy_example": preserved[0] if preserved else None,
            "matches_current_tracked_source": (
                rel == CURRENT_WRAPPER
                and staged["sha256"] == current_sha
                and staged["size_bytes"] == current_size
            ),
        }
        wrapper_pins.append(entry)
    report["wrapper_pins"] = wrapper_pins
    report["current_wrapper_tracked_at_head"] = wrapper_is_tracked_at_head()

    stale = [e for e in wrapper_pins if not e["matches_current_tracked_source"]]
    superseding = [e for e in wrapper_pins if e["matches_current_tracked_source"]]
    for entry in stale:
        preserved = entry["pinned_bytes_preserved_in_tracked_snapshot"]
        finding(
            "WRAPPER-PIN-STALE-PRESERVED" if preserved else "WRAPPER-PIN-STALE-LOST",
            "P2" if preserved else "P0",
            (
                f"{entry['build_manifest']} pins wrapper {entry['pinned_sha256'][:12]}… "
                f"({entry['pinned_size_bytes']} B) which is not the current tracked source "
                f"({current_sha[:12]}… / {current_size} B); the pinned bytes are "
                + (
                    f"preserved byte-identically in {entry['preserved_copy_count']} tracked "
                    f"snapshot(s), so the pin authenticates real archived material and does not "
                    "need to be rewritten"
                    if preserved
                    else "NOT recoverable from any tracked path, so the historical pin cannot be "
                    "re-verified at all"
                )
            ),
            {
                "build_manifest": entry["build_manifest"],
                "pinned_sha256": entry["pinned_sha256"],
                "size_bytes": entry["pinned_size_bytes"],
                "pinned_digest_is_git_object": entry["pinned_digest_is_git_object"],
                "current_sha256": current_sha,
                "current_size_bytes": current_size,
                "preserved_copy_example": entry["preserved_copy_example"],
                "preserved_copy_count": entry["preserved_copy_count"],
            },
        )
    if superseding:
        report["superseding_evidence"] = [
            e["build_manifest"] for e in superseding
        ]
        finding(
            "WRAPPER-CURRENT-DECLARED",
            "info",
            "a later, separately commissioned evidence directory already binds the current wrapper",
            report["superseding_evidence"],
        )
    else:
        finding(
            "WRAPPER-CURRENT-UNDECLARED",
            "P0",
            "no commissioned evidence binds the current wrapper; the drift would be an unaccepted change",
        )

    # --- 4. auditor's vendor regex classified ------------------------------
    code, tracked_raw = git("ls-files", "-z")
    tracked = [n for n in tracked_raw.split("\0") if n]
    vendor_hits = []
    for name in tracked:
        if VENDOR_RE.search(name):
            vendor_hits.append({"path": name, "classification": classify_path(name)})
    report["vendor_regex_hits"] = vendor_hits
    report["vendor_regex_hit_count"] = len(vendor_hits)
    classes = sorted({hit["classification"] for hit in vendor_hits})
    report["vendor_regex_hit_classes"] = classes
    real_vendor = [
        hit for hit in vendor_hits
        if hit["classification"] in {"vendor-dll-name", "vendor-zip-name", "binary-content", "unreadable"}
    ]
    report["real_vendor_material_count"] = len(real_vendor)
    if real_vendor:
        finding("VENDOR-REAL", "P0", "tracked vendor material found", real_vendor)
    elif vendor_hits:
        finding(
            "VENDOR-FALSE-POSITIVE",
            "P1",
            (
                f"the vendor rule matched {len(vendor_hits)} tracked paths on filename/path text alone; "
                f"all {len(vendor_hits)} classify as {classes} and none carries vendor bytes, so the audit "
                "violation is a filename-based misclassification"
            ),
            {"classes": classes, "example": vendor_hits[0]["path"]},
        )

    report["status"] = (
        "consistent"
        if not [f for f in report["findings"] if f["severity"] in {"P0", "P1"}]
        else "drift_detected"
    )
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    sys.stdout.buffer.write(raw.encode("utf-8"))
    if args.fail_on_drift and report["status"] != "consistent":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
